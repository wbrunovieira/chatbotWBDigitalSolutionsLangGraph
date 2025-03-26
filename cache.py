import redis.asyncio as redis
import json
from config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_CACHE_EXPIRE_SECONDS

redis_client = redis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")

async def get_cached_response(key: str):
    cached = await redis_client.get(key)
    if cached:
        return json.loads(cached)
    return None

async def set_cached_response(key: str, value: dict, expire: int = REDIS_CACHE_EXPIRE_SECONDS):
    await redis_client.set(key, json.dumps(value), ex=expire)