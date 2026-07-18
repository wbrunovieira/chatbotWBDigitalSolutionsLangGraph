#!/usr/bin/env python
"""
Versão 3 dos prompts - TODOS os prompts centralizados no Langfuse.

Arquitetura:
- Todos os prompts versionados no Langfuse
- Código apenas executa, não contém prompts hardcoded
- Fallback local apenas se Langfuse offline

Usage:
    python langfuse_prompts_v3.py
"""
import logging
from langfuse import Langfuse
from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# TODOS OS PROMPTS DO CHATBOT - VERSÃO 3
# ============================================================

PROMPTS_V3 = {
    # ========== DETECÇÃO DE INTENT ==========
    "detect_intent": {
        "type": "text",
        "prompt": """Classify the user's intent for the WB Digital Solutions chatbot.

Company services: websites, e-commerce, automation, AI solutions and AI agents,
e-learning / EAD platforms.

User message: "{{user_input}}"
User language: {{language}}
Current page: {{current_page}}

Messages are short, informal, and often contain typos, abbreviations (vc, vcs, pq),
missing accents, or spelling mistakes ("automassao" = automação). Classify by INTENT,
not by spelling.

CLASSIFICATION RULES:

1. **greeting** - A social greeting with NO other request. Includes time-of-day
   greetings in any language:
   - pt: "oi", "olá", "bom dia", "boa tarde", "boa noite", "e aí"
   - en: "hi", "hello", "hey", "good morning/afternoon/evening"
   - es: "hola", "buenos días", "buenas tardes/noches"
   - it: "ciao", "buongiorno", "buonasera"
   - If the message is a greeting AND also asks something, use the OTHER intent:
     "boa tarde, quanto custa?" → request_quote

2. **request_quote** - Asking about PRICE or BUDGET:
   - "quanto custa", "preço", "valor", "orçamento", "how much", "price", "cost"

3. **inquire_services** - Any question or interest about WHAT WB DOES — services,
   features, timelines, process — even if misspelled or just "do you do X?":
   - "quais serviços", "vocês fazem X", "vcs fazem site/automassao?", "quanto tempo",
     "como funciona", "quero uma automação", "app com agentes", "plataforma de ensino"

4. **share_contact** - Wants CONTACT INFO:
   - "como falo com vocês", "contato", "whatsapp", "telefone", "email"

5. **chat_with_agent** - Wants to talk to a HUMAN:
   - "falar com humano", "atendente", "pessoa real", "quero falar com alguém"

6. **off_topic** - ONLY topics with NO relation to WB's business:
   - general trivia, math, weather, sports: "capital do Brasil", "2+2", "que horas são"
   - A greeting is NEVER off_topic. Anything about websites, e-commerce, automation,
     AI, agents, or e-learning is NEVER off_topic (classify it as inquire_services or
     request_quote instead). When unsure between a service intent and off_topic,
     choose the service intent.

Examples:
- "boa tarde" → greeting
- "bom dia" → greeting
- "vcs fazem automassao?" → inquire_services
- "boa tarde, voce desenvolvem app com agentes?" → inquire_services
- "quanto custa um site?" → request_quote
- "qual a capital do Brasil?" → off_topic

Respond with ONLY a JSON object, no prose:
{"intent": "<one of: greeting, request_quote, inquire_services, share_contact, chat_with_agent, off_topic>"}""",
        "config": {"model": "deepseek-chat", "temperature": 0.1},
    },

    # Greetings are hardcoded (no LLM call) in nodes.GREETINGS — see the architecture guideline.

    # ========== OFF-TOPIC ==========
    "generate_off_topic": {
        "type": "text",
        "prompt": """Generate a polite redirect response for an off-topic question.

User asked: "{{user_input}}"
Language: {{language}}

RULES:
1. Do NOT answer the off-topic question
2. Politely explain you're specialized in digital solutions
3. List what you CAN help with (websites, automation, AI, EAD)
4. Invite them to ask about these services
5. Do NOT include contact info (they didn't ask about services)
6. Keep it friendly, not dismissive
7. Use 1-2 emoji

Generate the redirect response in {{language}}:""",
        "config": {"model": "deepseek-chat", "temperature": 0.7},
    },

    # ========== RESPOSTA SOBRE SERVIÇOS ==========
    "generate_services_response": {
        "type": "text",
        "prompt": """Generate a response about WB Digital Solutions services.

User question: "{{user_input}}"
Language: {{language}}
Current page: {{current_page}}
Detected intent: {{intent}}

COMPANY CONTEXT:
{{company_context}}

RULES:
1. Answer the specific question asked
2. Be informative but concise (max 3 paragraphs)
3. Highlight relevant services based on the question
4. End with a helpful next step that keeps the conversation going — invite the user to tell
   you more about their project or offer to help them move forward. Do NOT paste a phone
   number or WhatsApp; contact is offered separately, only when the user asks to talk to a
   person or is clearly ready to proceed.
5. Use bullet points for lists
6. Use appropriate emoji (1-2 max)

SERVICES TO MENTION (if relevant):
- 🌐 Websites: institutional, landing pages, PWA
- 🛒 E-commerce: online stores, payment integration
- ⚙️ Automation: process automation, integrations, chatbots
- 🤖 AI Solutions: data analysis, ML, virtual assistants
- 🎓 EAD Platforms: LMS, online courses, virtual classrooms

Generate response in {{language}}:""",
        "config": {"model": "deepseek-chat", "temperature": 0.7},
    },

    # Pricing is no longer discussed in chat — a price question is routed to lead capture
    # (create_lead / schedule_meeting) instead of quoting. Prompt intentionally removed.

    # Contact-on-request is handled by the handoff_to_human tool (see nodes.TOOL_SYSTEM_PROMPT);
    # the former generate_contact_response / generate_response_system prompts were never wired
    # and have been removed.

    # ========== INSTRUÇÃO DE GERAÇÃO ==========
    "generate_response_instruction": {
        "type": "text",
        "prompt": """CHECKLIST before responding:
✅ Language: Same as user ({{language}})
✅ Length: Max 3 paragraphs, ~400 characters
✅ Contact: only if the user asked to talk to someone or is ready to proceed — otherwise keep engaging
✅ Tone: Professional, friendly, helpful
✅ Call-to-action: Clear next step""",
        "config": {},
    },

    # ========== REVISÃO DE RESPOSTA ==========
    "revise_response": {
        "type": "text",
        "prompt": """Revise this chatbot response.

Original: {{response}}
Language: {{language}}
Intent: {{intent}}

STRICT RULES:
1. MAX 500 characters
2. MAX 3 paragraphs
3. Keep original language ({{language}})
4. Do NOT add a phone number or WhatsApp that isn't already in the original — contact is
   surfaced elsewhere (a booking link / human handoff), only when the user asks or is ready
5. If contact is already present, keep it (consolidate if fragmented)
6. Remove redundancy
7. Keep friendly, professional tone

Return ONLY the revised text:""",
        "config": {"model": "deepseek-chat", "temperature": 0.5},
    },

    # ========== AVALIAÇÃO ==========
    "evaluate_response": {
        "type": "text",
        "prompt": """Evaluate the chatbot response. Score each 0 or 1.

User: {{user_input}}
Response: {{response}}
Intent: {{intent}}

CRITERIA:
1. relevance: Addresses user's question? (1=yes, 0=no)
2. contact_when_asked: 1 if the user asked how to contact us and the response provides it, OR the user did not ask (contact not needed); 0 only if the user asked for contact and it's missing
3. tone: Professional and friendly? (1=yes, 0=no)
4. language_correct: Correct language? (1=yes, 0=no)
5. concise: Not too long? (1=yes, 0=no)

JSON only:
{"relevance": 0|1, "contact_when_asked": 0|1, "tone": 0|1, "language_correct": 0|1, "concise": 0|1}""",
        "config": {"model": "deepseek-chat", "temperature": 0.1},
    },
}

