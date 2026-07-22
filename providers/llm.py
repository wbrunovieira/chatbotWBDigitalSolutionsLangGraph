"""LLM routing + provider fallback (#13).

A thin layer over deepseek_client that (1) routes each task to a model — a cheap/fast model
for classification (intent), a stronger one for generation/revision — and (2) fails over to
a secondary OpenAI-compatible provider when the primary errors or returns a 5xx.

Every call site goes through `chat_completion(messages, task=...)`. Model routing and the
failover are pure config, so with the defaults (both models = DEEPSEEK_MODEL, no fallback
configured) behaviour is identical to calling deepseek_client directly.
"""

import logging

import httpx

import config
from providers import deepseek_client

# task -> configured model. Unknown tasks fall back to the primary model.
_TASK_MODELS = {
    "intent": lambda: config.INTENT_MODEL,
    "generation": lambda: config.GENERATION_MODEL,
    "revision": lambda: config.GENERATION_MODEL,
}


def model_for(task: str) -> str:
    return _TASK_MODELS.get(task, lambda: config.DEEPSEEK_MODEL)()


def fallback_configured() -> bool:
    return bool(config.FALLBACK_API_URL and config.FALLBACK_API_KEY and config.FALLBACK_MODEL)


# Statuses where the primary can't serve a well-formed request right now, so retrying the
# SAME request on the secondary is worth it: any 5xx (provider outage), 402 (DeepSeek's
# "Insufficient Balance" — the out-of-credit case our balance alert also guards), and 429
# (rate-limited / at capacity). A 4xx like 400/401/403/404 is our fault (bad request, revoked
# key, wrong model); failing over would just replay the broken request and burn the secondary,
# so we let those surface instead.
_FAILOVER_STATUSES = frozenset({402, 429})


def _should_failover(status: int) -> bool:
    return status >= 500 or status in _FAILOVER_STATUSES


async def _fallback_completion(messages, **kwargs) -> httpx.Response:
    """Same request against the secondary provider (model/url/key from config)."""
    kwargs.pop("model", None)
    return await deepseek_client.chat_completion(
        messages,
        model=config.FALLBACK_MODEL,
        api_url=config.FALLBACK_API_URL,
        api_key=config.FALLBACK_API_KEY,
        **kwargs,
    )


async def chat_completion(messages: list, *, task: str = "generation", **kwargs) -> httpx.Response:
    """Route by task to the primary provider; fail over to the secondary on error/5xx.

    Returns the raw httpx.Response, so callers keep their existing `.json()` / choices
    handling. When no fallback is configured, a primary failure propagates exactly as before.
    """
    model = kwargs.pop("model", None) or model_for(task)
    try:
        resp = await deepseek_client.chat_completion(messages, model=model, **kwargs)
    except httpx.HTTPError as exc:
        if fallback_configured():
            logging.warning("LLM primary error on task=%s (%s); failing over to secondary", task, exc)
            return await _fallback_completion(messages, **kwargs)
        raise
    # Some statuses mean "primary is down / out of credit / throttled" rather than a client
    # error — fail over too, if we can. (getattr: a real httpx.Response always has status_code;
    # be defensive for odd/faked responses.)
    status = getattr(resp, "status_code", 200)
    if _should_failover(status) and fallback_configured():
        logging.warning("LLM primary %s on task=%s; failing over to secondary", status, task)
        return await _fallback_completion(messages, **kwargs)
    return resp


async def stream_completion(messages: list, *, task: str = "generation", **kwargs):
    """Stream a routed completion, yielding content-delta strings (#14).

    Routes the model by task like chat_completion. No provider failover here: a mid-stream
    switch would double-emit tokens, so a streaming failure surfaces to the endpoint, which
    degrades to a graceful message.
    """
    model = kwargs.pop("model", None) or model_for(task)
    async for delta in deepseek_client.stream_chat_completion(messages, model=model, **kwargs):
        yield delta
