"""Deterministic (hardcoded, no-LLM) opening greetings."""

# Deterministic opening greetings — no LLM call (per the architecture guideline: greetings
# use hardcoded responses). They engage and end on a qualifying question, and never push
# contact on turn 0; WhatsApp is surfaced later via handoff_to_human when the user asks.
GREETINGS = {
    "pt-BR": (
        "Olá 👋! Somos a WB Digital Solutions e ajudamos empresas a crescer com sites, "
        "automação e inteligência artificial. Para começar, você está pensando em um site "
        "novo, em automatizar um processo ou em usar IA no seu negócio?"
    ),
    "en": (
        "Hi 👋! We're WB Digital Solutions and we help businesses grow with websites, "
        "automation, and AI. To get started, are you thinking about a new website, "
        "automating a process, or using AI in your business?"
    ),
    "es": (
        "¡Hola 👋! Somos WB Digital Solutions y ayudamos a las empresas a crecer con sitios "
        "web, automatización e inteligencia artificial. Para empezar, ¿estás pensando en un "
        "sitio nuevo, en automatizar un proceso o en usar IA en tu negocio?"
    ),
    "it": (
        "Ciao 👋! Siamo WB Digital Solutions e aiutiamo le aziende a crescere con siti web, "
        "automazione e intelligenza artificiale. Per iniziare, stai pensando a un nuovo sito, "
        "ad automatizzare un processo o a usare l'IA nella tua azienda?"
    ),
}


async def generate_greeting_response(state: dict) -> dict:
    """Return a deterministic greeting — no LLM call (per the architecture guideline)."""
    language = state.get("language") or "pt-BR"
    response = GREETINGS.get(language, GREETINGS["pt-BR"])
    return {
        **state,
        "response": response,
        "revised_response": response,
        "step": "generate_greeting_response",
    }
