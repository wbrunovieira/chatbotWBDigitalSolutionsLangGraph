"""
Ingest the company knowledge base (company_info.md) into Qdrant as retrievable chunks.

Replaces the old approach of storing the whole document as a single vector (searched with
limit=1, which returned the entire doc regardless of the query). Here the document is split
into heading-aware chunks (~300-500 tokens), each embedded and stored separately so real
top-k retrieval can return only the relevant passages.

Idempotent and content-addressed: each chunk's point id is derived from its content, so
re-running upserts identical points (no duplicates) and prunes points whose content is gone.
Runs at app startup (cheap when unchanged) and as a CLI: `python ingest.py`.
"""

import hashlib
import logging
import re

from qdrant_client.http.models import Distance, PointStruct, VectorParams

COLLECTION = "company_info"
VECTOR_SIZE = 384
KB_PATH = "company_info.md"
# ~300-500 tokens at ~4 chars/token. Kept as chars to avoid a tokenizer dependency here.
CHUNK_MAX_CHARS = 1600

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _split_body(body: str, max_chars: int) -> list:
    """Split an over-long section body into <= max_chars pieces on paragraph boundaries."""
    if len(body) <= max_chars:
        return [body]
    pieces, current = [], ""
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) + 2 > max_chars:
            pieces.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        pieces.append(current)
    # A single paragraph longer than max_chars still has to be broken up.
    final = []
    for piece in pieces:
        while len(piece) > max_chars:
            final.append(piece[:max_chars])
            piece = piece[max_chars:]
        if piece:
            final.append(piece)
    return final


def chunk_document(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list:
    """
    Split markdown into heading-aware chunks. Each chunk carries its heading path as a
    `section` label and is prefixed with that path so a retrieved passage stays self-describing.
    """
    chunks = []
    heading_stack = []  # list of (level, title)
    buffer = []

    def flush():
        body = "\n".join(buffer).strip()
        buffer.clear()
        if not body:
            return
        section = " > ".join(title for _, title in heading_stack) or "WB Digital Solutions"
        for piece in _split_body(body, max_chars):
            chunks.append({"section": section, "text": f"{section}\n\n{piece}".strip()})

    for line in text.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            continue
        if line.strip() == "---":  # horizontal rule = section boundary
            flush()
            continue
        buffer.append(line)
    flush()
    return chunks


def _chunk_id(chunk: dict, model_tag: str = "") -> int:
    # The point id folds in the embedding-model tag: swapping the model changes every id,
    # so the "unchanged" skip below can't leave stale vectors from the old model behind
    # (the KB text is identical across a model swap, so text alone would falsely match).
    key = f"{model_tag}\x00{chunk['section']}\x00{chunk['text']}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:15], 16)  # 60-bit unsigned int, safely within Qdrant's uint64 id space


def _ensure_collection(client) -> None:
    try:
        client.get_collection(COLLECTION)
    except Exception:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def _existing_ids(client) -> set:
    ids, offset = set(), None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION, limit=256, offset=offset,
            with_payload=False, with_vectors=False,
        )
        ids.update(p.id for p in points)
        if offset is None:
            break
    return ids


def ingest_company_info(client, path: str = KB_PATH, embed_fn=None, model_tag: str = None) -> dict:
    """
    Chunk + embed + upsert the KB, idempotently. Returns a summary dict.

    embed_fn defaults to nodes.compute_embedding; it's injectable so tests can run without
    downloading the ONNX model. model_tag defaults to the active embedding model name and is
    folded into each point id so a model swap forces a full re-ingest (see _chunk_id).
    """
    if embed_fn is None:
        from nodes import compute_embedding as embed_fn  # lazy: avoids importing the model at import time
    if model_tag is None:
        try:
            from nodes import EMBEDDING_MODEL_NAME
            model_tag = EMBEDDING_MODEL_NAME
        except Exception:
            model_tag = ""

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = chunk_document(text)
    target = {_chunk_id(c, model_tag): c for c in chunks}

    _ensure_collection(client)
    existing = _existing_ids(client)
    if existing == set(target):
        logging.info("company_info ingest: unchanged (%d chunks), skipping", len(target))
        return {"skipped": True, "chunks": len(target), "pruned": 0}

    points = [
        PointStruct(id=pid, vector=embed_fn(c["text"]), payload={"text": c["text"], "section": c["section"]})
        for pid, c in target.items()
    ]
    client.upsert(collection_name=COLLECTION, points=points)

    stale = list(existing - set(target))
    if stale:
        client.delete(collection_name=COLLECTION, points_selector=stale)

    logging.info("company_info ingest: %d chunks upserted, %d pruned", len(points), len(stale))
    return {"skipped": False, "chunks": len(points), "pruned": len(stale)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from qdrant_client import QdrantClient

    from config import QDRANT_API_KEY, QDRANT_HOST

    client = QdrantClient(url=QDRANT_HOST, api_key=QDRANT_API_KEY)
    print(ingest_company_info(client))
