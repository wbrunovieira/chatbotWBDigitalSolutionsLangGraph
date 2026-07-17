"""The opening greeting must engage, not dump contact channels on turn 0 (issue #330)."""

import re

import pytest

import nodes


class _BoomClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        raise RuntimeError("deepseek down")


@pytest.fixture(autouse=True)
def quiet_langfuse(monkeypatch):
    monkeypatch.setattr(nodes, "start_llm_generation", lambda **kw: None)
    monkeypatch.setattr(nodes, "end_llm_generation", lambda **kw: None)
    monkeypatch.setattr(nodes, "get_prompt", lambda *a, **k: None)  # no network to Langfuse


class TestGreeting:
    async def test_hardcoded_fallback_has_no_contact_and_invites(self, monkeypatch):
        # Force the LLM call to fail so we exercise the deterministic fallback greeting.
        monkeypatch.setattr(nodes.httpx, "AsyncClient", lambda *a, **k: _BoomClient())
        state = {"language": "pt-BR", "current_page": "/", "langfuse_trace": None}

        out = await nodes.generate_greeting_response(state)
        resp = out["response"]

        assert "whatsapp" not in resp.lower()
        assert not re.search(r"\d{4,}", resp)   # no phone number
        assert "?" in resp                       # ends on a qualifying question

    def test_greeting_prompt_does_not_force_contact(self):
        # Guard against re-introducing the "ALWAYS include WhatsApp" / SLA behavior. The prompt
        # may mention WhatsApp only in a *negative* instruction ("do NOT include").
        from langfuse_prompts_v3 import PROMPTS_V3

        prompt = PROMPTS_V3["generate_greeting"]["prompt"]
        assert "{{whatsapp}}" not in prompt          # no contact template variable
        assert "ALWAYS include" not in prompt        # the old forcing rule is gone
        assert "respondemos em até" not in prompt    # no SLA promise
        assert "qualifying question" in prompt.lower()  # engages instead