# ============================================================
# CONSTANTES (usadas nos prompts)
# ============================================================
CONTACT_INFO = {
    "whatsapp": "(11) 98286-4581",
    "whatsapp_international": "+55 11 98286-4581",
    "email": "bruno@wbdigitalsolutions.com",
}


def upload_prompts_v3():
    """Upload all v3 prompts to Langfuse."""
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        logger.error("Langfuse credentials not configured")
        return False

    client = Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
    )

    success_count = 0
    for name, data in PROMPTS_V3.items():
        try:
            logger.info(f"Uploading prompt: {name}")
            client.create_prompt(
                name=name,
                type=data["type"],
                prompt=data["prompt"],
                config=data.get("config", {}),
                labels=["production", "v3"],
            )
            logger.info(f"✓ {name}")
            success_count += 1
        except Exception as e:
            logger.error(f"✗ {name}: {e}")

    client.flush()

    print(f"\n{'='*50}")
    print(f"Uploaded {success_count}/{len(PROMPTS_V3)} prompts")
    print(f"{'='*50}")

    return success_count == len(PROMPTS_V3)


def list_all_prompts():
    """List all prompts from Langfuse."""
    client = Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
    )

    print("\nPrompts no Langfuse:")
    print("=" * 50)
    for name in PROMPTS_V3.keys():
        try:
            p = client.get_prompt(name)
            print(f"✓ {name}: v{p.version}")
        except:
            print(f"✗ {name}: não encontrado")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "list":
        list_all_prompts()
    else:
        print("=" * 50)
        print("  LANGFUSE PROMPTS V3 - Arquitetura Centralizada")
        print("=" * 50)
        print("\nPrompts a criar:")
        for name in PROMPTS_V3.keys():
            print(f"  • {name}")
        print()

        upload_prompts_v3()

        print("\nVerificando...")
        list_all_prompts()
