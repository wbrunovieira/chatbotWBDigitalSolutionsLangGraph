import redis.asyncio as redis
import json
import os
from config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_CACHE_EXPIRE_SECONDS

REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
if REDIS_PASSWORD and REDIS_PASSWORD != "generate_on_deploy":
    redis_client = redis.from_url(f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
else:
    redis_client = redis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")

async def get_cached_response(key: str):
    cached = await redis_client.get(key)
    if cached:
        return json.loads(cached)
    return None

async def set_cached_response(key: str, value: dict, expire: int = REDIS_CACHE_EXPIRE_SECONDS):
    await redis_client.set(key, json.dumps(value), ex=expire)