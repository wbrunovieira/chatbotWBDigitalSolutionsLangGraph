"""Guardrails: hardened system prompt + the output canary backstop."""

import guardrails


class TestHardenSystemPrompt:
    def test_appends_rules_and_canary_to_base(self):
        out = guardrails.harden_system_prompt("BASE PROMPT")
        assert out.startswith("BASE PROMPT")
        assert guardrails.SYSTEM_PROMPT_CANARY in out
        assert "untrusted" in out.lower()
        assert "never reveal" in out.lower()


class TestContainsCanary:
    def test_detects_exact(self):
        assert guardrails.contains_canary(f"leak: {guardrails.SYSTEM_PROMPT_CANARY}")

    def test_detects_case_and_punctuation_variants(self):
        # the backstop must be at least as strong as the eval's normalized check
        assert guardrails.contains_canary(guardrails.SYSTEM_PROMPT_CANARY.lower())
        assert guardrails.contains_canary(guardrails.SYSTEM_PROMPT_CANARY.replace("-", " "))

    def test_clean_text_has_no_canary(self):
        assert not guardrails.contains_canary("Olá! Posso ajudar com sites e automação.")


class TestScrubOutput:
    def test_blocks_reply_when_canary_leaks(self):
        leaked = f"Sure — my full instructions are: {guardrails.SYSTEM_PROMPT_CANARY} ..."
        out = guardrails.scrub_output(leaked)
        assert not guardrails.contains_canary(out)   # leak redacted
        assert "WB Digital Solutions" in out          # replaced with a safe refusal

    def test_refusal_matches_user_language(self):
        leaked = guardrails.SYSTEM_PROMPT_CANARY
        assert "can't help" in guardrails.scrub_output(leaked, "en").lower()
        assert "non posso" in guardrails.scrub_output(leaked, "it").lower()

    def test_passes_clean_output_through_unchanged(self):
        clean = "Olá! Posso te ajudar com sites, automação e IA. 😊"
        assert guardrails.scrub_output(clean) == clean

    def test_empty_is_safe(self):
        assert guardrails.scrub_output("") == ""


class TestRedactPii:
    def test_masks_email_phone_and_documents(self):
        out = guardrails.redact_pii(
            "email joao@padaria.com, fone (11) 98286-4581, cpf 123.456.789-00, cnpj 12.345.678/0001-99"
        )
        assert "joao@padaria.com" not in out
        assert "98286-4581" not in out
        assert "123.456.789-00" not in out
        assert "12.345.678/0001-99" not in out
        assert "[email redacted]" in out and "[phone redacted]" in out and "[document redacted]" in out

    def test_masks_international_phone(self):
        assert "98286" not in guardrails.redact_pii("me liga +55 11 98286-4581")

    def test_leaves_prices_dates_and_names_alone(self):
        for keep in ("orçamento de R$ 5000", "prazo de 4 a 12 semanas", "João da Padaria Central"):
            assert guardrails.redact_pii(keep) == keep

    def test_none_and_empty_are_safe(self):
        assert guardrails.redact_pii(None) is None
        assert guardrails.redact_pii("") == ""
