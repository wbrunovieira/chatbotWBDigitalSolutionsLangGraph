# config.py
import os
from dotenv import load_dotenv
import logging


load_dotenv()


logging.basicConfig(level=logging.INFO)


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
# DeepSeek's OpenAI-compatible endpoint + model. Centralized here (were hardcoded at every
# call site) so a provider/model swap is a one-place change — see deepseek_client.py.
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# Model routing (#13, see llm.py): a cheap/fast model for classification (intent) and a
# stronger one for generation/revision. Both default to DEEPSEEK_MODEL, so the routing seam
# is free until a cheaper intent model is pointed at INTENT_MODEL via env.
INTENT_MODEL = os.getenv("INTENT_MODEL", DEEPSEEK_MODEL)
GENERATION_MODEL = os.getenv("GENERATION_MODEL", DEEPSEEK_MODEL)

# Secondary provider (#13): if the primary fails (transport error or 5xx), retry once on this
# OpenAI-compatible endpoint. Unset by default -> no failover, behaviour unchanged.
FALLBACK_API_URL = os.getenv("FALLBACK_API_URL", "")
FALLBACK_API_KEY = os.getenv("FALLBACK_API_KEY", "")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")
QDRANT_HOST = os.getenv("QDRANT_HOST")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_CACHE_EXPIRE_SECONDS = 604800  # 7 dias

# Semantic cache (#12): an embedding-similarity layer in front of the exact-match cache so
# paraphrases of an already-answered question hit without a new LLM call. Only applied to
# shared/anon users (context-free, user-independent turns) — logged-in users with memory
# skip it so a paraphrase can't bypass their conversation. High threshold to avoid serving
# a near-but-wrong answer; bounded per (language, page) bucket.
SEMANTIC_CACHE_ENABLED = os.getenv("SEMANTIC_CACHE_ENABLED", "true").lower() == "true"
SEMANTIC_CACHE_THRESHOLD = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.92"))
SEMANTIC_CACHE_MAX_ENTRIES = int(os.getenv("SEMANTIC_CACHE_MAX_ENTRIES", "50"))

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

# --- Agent tools (see tools.py) ---

# WB-CRM (internal): create_lead posts here. In production the chatbot container is
# attached to the wb-crm network and reaches it by service name; in the demo this points
# at a stub so `docker compose up` works without the real CRM.
WBCRM_BASE_URL = os.getenv("WBCRM_BASE_URL", "http://wb-crm-backend:3010")
WBCRM_API_TOKEN = os.getenv("WBCRM_API_TOKEN", "")
LEAD_SOURCE_GROUP = os.getenv("LEAD_SOURCE_GROUP", "bot")

# RAG retrieval tuning (see nodes.retrieve_company_context). Env-tunable so the score
# threshold can be re-calibrated from prod traces without a code change — the default is
# calibrated for the multilingual-query / English-KB cross-lingual score range.
COMPANY_TOP_K = int(os.getenv("COMPANY_TOP_K", "4"))
COMPANY_SCORE_THRESHOLD = float(os.getenv("COMPANY_SCORE_THRESHOLD", "0.2"))

# Short-term conversation memory: how many recent messages (user+assistant turns) to keep
# in the checkpointed history and replay to the model. 10 = the last ~5 turns; caps the
# context window and cost as a conversation grows.
# Rounded down to an even number so the [-N:] slice never orphans a user message from its
# assistant reply (history grows in user/assistant pairs).
MAX_HISTORY_MESSAGES = (int(os.getenv("MAX_HISTORY_MESSAGES", "10")) // 2) * 2

# Long-term memory: semantic recall of this user's most relevant PAST exchanges from
# chat_logs (across sessions). Top-k above a score floor.
USER_CONTEXT_TOP_K = int(os.getenv("USER_CONTEXT_TOP_K", "3"))
USER_CONTEXT_SCORE_THRESHOLD = float(os.getenv("USER_CONTEXT_SCORE_THRESHOLD", "0.3"))
# user_ids that are shared across many people — never pull a cross-user "history" for these.
SHARED_USER_IDS = {"anon", "experiment", "", None}

# LGPD retention: delete chat_logs points older than this many days (run by retention.py).
CHAT_LOGS_RETENTION_DAYS = int(os.getenv("CHAT_LOGS_RETENTION_DAYS", "90"))

# Answer quality (see nodes.revision / main._maybe_schedule_judge). Kept OFF the hot path:
# revision is a second LLM round-trip, so only long answers that need trimming toward the
# ~500-char target are revised; short, direct replies are returned as generated. The judge
# is sampled and scored in a background task, never blocking the visitor's response.
REVISION_MAX_LENGTH = int(os.getenv("REVISION_MAX_LENGTH", "600"))
JUDGE_SAMPLE_RATE = float(os.getenv("JUDGE_SAMPLE_RATE", "0.1"))

# schedule_meeting hands the user this direct booking link.
BOOKING_URL = os.getenv("BOOKING_URL", "https://agenda.wbdigitalsolutions.com/book")

# handoff_to_human / fallbacks route the user here.
WHATSAPP_CONTACT = os.getenv("WHATSAPP_CONTACT", "(11) 98286-4581")

# Evolution API (WhatsApp) — create_lead notifies the team here. Best-effort: if any of
# these is unset the notification is skipped (the lead still persists).
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "")
MY_WHATSAPP_NUMBER = os.getenv("MY_WHATSAPP_NUMBER", "")

# Tool-failure handling (#8d): each tool call is bounded by a timeout and a few retries.
TOOL_TIMEOUT_SECONDS = float(os.getenv("TOOL_TIMEOUT_SECONDS", "8"))
TOOL_RETRIES = int(os.getenv("TOOL_RETRIES", "1"))

# Anti-spam: cap how many leads one client IP can create per UTC day (create_lead posts
# to the CRM and pushes a WhatsApp notify, so an uncapped loop would spam both).
MAX_LEADS_PER_IP_PER_DAY = int(os.getenv("MAX_LEADS_PER_IP_PER_DAY", "5"))

# Langfuse
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://calendar-langfuse.wbdigitalsolutions.com")