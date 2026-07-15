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
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_CACHE_EXPIRE_SECONDS = 604800  # 7 dias

# Runtime environment. Anything other than "production" is treated as dev.
APP_ENV = os.getenv("APP_ENV", "development")
IS_PRODUCTION = APP_ENV == "production"

# --- Abuse and cost controls (see security.py) ---

# Hard ceiling on DeepSeek spend per UTC day. Once crossed, /chat returns 503
# instead of calling the LLM. This is the backstop that guarantees abuse cannot
# turn into an invoice, regardless of how the attacker got in.
DAILY_SPEND_LIMIT_USD = float(os.getenv("DAILY_SPEND_LIMIT_USD", "5.0"))

# Per-IP slice of the daily budget, so a single abuser cannot burn the whole cap
# and take the chatbot offline for everyone else.
DAILY_SPEND_LIMIT_PER_IP_USD = float(os.getenv("DAILY_SPEND_LIMIT_PER_IP_USD", "0.50"))

# Fraction of the daily cap that triggers a one-per-day ERROR-level alert.
SPEND_ALERT_THRESHOLD = float(os.getenv("SPEND_ALERT_THRESHOLD", "0.70"))

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "100"))

# Caps the token-amplification blast radius: without this, a single 10MB body
# (nginx allowed up to client_max_body_size) is fanned out into up to 3 DeepSeek
# calls per request.
MAX_MESSAGE_LENGTH = int(os.getenv("MAX_MESSAGE_LENGTH", "1000"))

# Shared secret for operator-only endpoints (/usage-report). Safe as a static
# token because it is used server-to-server, never from the browser.
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN")

# Langfuse
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://calendar-langfuse.wbdigitalsolutions.com")