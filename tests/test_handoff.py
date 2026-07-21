"""chat_with_agent now returns a deterministic WhatsApp handoff (not an empty END)."""

import config
import nodes
from graph_config import route_after_intent


class TestGenerateHandoff:
    async def test_returns_whatsapp_handoff_per_language(self):
        out = await nodes.generate_handoff_response({"language": "en"})
        assert config.WHATSAPP_CONTACT in out["response"]
        assert "WhatsApp" in out["response"]
        assert out["revised_response"] == out["response"]
        assert out["step"] == "generate_handoff_response"

    async def test_unknown_or_missing_language_falls_back_to_pt(self):
        pt = (await nodes.generate_handoff_response({"language": "pt-BR"}))["response"]
        assert (await nodes.generate_handoff_response({"language": "xx"}))["response"] == pt
        assert (await nodes.generate_handoff_response({}))["response"] == pt

    async def test_never_empty(self):
        for lang in ("pt-BR", "en", "es", "it"):
            assert (await nodes.generate_handoff_response({"language": lang}))["response"].strip()


class TestRouting:
    def test_chat_with_agent_routes_to_handoff_not_end(self):
        # Regression: chat_with_agent used to return END (empty response).
        assert route_after_intent({"intent": "chat_with_agent"}) == "generate_handoff_response"

    def test_other_intents_unchanged(self):
        assert route_after_intent({"intent": "greeting"}) == "generate_greeting_response"
        assert route_after_intent({"intent": "off_topic"}) == "generate_off_topic_response"
        assert route_after_intent({"intent": "inquire_services"}) == "retrieve_company_context"
