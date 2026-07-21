"""
RAG-quality eval (#19): retrieval recall@k + answer faithfulness/groundedness.

Exercises the REAL retrieval stack offline — the same heading-aware chunking (ingest) and
the same FastEmbed model (nodes.compute_embedding) used in production — over the company
knowledge base, then grades two things per question:

  - recall@k:      does the top-k retrieved context contain the facts the answer needs
                   (the `must_include` keywords)? Measures retrieval quality.
  - faithfulness:  is every claim in a context-only answer actually supported by that
                   context (LLM-as-judge)? Measures groundedness / hallucination.

No Qdrant needed: the index is built in-process (cosine over the chunk embeddings), so this
runs in CI. The judge + the answer generation call DeepSeek, so it needs a real key:

    DEEPSEEK_API_KEY=... python evals/run_rag.py [--recall-threshold 0.8] [--faithfulness-threshold 0.9]

Exits non-zero if either metric is below its threshold, so it can gate a build.
"""

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import _deepseek  # noqa: E402 — evals/_deepseek.py (resilient DeepSeek call)
from config import COMPANY_TOP_K  # noqa: E402
from rag.ingest import KB_PATH, chunk_document  # noqa: E402
from nodes import compute_embedding  # noqa: E402


def _cosine(a: list, b: list) -> float:
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    return dot / (math.sqrt(na) * math.sqrt(nb)) if na and nb else 0.0


def _build_index():
    """Chunk + embed the KB in-process (same chunking/model as production, no Qdrant)."""
    chunks = chunk_document(Path(KB_PATH).read_text(encoding="utf-8"))
    vectors = [compute_embedding(c["text"]) for c in chunks]
    return chunks, vectors


def _retrieve(question: str, chunks: list, vectors: list, k: int) -> list:
    qv = compute_embedding(question)
    ranked = sorted(range(len(chunks)), key=lambda i: _cosine(qv, vectors[i]), reverse=True)
    return [chunks[i]["text"] for i in ranked[:k]]


def _answer_from_context(question: str, context: str, language: str) -> str:
    prompt = (
        f"Answer the question using ONLY the context below. If the answer is not in the "
        f"context, say you don't have that information. Reply in {language}.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}"
    )
    data = _deepseek.chat({
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    })
    return data["choices"][0]["message"]["content"]


def _is_faithful(question: str, context: str, answer: str) -> bool:
    prompt = (
        "You are a strict grader. Is EVERY factual claim in the Answer directly supported by "
        "the Context (no invented facts)? An honest 'I don't have that information' counts as "
        f'supported.\n\nContext:\n{context}\n\nQuestion: {question}\nAnswer: {answer}\n\n'
        'Reply ONLY with JSON: {"grounded": true|false}.'
    )
    data = _deepseek.chat({
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    })
    try:
        return bool(json.loads(data["choices"][0]["message"]["content"]).get("grounded"))
    except (ValueError, KeyError, IndexError, TypeError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recall-threshold", type=float, default=0.8)
    ap.add_argument("--faithfulness-threshold", type=float, default=0.9)
    ap.add_argument("--top-k", type=int, default=COMPANY_TOP_K)
    ap.add_argument("--dataset", default=str(ROOT / "evals" / "rag.jsonl"))
    args = ap.parse_args()

    rows = [json.loads(line) for line in Path(args.dataset).read_text(encoding="utf-8").splitlines() if line.strip()]
    chunks, vectors = _build_index()

    recall_hits, faithful_hits, fails = 0, 0, []
    try:
        for r in rows:
            context_chunks = _retrieve(r["question"], chunks, vectors, args.top_k)
            context = "\n\n".join(context_chunks)
            recalled = all(kw.lower() in context.lower() for kw in r["must_include"])
            recall_hits += recalled

            answer = _answer_from_context(r["question"], context, r.get("language", "en"))
            grounded = _is_faithful(r["question"], context, answer)
            faithful_hits += grounded

            if not recalled or not grounded:
                fails.append((r["question"], recalled, grounded))
    except _deepseek.InfraError as e:
        print(f"::error::eval aborted (infra, not a regression): {e}")
        return 2

    n = len(rows)
    recall = recall_hits / n if n else 0.0
    faithfulness = faithful_hits / n if n else 0.0
    print(f"RAG recall@{args.top_k}: {recall_hits}/{n} = {recall:.1%}")
    print(f"RAG faithfulness: {faithful_hits}/{n} = {faithfulness:.1%}")
    for question, recalled, grounded in fails:
        print(f"  FAIL: {question!r}  recalled={recalled}  grounded={grounded}")

    if recall < args.recall_threshold or faithfulness < args.faithfulness_threshold:
        print(f"BELOW THRESHOLD (recall {args.recall_threshold:.0%} / faithfulness "
              f"{args.faithfulness_threshold:.0%}) — failing the build")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
