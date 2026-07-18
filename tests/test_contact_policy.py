"""WhatsApp is surfaced by trigger (contact asked / handoff), not forced on every answer (#331)."""

from langfuse_prompts_v3 import PROMPTS_V3


def _template(name):
    p = PROMPTS_V3[name]["prompt"]
    return p if isinstance(p, str) else " ".join(m["content"] for m in p)


class TestContactNotForced:
    # Prompts that drive normal service/info answers must not auto-inject contact anymore.
    def test_generation_and_revision_prompts_do_not_force_contact(self):
        for name in (
            "generate_services_response",
            "generate_response_instruction",
            "revise_response",
        ):
            t = _template(name)
            assert "{{whatsapp}}" not in t, f"{name} still injects the WhatsApp template var"
            assert "respondemos em até" not in t.lower(), f"{name} still hardcodes the SLA"
            assert "always include whatsapp" not in t.lower(), f"{name} still forces contact"
            assert "always end with whatsapp" not in t.lower(), f"{name} still forces contact"

    def test_revise_does_not_add_missing_contact(self):
        t = _template("revise_response").lower()
        assert "do not add" in t and "phone number or whatsapp" in t


class TestContactStillAvailableOnTrigger:
    def test_handoff_prompt_routes_contact_and_whatsapp_asks(self):
        # A user asking for our contact / WhatsApp is routed to handoff_to_human, which
        # surfaces the real number (that live path is covered in test_tools.py). Assert on the
        # LIVE system prompt, not the dead generate_contact_response prompt.
        import nodes

        sp = nodes.TOOL_SYSTEM_PROMPT.lower()
        assert "handoff_to_human" in sp
        assert "whatsapp" in sp and "contact" in sp
