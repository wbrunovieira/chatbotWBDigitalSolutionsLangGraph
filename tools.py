"""
Agent tools the model decides to call.

Three tools, each with a Pydantic argument schema (validated before the call), run under a
timeout + bounded retry, and failing GRACEFULLY — a tool never crashes the turn; on failure
it returns an ok=False result whose `message` falls back to a human handoff.

- create_lead      — persist a lead in the WB-CRM, then best-effort notify the team on WhatsApp.
- schedule_meeting — give the user the direct booking link (and capture the lead).
- handoff_to_human — connect the user to a human on WhatsApp.

`TOOL_SPECS` is the OpenAI/DeepSeek function-calling schema; `dispatch()` validates and runs a
tool by name. Neither the graph nor the tests need to know a tool's internals.
"""

import asyncio
import contextvars
import logging
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

import httpx
from pydantic import BaseModel, Field, field_validator

import behavior as behavior_ctx
import guardrails

import config
from cache import get_redis

_E164 = re.compile(r"^\+\d{8,15}$")

# Keep strong refs to fire-and-forget tasks so they aren't garbage-collected mid-flight.
_bg_tasks: set = set()


def _fire_and_forget(coro) -> None:
    task = asyncio.ensure_future(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


# The request's client IP, bound per request (main.py) so create_lead can rate-cap leads.
_client_ip: contextvars.ContextVar = contextvars.ContextVar("tool_client_ip", default="unknown")


def set_client_ip(ip: str) -> None:
    _client_ip.set(ip or "unknown")


# The request's optional behavioral context (#8b), bound per request so create_lead can
# score + enrich the lead regardless of what the model passed as tool args.
_behavior: contextvars.ContextVar = contextvars.ContextVar("tool_behavior", default=None)


def set_behavior(value: Optional[dict]) -> None:
    _behavior.set(behavior_ctx.as_dict(value))


async def _lead_quota_ok() -> bool:
    """
    True if the current IP is under its daily lead cap (and count this attempt). Anti-spam
    for create_lead. Fails OPEN — a Redis hiccup must never block a genuine lead.
    """
    ip = _client_ip.get()
    # MCP clients are local & trusted (stdio), not a public spam surface — don't cap them
    # (otherwise the 6th lead/day would be silently dropped as a fake "success").
    if ip == "mcp":
        return True
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"leads:ip:{ip}:{day}"
    try:
        pipe = get_redis().pipeline()
        pipe.incr(key)
        pipe.expire(key, 172800)
        count, _ = await pipe.execute()
        return int(count) <= config.MAX_LEADS_PER_IP_PER_DAY
    except Exception as e:  # noqa: BLE001
        logging.warning("lead quota check failed (allowing): %s", e)
        return True


def _normalize_phone(value: Optional[str]) -> Optional[str]:
    """Coerce a phone into E.164 (+digits). Returns None if it can't be made valid."""
    if not value:
        return None
    digits = re.sub(r"[^\d+]", "", value)
    if not digits.startswith("+"):
        digits = "+" + digits.lstrip("+")
    return digits if _E164.match(digits) else None


# --- argument schemas ---

class CreateLeadArgs(BaseModel):
    business_name: str = Field(min_length=1, max_length=200, description="Person or company name the lead gave")
    contact_name: Optional[str] = Field(default=None, max_length=120)
    contact_whatsapp: Optional[str] = Field(default=None, description="WhatsApp/phone in any format; normalized to E.164")
    contact_email: Optional[str] = Field(default=None, max_length=200)
    description: str = Field(default="", max_length=4000, description="What the bot learned in the chat: needs, context, service of interest")

    @field_validator("contact_whatsapp")
    @classmethod
    def _phone(cls, v):
        return _normalize_phone(v)


class ScheduleMeetingArgs(BaseModel):
    business_name: Optional[str] = Field(default=None, max_length=200)
    description: str = Field(default="", max_length=4000)


class HandoffArgs(BaseModel):
    reason: str = Field(default="", max_length=500, description="Why the user is being handed to a human")


# --- tool implementations (raise on failure; the wrapper handles resilience) ---

async def _notify_team_whatsapp(text: str) -> None:
    """Best-effort WhatsApp notification via Evolution. Never raises — a failed notify
    must not fail the lead."""
    if not (config.EVOLUTION_API_URL and config.EVOLUTION_API_KEY and config.EVOLUTION_INSTANCE and config.MY_WHATSAPP_NUMBER):
        logging.info("WhatsApp notify skipped (Evolution not fully configured)")
        return
    try:
        url = f"{config.EVOLUTION_API_URL.rstrip('/')}/message/sendText/{config.EVOLUTION_INSTANCE}"
        async with httpx.AsyncClient(timeout=6.0) as client:
            await client.post(
                url,
                headers={"apikey": config.EVOLUTION_API_KEY, "Content-Type": "application/json"},
                json={"number": config.MY_WHATSAPP_NUMBER, "text": text},
            )
    except Exception as e:  # noqa: BLE001 — best-effort, log and move on
        logging.warning("WhatsApp notify failed (lead still saved): %s", e)


async def create_lead(args: CreateLeadArgs) -> dict:
    # Anti-spam: cap leads per IP/day. Over the cap we tell the user they're registered
    # (they are, from a prior message) but skip the CRM write + WhatsApp push.
    if not await _lead_quota_ok():
        logging.warning("lead quota exceeded for ip=%s", _client_ip.get())
        return {
            "ok": True,
            "message": "Já registrei seu contato — nosso time vai te procurar! 😊",
            "data": {"skipped": "quota"},
        }

    # Behavioral enrichment (#8b): score the lead by journey depth and fold a compact
    # summary into the description. Kept inside `description` (not new top-level fields) so
    # the CRM contract stays stable. Absent when the frontend sends no behavior.
    behavior = _behavior.get()
    lead_score = behavior_ctx.score_lead(behavior)
    behavior_summary = behavior_ctx.summarize_behavior(behavior)
    description = args.description
    if behavior_summary:
        description = f"{description}\n\n[lead score: {lead_score}/100] {behavior_summary}".strip()

    payload: dict[str, Any] = {
        "businessName": args.business_name,
        "description": description,
        "source": "chatbot",
        "sourceGroup": config.LEAD_SOURCE_GROUP,
        "isProspect": False,
    }
    if args.contact_whatsapp:
        payload["whatsapp"] = args.contact_whatsapp
    if any([args.contact_name, args.contact_whatsapp, args.contact_email]):
        payload["contacts"] = [{
            "name": args.contact_name or args.business_name,
            "whatsapp": args.contact_whatsapp,
            "email": args.contact_email,
            "isPrimary": True,
        }]

    async with httpx.AsyncClient(timeout=config.TOOL_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            f"{config.WBCRM_BASE_URL.rstrip('/')}/leads",
            headers={"Authorization": f"Bearer {config.WBCRM_API_TOKEN}", "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        lead = resp.json()

    # Fire-and-forget so a slow notify can never extend the tool's timed window (which,
    # after a successful POST, could otherwise trigger a retry and a DUPLICATE lead).
    notify = f"🤖 Novo lead do chatbot: {args.business_name}\n{args.description[:300]}"
    if behavior_summary:
        notify += f"\n📊 Lead score: {lead_score}/100 — {behavior_summary}"
    _fire_and_forget(_notify_team_whatsapp(notify))
    return {
        "ok": True,
        "message": "Perfeito, registrei seu contato — nosso time já vai te procurar! 😊",
        "data": {"lead_id": lead.get("id")},
    }


async def schedule_meeting(args: ScheduleMeetingArgs) -> dict:
    # Capture the lead too (best-effort) so we know who is booking, but the link is the point.
    if args.business_name:
        try:
            await create_lead(CreateLeadArgs(business_name=args.business_name, description=f"[quer agendar] {args.description}"))
        except Exception as e:  # noqa: BLE001 — capture is a bonus; never block the link
            logging.warning("schedule_meeting lead capture failed (link still returned): %s", e)
    return {
        "ok": True,
        "message": f"Você pode agendar direto comigo por aqui: {config.BOOKING_URL} 📅",
        "data": {"booking_url": config.BOOKING_URL},
    }


async def handoff_to_human(args: HandoffArgs) -> dict:
    return {
        "ok": True,
        "message": f"Vou te conectar com uma pessoa do nosso time. Fale com a gente no WhatsApp {config.WHATSAPP_CONTACT} — respondemos rápido! 📲",
        "data": {"whatsapp": config.WHATSAPP_CONTACT},
    }


# --- registry + resilient dispatch ---

class _Tool:
    def __init__(self, name: str, description: str, args_model: type[BaseModel],
                 func: Callable[[Any], Awaitable[dict]], retries: Optional[int] = None):
        self.name = name
        self.description = description
        self.args_model = args_model
        self.func = func
        # retries=0 for non-idempotent writes (create_lead, schedule_meeting): retrying a
        # POST that may have already succeeded would create a duplicate lead. None -> config.
        self.retries = retries


_TOOLS: dict[str, _Tool] = {
    t.name: t for t in [
        _Tool("create_lead", "Save the interested person as a lead once they share who they are (name/company) or a contact. Call this to capture a lead.", CreateLeadArgs, create_lead, retries=0),
        _Tool("schedule_meeting", "Give the user the direct link to book a meeting with the team. Call when the user wants to talk, get a proposal, or schedule.", ScheduleMeetingArgs, schedule_meeting, retries=0),
        _Tool("handoff_to_human", "Hand the conversation to a human on WhatsApp. Call when the user explicitly wants a person or the bot can't help.", HandoffArgs, handoff_to_human),
    ]
}


def _fallback(reason: str) -> dict:
    return {
        "ok": False,
        "message": f"Tive um probleminha técnico agora, mas não quero te deixar na mão — fale com a gente no WhatsApp {config.WHATSAPP_CONTACT}! 📲",
        "error": reason,
    }


# OpenAI/DeepSeek function-calling schema, derived from the Pydantic models (single source).
TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.args_model.model_json_schema(),
        },
    }
    for t in _TOOLS.values()
]


async def dispatch(name: str, raw_args: dict) -> dict:
    """
    Validate `raw_args` against the tool's schema and run it with a timeout + bounded retry.
    Any validation error, timeout, or exception degrades to a graceful handoff message
    (ok=False) — the caller can always show `message` to the user.
    """
    tool = _TOOLS.get(name)
    if tool is None:
        logging.error("unknown tool requested: %s", name)
        return _fallback(f"unknown tool: {name}")

    try:
        args = tool.args_model(**(raw_args or {}))
    except Exception as e:  # noqa: BLE001 — hallucinated/invalid args must not crash
        logging.warning("tool %s got invalid args %s: %s", name, guardrails.redact_pii(str(raw_args)), e)
        return _fallback(f"invalid args: {e}")

    retries = tool.retries if tool.retries is not None else config.TOOL_RETRIES
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            return await asyncio.wait_for(tool.func(args), timeout=config.TOOL_TIMEOUT_SECONDS)
        except Exception as e:  # noqa: BLE001 — timeout or downstream error
            last_exc = e
            logging.warning("tool %s attempt %d/%d failed: %s", name, attempt + 1, retries + 1, e)

    return _fallback(str(last_exc))
