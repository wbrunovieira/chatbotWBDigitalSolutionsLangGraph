import json
import math
from urllib.parse import quote

import redis.asyncio as redis

from config import (
    REDIS_CACHE_EXPIRE_SECONDS,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
)

# The client is built lazily rather than at import time: importing this module
# should not open a socket, and tests need a seam to swap in a fake.
_client: redis.Redis | None = None


def _build_client() -> redis.Redis:
    # "generate_on_deploy" is the placeholder in ansible/inventory.ini.example; treat
    # it as "no password" instead of authenticating with the literal placeholder.
    password = REDIS_PASSWORD if REDIS_PASSWORD and REDIS_PASSWORD != "generate_on_deploy" else None

    if password:
        # The password is URL-quoted because it lands inside a redis:// URL, where
        # an unescaped ':' or '@' would silently corrupt the host/port parsing.
        return redis.from_url(
            f"redis://:{quote(password, safe='')}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
        )
    return redis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def set_redis(client) -> None:
    """Override the client. Test seam — production code never calls this."""
    global _client
    _client = client


async def get_cached_response(key: str):
    cached = await get_redis().get(key)
    if cached:
        return json.loads(cached)
    return None


async def set_cached_response(key: str, value: dict, expire: int = REDIS_CACHE_EXPIRE_SECONDS):
    await get_redis().set(key, json.dumps(value), ex=expire)


# --- Semantic cache (#12) ---
# A bounded bucket of {vec, payload} entries per (language, page) so a paraphrase of an
# already-answered question can be served without a new LLM call. The caller computes the
# embedding (keeps this module free of the embedding/nodes import → no cycle).


def _cosine(a: list, b: list) -> float:
    """Cosine similarity of two equal-length vectors; 0.0 if either is degenerate."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


async def semantic_get(bucket_key: str, query_vec: list, threshold: float):
    """Return the payload whose stored embedding is most similar to `query_vec`
    (cosine >= threshold), or None. `query_vec` is precomputed by the caller."""
    raw = await get_redis().get(bucket_key)
    if not raw:
        return None
    try:
        entries = json.loads(raw)
    except (ValueError, TypeError):
        return None
    best_payload, best_sim = None, -1.0
    for entry in entries:
        sim = _cosine(query_vec, entry.get("vec") or [])
        if sim > best_sim:
            best_payload, best_sim = entry.get("payload"), sim
    return best_payload if best_payload is not None and best_sim >= threshold else None


async def semantic_put(bucket_key: str, query_vec: list, payload: dict, max_entries: int,
                       expire: int = REDIS_CACHE_EXPIRE_SECONDS):
    """Append {vec, payload} to the bucket, keeping only the most recent `max_entries`."""
    raw = await get_redis().get(bucket_key)
    try:
        entries = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        entries = []
    entries.append({"vec": query_vec, "payload": payload})
    entries = entries[-max_entries:]
    await get_redis().set(bucket_key, json.dumps(entries), ex=expire)
