"""Conversion-funnel analytics from chat_logs (#24)."""

from types import SimpleNamespace

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from observability import analytics
from rag import db
import main


class FakeQdrant:
    """Serves a fixed set of chat_logs payloads through scroll() in one page."""

    def __init__(self, payloads):
        self._points = [SimpleNamespace(payload=p) for p in payloads]

    def scroll(self, collection_name, scroll_filter=None, with_payload=True,
               with_vectors=False, limit=256, offset=None):
        assert collection_name == "chat_logs"
        return self._points, None  # single page, no next offset


def _logs():
    return [
        {"user_id": "u1", "intent": "greeting", "tools_used": []},
        {"user_id": "u1", "intent": "inquire_services", "tools_used": []},
        {"user_id": "u1", "intent": "share_contact",
         "tools_used": [{"tool": "create_lead", "ok": True}]},
        {"user_id": "u2", "intent": "request_quote", "tools_used": []},
        {"user_id": "u2", "intent": "request_quote",
         "tools_used": [{"tool": "schedule_meeting", "ok": True}]},
        {"user_id": "u3", "intent": "off_topic", "tools_used": []},
        # a failed tool call must NOT count as a captured lead
        {"user_id": "u4", "intent": "inquire_services",
         "tools_used": [{"tool": "create_lead", "ok": False}]},
    ]


class TestConversionFunnel:
    def test_counts_intents_and_leads(self):
        out = analytics.conversion_funnel(FakeQdrant(_logs()), window_days=30)
        assert out["total_turns"] == 7
        assert out["unique_users"] == 4
        assert out["by_intent"]["request_quote"] == 2
        # u1 (create_lead ok) + u2 (schedule_meeting ok); u4's failed call doesn't count
        assert out["leads_captured_total"] == 2
        assert out["funnel_users"]["lead_captured"] == 2

    def test_funnel_stages_are_user_deduped(self):
        out = analytics.conversion_funnel(FakeQdrant(_logs()), window_days=30)
        assert out["funnel_users"]["greeted"] == 1          # only u1 greeted
        assert out["funnel_users"]["asked_question"] == 3   # u1, u2, u4 asked
        assert out["question_to_lead_rate"] == round(2 / 3, 3)

    def test_empty_logs_are_safe(self):
        out = analytics.conversion_funnel(FakeQdrant([]), window_days=7)
        assert out["total_turns"] == 0
        assert out["question_to_lead_rate"] == 0.0
        assert out["funnel_users"]["lead_captured"] == 0

    def test_scan_is_capped(self, monkeypatch):
        # A huge collection must not be scanned unbounded — the cap bounds memory + latency.
        monkeypatch.setattr(analytics, "MAX_FUNNEL_SCAN", 3)

        class Paged:
            def scroll(self, collection_name, scroll_filter=None, offset=None, **kw):
                # always returns a full page + a next offset (i.e. "infinite" collection)
                pts = [SimpleNamespace(payload={"user_id": "u", "intent": "greeting", "tools_used": []})
                       for _ in range(256)]
                return pts, "next"

        out = analytics.conversion_funnel(Paged(), window_days=None)
        assert out["total_turns"] == 3  # stopped at the cap, did not loop forever

    def test_window_none_scans_all_time(self):
        # window_days=None must not build a timestamp filter (scroll_filter stays None)
        seen = {}

        class Recorder(FakeQdrant):
            def scroll(self, collection_name, scroll_filter=None, **kw):
                seen["filter"] = scroll_filter
                return [], None

        analytics.conversion_funnel(Recorder([]), window_days=None)
        assert seen["filter"] is None


class TestFunnelEndpoint:
    async def test_admin_only_and_returns_funnel(self, redis_fake, limits):
        db.set_qdrant_client(FakeQdrant(_logs()))
        transport = ASGITransport(app=main.app)
        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as c:
                assert (await c.get("/analytics/funnel")).status_code == 401  # no token
                ok = await c.get("/analytics/funnel",
                                 headers={"Authorization": "Bearer test-admin-token"})
                assert ok.status_code == 200
                body = ok.json()
                assert body["leads_captured_total"] == 2 and "funnel_users" in body
        finally:
            db.set_qdrant_client(None)
