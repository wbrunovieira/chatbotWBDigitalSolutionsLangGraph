"""LLM routing + provider fallback (#13)."""

import httpx
import pytest

import config
from providers import llm


class FakeResp:
    def __init__(self, status=200):
        self.status_code = status


@pytest.fixture
def routed(monkeypatch):
    """Record calls to the underlying transport and return a canned response."""
    calls = []

    async def fake_cc(messages, **kwargs):
        calls.append(kwargs)
        return FakeResp(kwargs.pop("_status", 200))

    monkeypatch.setattr(llm.deepseek_client, "chat_completion", fake_cc)
    monkeypatch.setattr(config, "DEEPSEEK_MODEL", "primary-model")
    monkeypatch.setattr(config, "INTENT_MODEL", "cheap-intent")
    monkeypatch.setattr(config, "GENERATION_MODEL", "strong-gen")
    # no fallback by default
    monkeypatch.setattr(config, "FALLBACK_API_URL", "")
    monkeypatch.setattr(config, "FALLBACK_API_KEY", "")
    monkeypatch.setattr(config, "FALLBACK_MODEL", "")
    return calls


def _enable_fallback(monkeypatch):
    monkeypatch.setattr(config, "FALLBACK_API_URL", "https://fallback.test/v1/chat")
    monkeypatch.setattr(config, "FALLBACK_API_KEY", "fk")
    monkeypatch.setattr(config, "FALLBACK_MODEL", "backup-model")


class TestModelRouting:
    def test_model_for_task(self, routed):
        assert llm.model_for("intent") == "cheap-intent"
        assert llm.model_for("generation") == "strong-gen"
        assert llm.model_for("revision") == "strong-gen"
        assert llm.model_for("unknown") == "primary-model"  # -> DEEPSEEK_MODEL

    async def test_intent_task_uses_cheap_model(self, routed):
        await llm.chat_completion([{"role": "user", "content": "hi"}], task="intent")
        assert routed[0]["model"] == "cheap-intent"

    async def test_generation_task_uses_strong_model(self, routed):
        await llm.chat_completion([{"role": "user", "content": "hi"}], task="generation")
        assert routed[0]["model"] == "strong-gen"

    async def test_explicit_model_overrides_task(self, routed):
        await llm.chat_completion([], task="intent", model="forced")
        assert routed[0]["model"] == "forced"


class TestFallback:
    async def test_no_fallback_configured_propagates_error(self, routed, monkeypatch):
        async def boom(messages, **kwargs):
            raise httpx.ConnectError("primary down")

        monkeypatch.setattr(llm.deepseek_client, "chat_completion", boom)
        with pytest.raises(httpx.ConnectError):
            await llm.chat_completion([], task="generation")

    async def test_transport_error_fails_over_to_secondary(self, monkeypatch):
        _enable_fallback(monkeypatch)
        monkeypatch.setattr(config, "GENERATION_MODEL", "strong-gen")
        calls = []

        async def fake_cc(messages, **kwargs):
            calls.append(kwargs)
            if kwargs.get("model") == "strong-gen":  # primary
                raise httpx.ReadTimeout("slow")
            return FakeResp(200)  # secondary

        monkeypatch.setattr(llm.deepseek_client, "chat_completion", fake_cc)
        resp = await llm.chat_completion([], task="generation")
        assert resp.status_code == 200
        assert calls[-1]["model"] == "backup-model"
        assert calls[-1]["api_url"] == "https://fallback.test/v1/chat"
        assert calls[-1]["api_key"] == "fk"

    async def test_5xx_fails_over_to_secondary(self, monkeypatch):
        _enable_fallback(monkeypatch)
        calls = []

        async def fake_cc(messages, **kwargs):
            calls.append(kwargs)
            if "api_url" not in kwargs:  # primary
                return FakeResp(503)
            return FakeResp(200)  # secondary

        monkeypatch.setattr(llm.deepseek_client, "chat_completion", fake_cc)
        resp = await llm.chat_completion([], task="generation")
        assert resp.status_code == 200
        assert calls[-1]["model"] == "backup-model"

    @pytest.mark.parametrize("status", [402, 429, 500, 503])
    async def test_unavailable_statuses_fail_over(self, monkeypatch, status):
        """402 (out of credit), 429 (throttled) and 5xx all mean 'try the secondary'."""
        _enable_fallback(monkeypatch)
        calls = []

        async def fake_cc(messages, **kwargs):
            calls.append(kwargs)
            if "api_url" not in kwargs:  # primary
                return FakeResp(status)
            return FakeResp(200)  # secondary

        monkeypatch.setattr(llm.deepseek_client, "chat_completion", fake_cc)
        resp = await llm.chat_completion([], task="generation")
        assert resp.status_code == 200
        assert calls[-1]["model"] == "backup-model"

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
    async def test_client_error_statuses_do_not_fail_over(self, monkeypatch, status):
        """A 4xx that's our fault (bad request/key/model) must surface, not replay on secondary."""
        _enable_fallback(monkeypatch)
        calls = []

        async def fake_cc(messages, **kwargs):
            calls.append(kwargs)
            return FakeResp(status)

        monkeypatch.setattr(llm.deepseek_client, "chat_completion", fake_cc)
        resp = await llm.chat_completion([], task="generation")
        assert resp.status_code == status
        assert len(calls) == 1  # primary only, no failover

    async def test_success_does_not_call_fallback(self, monkeypatch):
        _enable_fallback(monkeypatch)
        calls = []

        async def fake_cc(messages, **kwargs):
            calls.append(kwargs)
            return FakeResp(200)

        monkeypatch.setattr(llm.deepseek_client, "chat_completion", fake_cc)
        await llm.chat_completion([], task="generation")
        assert len(calls) == 1  # primary only
        assert "api_url" not in calls[0]
