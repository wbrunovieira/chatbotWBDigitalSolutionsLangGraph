"""
Conversion-funnel analytics from chat_logs (#24).

Langfuse is disabled in production (no creds), so the funnel is derived from the Qdrant
chat_logs collection instead — each turn stores its intent, the tools that fired (with ok),
the user_id and a timestamp. From that we reconstruct the sales funnel:

    greeting  ->  question  ->  lead captured

Turn-level counts (by intent, total leads) are exact. The user-level funnel is best-effort:
anonymous visitors all share the "anon" id (no stable per-session id yet — see the frontend
session-id follow-up), so they collapse into one bucket; the funnel is meaningful for
identified users. Operator-only (see require_admin).
"""

import os
import time
from collections import defaultdict

from qdrant_client.http.models import FieldCondition, Filter, Range

# Intents that count as a real product question (not a greeting / off-topic / handoff).
QUESTION_INTENTS = {"inquire_services", "request_quote", "share_contact"}
# Tools whose successful call means a lead was captured / a meeting offered.
LEAD_TOOLS = {"create_lead", "schedule_meeting"}
# Hard cap on how many points a single funnel query scans, so it stays bounded in memory +
# latency even if chat_logs grows unexpectedly large (retention should keep it small, but
# this endpoint must never turn into a slow, unbounded scan). Env-tunable.
MAX_FUNNEL_SCAN = int(os.getenv("ANALYTICS_MAX_SCAN", "50000"))


def _scan_chat_logs(client, since_ts):
    """Page through chat_logs payloads (optionally newer than since_ts), capped at
    MAX_FUNNEL_SCAN points."""
    scroll_filter = None
    if since_ts is not None:
        scroll_filter = Filter(must=[FieldCondition(key="timestamp", range=Range(gte=since_ts))])
    payloads, offset = [], None
    while len(payloads) < MAX_FUNNEL_SCAN:
        batch, offset = client.scroll(
            collection_name="chat_logs",
            scroll_filter=scroll_filter,
            with_payload=True,
            with_vectors=False,
            limit=256,
            offset=offset,
        )
        payloads.extend(p.payload or {} for p in batch)
        if offset is None:
            break
    return payloads[:MAX_FUNNEL_SCAN]


def conversion_funnel(client, window_days: int | None = 30) -> dict:
    """Greeting -> question -> lead funnel over the last `window_days` (None = all time)."""
    since_ts = int(time.time()) - window_days * 86400 if window_days else None
    payloads = _scan_chat_logs(client, since_ts)

    by_intent = defaultdict(int)
    users_greeted, users_asked, users_lead, all_users = set(), set(), set(), set()
    leads_total = 0

    for p in payloads:
        user_id = p.get("user_id")
        intent = p.get("intent") or "unknown"
        by_intent[intent] += 1
        all_users.add(user_id)
        if intent == "greeting":
            users_greeted.add(user_id)
        if intent in QUESTION_INTENTS:
            users_asked.add(user_id)
        for tool in (p.get("tools_used") or []):
            if tool.get("tool") in LEAD_TOOLS and tool.get("ok"):
                leads_total += 1
                users_lead.add(user_id)

    asked = len(users_asked)
    captured = len(users_lead)
    return {
        "window_days": window_days,
        "total_turns": len(payloads),
        "unique_users": len(all_users),
        "by_intent": dict(sorted(by_intent.items(), key=lambda kv: -kv[1])),
        "funnel_users": {
            "greeted": len(users_greeted),
            "asked_question": asked,
            "lead_captured": captured,
        },
        "leads_captured_total": leads_total,
        "question_to_lead_rate": round(captured / asked, 3) if asked else 0.0,
        "note": "user-level funnel collapses anonymous visitors (shared 'anon' id); "
                "turn counts and leads_captured_total are exact.",
    }
