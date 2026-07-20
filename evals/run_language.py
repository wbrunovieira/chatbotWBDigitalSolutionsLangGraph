"""
Per-language answer-quality eval (#23): does the bot answer in the language it was asked in?

The knowledge base is in English, so a pt/es/it question risks drifting into an English
answer. This exercises the REAL production language instruction (nodes.LANGUAGE_INSTRUCTIONS,
imported — not a copy) over an English context, then uses an LLM to detect the answer's
language and checks it matches. A red gate means a per-language quality regression.

    DEEPSEEK_API_KEY=... python evals/run_language.py [--threshold 0.9]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import _deepseek  # noqa: E402 — evals/_deepseek.py (resilient DeepSeek call)
from nodes import LANGUAGE_INSTRUCTIONS  # noqa: E402 — the exact production instruction

# English context on purpose: it's the drift risk the language instruction must overcome.
_CONTEXT = (
    "WB Digital Solutions builds premium custom websites, business process automation, and "
    "AI solutions (chatbots, generative AI, machine learning). Technologies: Next.js, "
    "TypeScript, Python, Rust."
)
_LANG_NAMES = {"en": "English", "es": "Spanish", "it": "Italian", "pt-BR": "Portuguese"}


def _answer(question: str, language: str) -> str:
    prompt = (
        f"{LANGUAGE_INSTRUCTIONS[language]}\n\nContext: {_CONTEXT}\n\n"
        f"User question: {question}\n\nAnswer helpfully in 1-2 sentences."
    )
    data = _deepseek.chat({
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    })
    return data["choices"][0]["message"]["content"]


def _detected_language(text: str) -> str:
    prompt = (
        "What language is the following text written in? Reply ONLY with JSON "
        '{"language": "<English|Spanish|Italian|Portuguese|Other>"}.\n\n' + text
    )
    data = _deepseek.chat({
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    })
    try:
        return json.loads(data["choices"][0]["message"]["content"]).get("language", "")
    except (ValueError, KeyError, IndexError, TypeError):
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.8)
    ap.add_argument("--dataset", default=str(ROOT / "evals" / "language.jsonl"))
    args = ap.parse_args()

    rows = [json.loads(line) for line in Path(args.dataset).read_text(encoding="utf-8").splitlines() if line.strip()]
    passed, fails = 0, []
    try:
        for r in rows:
            answer = _answer(r["question"], r["language"])
            detected = _detected_language(answer)
            want = _LANG_NAMES[r["language"]]
            if want.lower() in detected.lower():
                passed += 1
            else:
                fails.append((r["question"], want, detected))
    except _deepseek.InfraError as e:
        print(f"::error::eval aborted (infra, not a regression): {e}")
        return 2

    accuracy = passed / len(rows) if rows else 0.0
    print(f"language consistency: {passed}/{len(rows)} = {accuracy:.1%}")
    for question, want, got in fails:
        print(f"  FAIL: {question!r}  want={want}  got={got}")

    if accuracy < args.threshold:
        print(f"BELOW THRESHOLD ({args.threshold:.0%}) — failing the build")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
