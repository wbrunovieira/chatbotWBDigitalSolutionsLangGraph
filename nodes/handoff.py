"""Deterministic (no-LLM) human-handoff response for the chat_with_agent intent.

Previously chat_with_agent routed straight to END with no backend response, delegating the
handoff entirely to the frontend — so if the widget didn't render a handoff UI, a user asking
to talk to a person got empty text (and the widget re-showed the last bubble). This node
returns a graceful handoff message pointing to WhatsApp, so the user is never left with
nothing. Hardcoded per language (like greetings) — no LLM call.
"""

import config

HANDOFFS = {
    "pt-BR": "Claro! Vou te conectar com uma pessoa do nosso time. Fale com a gente no WhatsApp {contact} — respondemos rápido! 📲",
    "en": "Of course! Let me connect you with someone from our team. Reach us on WhatsApp {contact} — we reply fast! 📲",
    "es": "¡Claro! Te conecto con alguien de nuestro equipo. Escríbenos por WhatsApp {contact} — ¡respondemos rápido! 📲",
    "it": "Certo! Ti metto in contatto con una persona del nostro team. Scrivici su WhatsApp {contact} — rispondiamo subito! 📲",
}


async def generate_handoff_response(state: dict) -> dict:
    """Return a deterministic human-handoff message — no LLM call."""
    language = state.get("language") or "pt-BR"
    template = HANDOFFS.get(language, HANDOFFS["pt-BR"])
    response = template.format(contact=config.WHATSAPP_CONTACT)
    return {
        **state,
        "response": response,
        "revised_response": response,
        "step": "generate_handoff_response",
    }
