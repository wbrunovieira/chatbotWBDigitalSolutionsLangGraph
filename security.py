# security.py
"""
Per-IP rate limiting and a cost circuit-breaker (spend cap) for /chat.

Counters live in Redis rather than process memory: they must survive container
restarts and be shared across uvicorn workers. An in-memory counter would reset on
every deploy and be tracked separately per worker, effectively multiplying the
spend cap by the number of workers.

These are FastAPI dependencies, not middleware, on purpose. A dependency runs
inside CORSMiddleware, so 429/503 responses carry the CORS headers and the browser
sees the real status. Middleware added after CORS would sit outside it, and the
widget would surface a misleading "CORS error" instead of the 429.

Config and the Redis client are resolved per call (via `config.X` / `get_redis()`)
rather than bound at import, so limits stay overridable in tests.
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, Request

import config
from cache import get_redis

# Spend counters expire after 48h: covers the current UTC day with slack.
SPEND_TTL_SECONDS = 172800

# Friendly copy shown in the site widget, so it stays in Portuguese.
_WHATSAPP = "(11) 98286-4581"
_TOO_FAST = "Muitas mensagens em pouco tempo. Aguarde alguns segundos e tente de novo."
_HOURLY_EXHAUSTED = f"Limite de mensagens por hora atingido. Fale com a gente no WhatsApp {_WHATSAPP}."
_BUDGET_EXHAUSTED = f"O assistente está temporariamente indisponível. Fale com a gente no WhatsApp {_WHATSAPP}."
_IP_BUDGET_EXHAUSTED = f"Você atingiu o limite de uso de hoje. Fale com a gente no WhatsApp {_WHATSAPP}."


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_client_ip(request: Request) -> str:
    """
    Resolve the real client IP.

    Trusting these headers depends on the app NOT being published directly to the
    internet: the production compose binds the app port to 127.0.0.1 only, so nginx
    is the sole reachable path and the sole injector of X-Real-IP. If that port is
    ever published on 0.0.0.0 again, anyone can forge these headers and walk past
    the rate limit.

    CF-Connecting-IP is checked first so this keeps working once the domain moves
    behind the Cloudflare proxy (stage 3), where X-Real-IP becomes the edge IP.
    """
    for header in ("cf-connecting-ip", "x-real-ip"):
        value = request.headers.get(header)
        if value and value.strip():
            return value.strip()

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and forwarded.strip():
        return forwarded.split(",")[0].strip()

    return request.client.host if request.client else "unknown"


async def _incr_with_ttl(key: str, ttl: int) -> int:
    pipe = get_redis().pipeline()
    pipe.incr(key)
    pipe.expire(key, ttl)
    count, _ = await pipe.execute()
    return int(count)


async def _read_float(key: str) -> float:
    return float(await get_redis().get(key) or 0.0)


async def check_rate_limit(ip: str) -> None:
    """Fixed-window counters, per minute and per hour. Raises 429 when exceeded."""
    if not config.RATE_LIMIT_ENABLED:
        return

    now = datetime.now(timezone.utc)

    per_minute = await _incr_with_ttl(f"rl:min:{ip}:{now:%Y%m%d%H%M}", 120)
    if per_minute > config.RATE_LIMIT_PER_MINUTE:
        logging.warning("Rate limit hit (per-minute): ip=%s count=%s", ip, per_minute)
        raise HTTPException(status_code=429, detail=_TOO_FAST, headers={"Retry-After": "60"})

    per_hour = await _incr_with_ttl(f"rl:hour:{ip}:{now:%Y%m%d%H}", 7200)
    if per_hour > config.RATE_LIMIT_PER_HOUR:
        logging.warning("Rate limit hit (per-hour): ip=%s count=%s", ip, per_hour)
        raise HTTPException(status_code=429, detail=_HOURLY_EXHAUSTED, headers={"Retry-After": "3600"})


async def check_spend_cap(ip: str) -> None:
    """
    Cost circuit-breaker. Raises 503 once today's spend (global, or for this IP) is
    over budget, BEFORE any LLM call happens.

    The cap is checked on the way in and the cost is only recorded once the response
    exists, so a request already in flight can overshoot the cap slightly. With
    `message` capped at MAX_MESSAGE_LENGTH and at most 3 DeepSeek calls per request,
    that overshoot is on the order of cents.
    """
    day = today()

    global_spend = await _read_float(f"spend:global:{day}")
    if global_spend >= config.DAILY_SPEND_LIMIT_USD:
        logging.error(
            "GLOBAL SPEND CAP REACHED: $%.4f/$%.2f on %s - refusing LLM calls",
            global_spend, config.DAILY_SPEND_LIMIT_USD, day,
        )
        raise HTTPException(status_code=503, detail=_BUDGET_EXHAUSTED, headers={"Retry-After": "3600"})

    ip_spend = await _read_float(f"spend:ip:{ip}:{day}")
    if ip_spend >= config.DAILY_SPEND_LIMIT_PER_IP_USD:
        logging.warning(
            "Per-IP spend cap reached: ip=%s $%.4f/$%.2f on %s",
            ip, ip_spend, config.DAILY_SPEND_LIMIT_PER_IP_USD, day,
        )
        raise HTTPException(status_code=503, detail=_IP_BUDGET_EXHAUSTED, headers={"Retry-After": "3600"})


async def record_spend(ip: str, cost_usd: float) -> None:
    """Add a request's real cost to today's counters and fire the alert threshold."""
    if cost_usd <= 0:
        return

    day = today()
    global_key = f"spend:global:{day}"
    ip_key = f"spend:ip:{ip}:{day}"

    pipe = get_redis().pipeline()
    pipe.incrbyfloat(global_key, cost_usd)
    pipe.expire(global_key, SPEND_TTL_SECONDS)
    pipe.incrbyfloat(ip_key, cost_usd)
    pipe.expire(ip_key, SPEND_TTL_SECONDS)
    results = await pipe.execute()

    global_spend = float(results[0])
    threshold = config.DAILY_SPEND_LIMIT_USD * config.SPEND_ALERT_THRESHOLD
    if global_spend < threshold:
        return

    # SET NX keeps this to a single alert per day, even across workers.
    is_first_alert = await get_redis().set(f"spend:alert:{day}", "1", ex=SPEND_TTL_SECONDS, nx=True)
    if is_first_alert:
        logging.error(
            "SPEND ALERT: $%.4f of $%.2f (%.0f%% of the daily cap) on %s",
            global_spend,
            config.DAILY_SPEND_LIMIT_USD,
            (global_spend / config.DAILY_SPEND_LIMIT_USD) * 100,
            day,
        )


async def get_spend_snapshot() -> dict:
    """Current circuit-breaker state, surfaced by /usage-report."""
    day = today()
    limit = config.DAILY_SPEND_LIMIT_USD
    spent = await _read_float(f"spend:global:{day}")
    return {
        "date": day,
        "spent_usd": round(spent, 4),
        "daily_limit_usd": limit,
        "percent_used": round((spent / limit) * 100, 1) if limit else 0.0,
        "circuit_open": spent >= limit,
    }


async def enforce_chat_limits(request: Request) -> str:
    """
    Dependency for /chat. Returns the client IP so the handler can bill cost to it.

    Fails OPEN when Redis is unreachable: refusing requests would take the whole
    chatbot offline on a Redis hiccup, and after stage 1 Redis is only reachable on
    the internal Docker network, so an attacker cannot knock it over to escape the
    limit. The trade-off is deliberate — while Redis is down there is no spend cap,
    which is what the ERROR log below exists to surface.
    """
    ip = get_client_ip(request)
    try:
        await check_rate_limit(ip)
        await check_spend_cap(ip)
    except HTTPException:
        raise
    except Exception as e:
        logging.error("Redis unavailable for rate limit / spend cap (FAILING OPEN): %s", e)
    return ip
