"""Agent tools: validation, resilience (timeout/retry/fallback), and the CRM call."""

import asyncio

import httpx
import pytest

import config
import tools


class FakeResponse:
    def __init__(self, status=200, json_data=None):
        self.status_code = status
        self._json = json_data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json


class FakeAsyncClient:
    """Records POSTs and returns canned responses. Configured per test via `install`."""

    calls: list = []
    response = FakeResponse(200, {"id": "lead-123"})
    raise_exc = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kwargs):
        FakeAsyncClient.calls.append({"url": url, **kwargs})
        if FakeAsyncClient.raise_exc:
            raise FakeAsyncClient.raise_exc
        return FakeAsyncClient.response


@pytest.fixture
def fake_http(monkeypatch, redis_fake):  # redis_fake: create_lead's per-IP quota uses Redis
    FakeAsyncClient.calls = []
    FakeAsyncClient.response = FakeResponse(200, {"id": "lead-123"})
    FakeAsyncClient.raise_exc = None
    monkeypatch.setattr(tools.httpx, "AsyncClient", FakeAsyncClient)
    # deterministic tool config
    monkeypatch.setattr(config, "WBCRM_BASE_URL", "http://crm.test:3010")
    monkeypatch.setattr(config, "WBCRM_API_TOKEN", "tok")
    monkeypatch.setattr(config, "LEAD_SOURCE_GROUP", "bot-test")
    monkeypatch.setattr(config, "TOOL_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(config, "TOOL_RETRIES", 1)
    # Evolution unset -> notify is a no-op
    for k in ("EVOLUTION_API_URL", "EVOLUTION_API_KEY", "EVOLUTION_INSTANCE", "MY_WHATSAPP_NUMBER"):
        monkeypatch.setattr(config, k, "")
    return FakeAsyncClient


class TestCreateLead:
    async def test_posts_to_crm_and_returns_ok(self, fake_http):
        res = await tools.dispatch("create_lead", {"business_name": "Padaria do Zé", "description": "quer um site"})
        assert res["ok"] is True
        assert res["data"]["lead_id"] == "lead-123"
        call = fake_http.calls[0]
        assert call["url"] == "http://crm.test:3010/leads"
        assert call["headers"]["Authorization"] == "Bearer tok"
        body = call["json"]
        assert body["businessName"] == "Padaria do Zé"
        assert body["isProspect"] is False
        assert body["sourceGroup"] == "bot-test"
        assert body["source"] == "chatbot"

    async def test_normalizes_phone_to_e164(self, fake_http):
        await tools.dispatch("create_lead", {"business_name": "Zé", "contact_whatsapp": "+55 (24) 99999-0000"})
        body = fake_http.calls[0]["json"]
        assert body["whatsapp"] == "+5524999990000"

    async def test_lead_still_saved_when_whatsapp_notify_unconfigured(self, fake_http):
        # Evolution env is unset in the fixture; create_lead must still succeed.
        res = await tools.dispatch("create_lead", {"business_name": "X"})
        assert res["ok"] is True


class TestValidation:
    async def test_missing_required_arg_falls_back_gracefully(self, fake_http):
        res = await tools.dispatch("create_lead", {})  # business_name required
        assert res["ok"] is False
        assert config.WHATSAPP_CONTACT in res["message"]  # graceful handoff
        assert fake_http.calls == []  # never hit the CRM with bad args

    async def test_unknown_tool_falls_back(self, fake_http):
        res = await tools.dispatch("delete_everything", {"x": 1})
        assert res["ok"] is False


class TestResilience:
    async def test_crm_error_falls_back(self, fake_http):
        fake_http.raise_exc = httpx.ConnectError("crm down")
        res = await tools.dispatch("create_lead", {"business_name": "X"})
        assert res["ok"] is False
        assert "error" in res

    async def test_timeout_falls_back(self, fake_http, monkeypatch):
        monkeypatch.setattr(config, "TOOL_TIMEOUT_SECONDS", 0.05)

        async def slow(_args):
            await asyncio.sleep(1)

        monkeypatch.setattr(tools._TOOLS["create_lead"], "func", slow)
        res = await tools.dispatch("create_lead", {"business_name": "X"})
        assert res["ok"] is False

    async def test_writes_do_not_retry(self, fake_http, monkeypatch):
        # create_lead is a non-idempotent write -> retries=0. A transient failure must NOT
        # be retried (that would risk a duplicate lead); it degrades gracefully instead.
        attempts = {"n": 0}

        async def flaky(_args):
            attempts["n"] += 1
            raise httpx.ConnectError("transient")

        monkeypatch.setattr(tools._TOOLS["create_lead"], "func", flaky)
        res = await tools.dispatch("create_lead", {"business_name": "X"})
        assert res["ok"] is False
        assert attempts["n"] == 1  # exactly one attempt, no retry

    async def test_retryable_tool_retries_then_succeeds(self, fake_http, monkeypatch):
        # An idempotent tool (handoff) uses the default retry policy (config.TOOL_RETRIES).
        monkeypatch.setattr(config, "TOOL_RETRIES", 1)
        attempts = {"n": 0}

        async def flaky(_args):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise httpx.ConnectError("transient")
            return {"ok": True, "message": "ok"}

        monkeypatch.setattr(tools._TOOLS["handoff_to_human"], "func", flaky)
        res = await tools.dispatch("handoff_to_human", {})
        assert res["ok"] is True
        assert attempts["n"] == 2


class TestOtherTools:
    async def test_schedule_meeting_returns_booking_link(self, fake_http, monkeypatch):
        monkeypatch.setattr(config, "BOOKING_URL", "https://agenda.test/book")
        res = await tools.dispatch("schedule_meeting", {"business_name": "Zé", "description": "quer conversar"})
        assert res["ok"] is True
        assert "https://agenda.test/book" in res["message"]

    async def test_handoff_returns_whatsapp(self, fake_http):
        res = await tools.dispatch("handoff_to_human", {"reason": "wants a person"})
        assert res["ok"] is True
        assert config.WHATSAPP_CONTACT in res["message"]


class TestLeadQuota:
    async def test_over_daily_cap_skips_crm_and_notify(self, fake_http, monkeypatch):
        monkeypatch.setattr(config, "MAX_LEADS_PER_IP_PER_DAY", 2)
        tools.set_client_ip("9.9.9.9")

        for _ in range(2):  # first two create real leads
            r = await tools.dispatch("create_lead", {"business_name": "X"})
            assert r["ok"] is True and r["data"].get("skipped") != "quota"

        posts_before = len(fake_http.calls)
        r = await tools.dispatch("create_lead", {"business_name": "X"})  # third is over the cap
        assert r["ok"] is True
        assert r["data"].get("skipped") == "quota"
        assert len(fake_http.calls) == posts_before  # no new CRM POST


class TestToolSpecs:
    def test_specs_are_wellformed_for_function_calling(self):
        names = {s["function"]["name"] for s in tools.TOOL_SPECS}
        assert names == {"create_lead", "schedule_meeting", "handoff_to_human"}
        for spec in tools.TOOL_SPECS:
            assert spec["type"] == "function"
            fn = spec["function"]
            assert fn["description"]
            assert fn["parameters"]["type"] == "object"
