# config.py
import os
from dotenv import load_dotenv
import logging


load_dotenv()


logging.basicConfig(level=logging.INFO)


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
QDRANT_HOST = os.getenv("QDRANT_HOST")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_CACHE_EXPIRE_SECONDS = 604800  # 7 dias

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
MY_WHATSAPP_NUMBER = os.getenv("MY_WHATSAPP_NUMBER")