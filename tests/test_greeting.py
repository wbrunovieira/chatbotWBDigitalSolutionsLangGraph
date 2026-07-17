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

    def test_rendered_greeting_prompt_has_no_forced_contact(self):
        # Guard the prod chain (LOCAL_PROMPTS, derived from PROMPTS_V3) against re-introducing
        # a hardcoded contact/SLA. Asserts on the RENDERED prompt, not fragile instruction prose.
        from langfuse_client import LOCAL_PROMPTS

        template = LOCAL_PROMPTS["generate_greeting"]["template"]
        assert "{{whatsapp}}" not in template            # no contact template variable
        assert not re.search(r"\d{4,}", template)        # no hardcoded phone number
        assert "respondemos em até" not in template.lower()  # no SLA promise


class TestGreetingBubbleSplit:
    def test_keeps_question_mark_and_avoids_stray_dot(self):
        import main

        parts = main.split_greeting_bubbles(
            "Olá! Somos a WB Digital Solutions. Você quer um site, automação ou IA?"
        )
        assert parts[-1].endswith("?")
        assert not any(p.endswith("?.") or p.endswith("..") for p in parts)
        # "WB Digital Solutions." is not mis-split into its own tiny bubble mid-name
        assert any("WB Digital Solutions." in p for p in parts)
