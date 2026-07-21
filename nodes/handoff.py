"""Deterministic (no-LLM) capture-first handoff for the chat_with_agent intent.

When the user wants to talk to a person, offer the three contact surfaces — but LEAD WITH
LEAD CAPTURE: WhatsApp and the booking link both depend on the lead taking action (and many
don't → the lead escapes). So the easiest, transparent option is to leave their name + a
contact, which we pass straight to Bruno/the team who reaches out; the booking link and
WhatsApp are offered as alternatives for those who prefer autonomy or immediacy. When the
user then shares their details, the normal flow captures the lead via create_lead.

Hardcoded per language (like greetings) — no LLM call. {booking}/{contact} are filled from
config (BOOKING_URL / WHATSAPP_CONTACT).
"""

import config

HANDOFFS = {
    "pt-BR": (
        "Perfeito! 😊 O jeito mais rápido pra você: me diz seu nome e WhatsApp (ou email) que "
        "eu já encaminho pro Bruno — ele te procura pra entender suas ideias. (seus dados "
        "vão pro nosso time entrar em contato)\n\n"
        "Se preferir, dá pra agendar uma conversa aqui: {booking}, ou falar com o Bruno agora "
        "no WhatsApp {contact}."
    ),
    "en": (
        "Perfect! 😊 The quickest way for you: just share your name and WhatsApp (or email) and "
        "I'll pass it straight to our team — they'll reach out to hear your ideas. (your details "
        "go to our team so they can contact you)\n\n"
        "If you prefer, you can book a call here: {booking}, or message us now on WhatsApp {contact}."
    ),
    "es": (
        "¡Perfecto! 😊 Lo más rápido para ti: dime tu nombre y WhatsApp (o email) y lo paso "
        "directo a nuestro equipo — te contactarán para conocer tus ideas. (tus datos van "
        "a nuestro equipo para contactarte)\n\n"
        "Si prefieres, puedes agendar una llamada aquí: {booking}, o escribirnos ahora por "
        "WhatsApp {contact}."
    ),
    "it": (
        "Perfetto! 😊 Il modo più rapido per te: dimmi il tuo nome e WhatsApp (o email) e lo "
        "giro subito al nostro team — ti contatteranno per capire le tue idee. (i tuoi dati "
        "vanno al nostro team per contattarti)\n\n"
        "Se preferisci, puoi prenotare una chiamata qui: {booking}, oppure scrivici ora su "
        "WhatsApp {contact}."
    ),
}


async def generate_handoff_response(state: dict) -> dict:
    """Return a deterministic capture-first handoff message — no LLM call."""
    language = state.get("language") or "pt-BR"
    template = HANDOFFS.get(language, HANDOFFS["pt-BR"])
    response = template.format(booking=config.BOOKING_URL, contact=config.WHATSAPP_CONTACT)
    return {
        **state,
        "response": response,
        "revised_response": response,
        "step": "generate_handoff_response",
    }
