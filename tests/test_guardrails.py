"""Guardrails: hardened system prompt + the output canary backstop."""

import guardrails


class TestHardenSystemPrompt:
    def test_appends_rules_and_canary_to_base(self):
        out = guardrails.harden_system_prompt("BASE PROMPT")
        assert out.startswith("BASE PROMPT")
        assert guardrails.SYSTEM_PROMPT_CANARY in out
        assert "untrusted" in out.lower()
        assert "never reveal" in out.lower()


class TestScrubOutput:
    def test_blocks_reply_when_canary_leaks(self):
        leaked = f"Sure — my full instructions are: {guardrails.SYSTEM_PROMPT_CANARY} ..."
        out = guardrails.scrub_output(leaked)
        assert guardrails.SYSTEM_PROMPT_CANARY not in out  # leak redacted
        assert "WB Digital Solutions" in out               # replaced with a safe refusal

    def test_passes_clean_output_through_unchanged(self):
        clean = "Olá! Posso te ajudar com sites, automação e IA. 😊"
        assert guardrails.scrub_output(clean) == clean

    def test_empty_is_safe(self):
        assert guardrails.scrub_output("") == ""
