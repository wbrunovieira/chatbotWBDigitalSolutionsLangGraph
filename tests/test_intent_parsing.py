"""Robustness of intent parsing (the deterministic core of detect_intent)."""

import json
from pathlib import Path

import pytest

from nodes import DEFAULT_INTENT, VALID_INTENTS, parse_intent


class TestParseIntent:
    @pytest.mark.parametrize("intent", VALID_INTENTS)
    def test_json_object_round_trips_every_intent(self, intent):
        assert parse_intent(json.dumps({"intent": intent})) == intent

    @pytest.mark.parametrize("intent", VALID_INTENTS)
    def test_bare_word_round_trips(self, intent):
        assert parse_intent(intent) == intent

    def test_scans_any_json_key_not_just_intent(self):
        # If the model drifts and uses a different key, still recover the value.
        assert parse_intent('{"result": "greeting"}') == "greeting"

    def test_space_or_hyphen_variants_match(self):
        assert parse_intent("off topic") == "off_topic"
        assert parse_intent("off-topic") == "off_topic"

    def test_extracts_from_messy_prose(self):
        assert parse_intent("The intent is inquire_services.") == "inquire_services"

    def test_case_insensitive(self):
        assert parse_intent('{"intent": "GREETING"}') == "greeting"

    def test_surrounding_whitespace(self):
        assert parse_intent('\n  {"intent": "request_quote"}  \n') == "request_quote"

    def test_explicit_off_topic_intent_is_respected(self):
        # An explicit classification is trusted — a word in the reasoning must NOT
        # override it. (Fixing "boa tarde" is the prompt's job, not the parser's.)
        assert parse_intent('{"intent": "off_topic", "reason": "mentions services"}') == "off_topic"

    def test_free_text_scan_prefers_service_over_off_topic(self):
        # In the greedy fallback (no valid JSON intent value), a service word beats
        # off_topic thanks to the off_topic-last ordering — never deflect on ambiguity.
        assert parse_intent("looks off_topic but is really inquire_services") == "inquire_services"

    def test_empty_defaults_to_service_not_off_topic(self):
        assert parse_intent("") == DEFAULT_INTENT
        assert DEFAULT_INTENT == "inquire_services"

    def test_garbage_defaults_to_service(self):
        assert parse_intent("asdfghjkl") == DEFAULT_INTENT

    def test_none_is_handled(self):
        assert parse_intent(None) == DEFAULT_INTENT


class TestEvalDatasetSanity:
    """The eval dataset must be well-formed and use only known labels."""

    def _load(self):
        path = Path(__file__).resolve().parent.parent / "evals" / "intents.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return rows

    def test_dataset_is_nonempty_and_well_formed(self):
        rows = self._load()
        assert len(rows) >= 20
        for r in rows:
            assert r["message"] and isinstance(r["message"], str)
            assert r["expected"] in VALID_INTENTS

    def test_covers_the_real_production_failures(self):
        rows = self._load()
        msgs = {r["message"].lower() for r in rows}
        assert "boa tarde" in msgs
        assert "vcs fazem automassao?" in msgs

    def test_expected_labels_round_trip_through_the_parser(self):
        # Every gold label, wrapped as the model is asked to return it, parses back.
        for r in self._load():
            assert parse_intent(json.dumps({"intent": r["expected"]})) == r["expected"]


class TestReasoningFieldDoesNotHijack:
    """A word inside a reasoning field must not override the explicit intent value."""

    def test_greeting_in_reason_does_not_win(self):
        raw = '{"intent": "request_quote", "reason": "not just a greeting, wants price"}'
        assert parse_intent(raw) == "request_quote"

    def test_service_in_reason_does_not_win(self):
        raw = '{"intent": "share_contact", "reason": "asked after an inquire_services question"}'
        assert parse_intent(raw) == "share_contact"


class TestPromptsRequestJson:
    """
    Every detect_intent prompt the code can send must contain 'json' — DeepSeek's
    json_object mode 400s without it. This guards the blocker where the local fallback
    still used the old one-word prompt.
    """

    def test_local_fallback_prompt_is_json_and_compiles(self):
        from observability.langfuse_client import LOCAL_PROMPTS, LocalPrompt

        tmpl = LOCAL_PROMPTS["detect_intent"]
        compiled = LocalPrompt("detect_intent", tmpl["template"], tmpl["type"]).compile(
            user_input="boa tarde"
        )
        assert "boa tarde" in compiled          # {{user_input}} substituted (mustache)
        assert '{"intent"' in compiled          # literal JSON object preserved
        assert "json" in compiled.lower()       # json_object mode requirement

    def test_langfuse_source_prompt_is_json(self):
        from observability.langfuse_prompts_v3 import PROMPTS_V3

        assert "json" in PROMPTS_V3["detect_intent"]["prompt"].lower()
