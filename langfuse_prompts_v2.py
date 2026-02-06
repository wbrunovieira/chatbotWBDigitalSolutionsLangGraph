# langfuse_prompts_v2.py
"""
Versão 2 dos prompts do chatbot - Melhorias baseadas nos resultados do experimento analysis-v1.

Problemas identificados na v1:
- intent_correct: 74.1% - Confusão entre intents similares
- mentions_contact: 51.9% - Não menciona contato quando deveria

Melhorias na v2:
1. detect_intent: Mais exemplos e regras mais claras
2. generate_response: Regra OBRIGATÓRIA para mencionar contato
3. revise_response: Garantir que contato não seja removido

Usage:
    python langfuse_prompts_v2.py
"""
import logging
from langfuse import Langfuse
from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Prompt definitions - VERSION 2
PROMPTS_V2 = {
    "detect_intent": {
        "type": "text",
        "prompt": """Analyze this message and classify the user's intent for WB Digital Solutions chatbot.

WB Digital Solutions provides: websites, e-commerce, automation, AI solutions, and EAD platforms.

Message: "{{user_input}}"

CLASSIFICATION RULES (in order of priority):

1. **off_topic** - Message is COMPLETELY UNRELATED to business/tech services:
   - General knowledge questions (geography, math, history, weather)
   - Personal questions unrelated to services
   - Examples: "What's the capital of Brazil?", "What's 2+2?", "How's the weather?"

2. **greeting** - ONLY simple greetings without any service question:
   - Examples: "Hi", "Hello", "Oi", "Olá", "Good morning"
   - NOT greeting if includes a question: "Hi, what services do you offer?" → inquire_services

3. **request_quote** - Asking about PRICES, COSTS, or BUDGET:
   - Keywords: "quanto custa", "preço", "valor", "orçamento", "how much", "price", "cost", "budget"
   - Examples: "Quanto custa um site?", "How much for e-commerce?", "Quero orçamento"

4. **chat_with_agent** / **share_contact** - Wants to TALK TO A HUMAN or get CONTACT INFO:
   - Keywords: "falar com humano", "falar com alguém", "contato", "WhatsApp", "talk to someone"
   - Examples: "Quero falar com um humano", "Como posso falar com vocês?"

5. **inquire_services** - Questions about SERVICES, FEATURES, CAPABILITIES, TIMELINES:
   - Asking what services are offered
   - Asking about specific features or technologies
   - Asking about timelines or delivery
   - Asking for more information about a service
   - Examples: "Quais serviços oferecem?", "Vocês fazem sites?", "Me conta mais", "Quanto tempo demora?"

Return ONLY one of these intents: greeting, inquire_services, request_quote, chat_with_agent, share_contact, off_topic""",
        "config": {
            "model": "deepseek-chat",
            "temperature": 0.1,
        },
    },
    "generate_response_system": {
        "type": "chat",
        "prompt": [
            {
                "role": "system",
                "content": """You are an assistant from WB Digital Solutions, a company specialized in creating premium custom websites, business automation, and AI-driven solutions.

{{language_instruction}}

=== CRITICAL RULES ===

1. **ALWAYS INCLUDE CONTACT** when the intent is:
   - inquire_services
   - request_quote
   - chat_with_agent
   - share_contact

   Contact format: "📲 WhatsApp (11) 98286-4581 - respondemos em até 2h!"

   This is MANDATORY. Every response about services MUST end with contact info.

2. **OFF-TOPIC HANDLING**: If the user asks about something UNRELATED to our services (geography, math, sports, etc.), politely redirect:
   "Essa pergunta foge um pouco da minha área! 😊 Sou especializado em ajudar com sites, automação e soluções de IA. Posso ajudar com algum projeto digital?"

   Do NOT answer off-topic questions directly. Do NOT include contact for off-topic.

3. **GREETING ONLY**: For simple greetings, welcome warmly and briefly mention services, but contact is optional.

=== CONTEXT ===

Current page: {{current_page}}
{{page_context}}
{{page_specific_context}}

Company Context:
{{company_context}}

User's Previous Interaction:
{{user_context}}

=== RESPONSE GUIDELINES ===

- Keep responses concise (2-3 paragraphs max)
- Focus on value and benefits for the customer
- End with a clear call-to-action
- For service/quote questions: ALWAYS include WhatsApp contact at the end
- Typical timelines: 4-12 weeks depending on complexity
- Emphasize: fast response (2h), personalized service, modern tech stack""",
            },
            {"role": "user", "content": "{{user_input}}"},
        ],
        "config": {
            "model": "deepseek-chat",
            "temperature": 0.7,
        },
    },
    "generate_response_instruction": {
        "type": "text",
        "prompt": """MANDATORY CHECKLIST before sending response:

✅ Language: Same as user's message
✅ Length: Max 3 paragraphs, ~400 characters
✅ Typos: Ignore user typos, understand intent
✅ Contact: If about services/pricing → MUST include "📲 WhatsApp (11) 98286-4581"
✅ Off-topic: Redirect politely, NO contact info
✅ Call-to-action: End with clear next step

CONTACT IS REQUIRED for: services, pricing, quotes, features, timelines, "tell me more"
CONTACT IS NOT REQUIRED for: greetings only, off-topic redirects""",
        "config": {},
    },
    "revise_response": {
        "type": "text",
        "prompt": """Revise this chatbot response following these STRICT rules:

RULES:
1. MAX 500 characters total
2. MAX 3 paragraphs
3. Keep original language
4. If WhatsApp/contact exists in original → KEEP IT (consolidate to one line if fragmented)
5. If original is about services but MISSING contact → ADD: "📲 WhatsApp (11) 98286-4581 - respondemos em até 2h!"
6. End with clear call-to-action
7. Keep friendly, professional tone
8. Remove redundancy but NEVER remove contact info

CONTACT FORMAT (always use this exact format):
📲 WhatsApp (11) 98286-4581 - respondemos em até 2h!

Reply ONLY with the revised text, no explanations.

Original: {{response}}""",
        "config": {
            "model": "deepseek-chat",
            "temperature": 0.5,
        },
    },
    "evaluate_response": {
        "type": "text",
        "prompt": """Evaluate the chatbot response. Score each criterion 0 or 1.

User question: {{user_input}}
Chatbot response: {{response}}
Detected intent: {{intent}}

SCORING RULES:

1. **relevance** (0 or 1): Does response address the user's question?
   - 1 = Answers the question or appropriately redirects
   - 0 = Ignores the question or gives unrelated info

2. **mentions_contact** (0 or 1): Contact info when needed?
   - Intent is inquire_services, request_quote, chat_with_agent, share_contact:
     - 1 = Contains WhatsApp/phone/email
     - 0 = Missing contact info
   - Intent is greeting or off_topic:
     - 1 = Always (contact optional for these)

3. **tone** (0 or 1): Professional and friendly?
   - 1 = Polite, helpful, appropriate emojis
   - 0 = Rude, cold, or unprofessional

4. **on_topic** (0 or 1): Stays on topic?
   - 1 = About WB services OR properly redirects off-topic
   - 0 = Answers off-topic questions directly

5. **concise** (0 or 1): Appropriately concise?
   - 1 = Clear, not verbose, max 3-4 paragraphs
   - 0 = Too long or too short

Return ONLY valid JSON:
{"relevance": 0 or 1, "mentions_contact": 0 or 1, "tone": 0 or 1, "on_topic": 0 or 1, "concise": 0 or 1}""",
        "config": {
            "model": "deepseek-chat",
            "temperature": 0.1,
        },
    },
}


def upload_prompts_v2():
    """Upload all v2 prompts to Langfuse."""
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        logger.error("Langfuse credentials not configured")
        return False

    client = Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
    )

    success_count = 0
    for name, data in PROMPTS_V2.items():
        try:
            logger.info(f"Uploading prompt v2: {name}")
            client.create_prompt(
                name=name,
                type=data["type"],
                prompt=data["prompt"],
                config=data.get("config", {}),
                labels=["production", "v2"],
            )
            logger.info(f"Successfully uploaded: {name}")
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to upload {name}: {e}")

    client.flush()
    logger.info(f"Uploaded {success_count}/{len(PROMPTS_V2)} prompts")
    return success_count == len(PROMPTS_V2)


if __name__ == "__main__":
    print("=" * 60)
    print("  Uploading Prompts V2 to Langfuse")
    print("=" * 60)
    print("\nImprovements in V2:")
    print("  - detect_intent: Clearer rules, more examples")
    print("  - generate_response: MANDATORY contact for services")
    print("  - revise_response: Never remove contact, add if missing")
    print()

    if upload_prompts_v2():
        print("\n✅ All prompts uploaded successfully!")
        print("   New version created in Langfuse with labels: production, v2")
    else:
        print("\n❌ Some prompts failed to upload")
