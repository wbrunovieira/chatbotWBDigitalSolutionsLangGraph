"""The opening greeting is hardcoded (no LLM), engages, and never dumps contact (#330/#342)."""

import re

import nodes


def _no_http(*args, **kwargs):
    raise AssertionError("greeting must not call the LLM")


class TestHardcodedGreetings:
    def test_all_languages_have_no_contact_and_a_question(self):
        for lang, text in nodes.GREETINGS.items():
            assert "whatsapp" not in text.lower(), lang
            assert not re.search(r"\d{4,}", text), lang   # no phone number
            assert "?" in text, lang                       # ends on a qualifying question

    async def test_returns_language_greeting_without_calling_llm(self, monkeypatch):
        # If the greeting touched the LLM, this patched client would raise.
        monkeypatch.setattr(nodes.deepseek_client, "chat_completion", _no_http)
        out = await nodes.generate_greeting_response({"language": "en"})
        assert out["response"] == nodes.GREETINGS["en"]
        assert out["revised_response"] == nodes.GREETINGS["en"]
        assert out["step"] == "generate_greeting_response"

    async def test_unknown_missing_or_null_language_falls_back_to_pt(self):
        assert (await nodes.generate_greeting_response({"language": "fr"}))["response"] == nodes.GREETINGS["pt-BR"]
        assert (await nodes.generate_greeting_response({}))["response"] == nodes.GREETINGS["pt-BR"]
        assert (await nodes.generate_greeting_response({"language": None}))["response"] == nodes.GREETINGS["pt-BR"]


class TestGreetingBubbleSplit:
    def test_keeps_question_mark_and_avoids_stray_dot(self):
        import main

        parts = main.split_greeting_bubbles(nodes.GREETINGS["pt-BR"])
        assert parts[-1].endswith("?")
        assert not any(p.endswith("?.") or p.endswith("..") for p in parts)
