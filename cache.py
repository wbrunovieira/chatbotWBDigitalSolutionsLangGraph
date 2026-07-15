import json
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
