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
            "generate_response_system",
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
    def test_contact_response_still_provides_whatsapp(self):
        # When the user explicitly asks for contact (share_contact intent), we DO give it.
        assert "{{whatsapp}}" in _template("generate_contact_response")
