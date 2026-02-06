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
        "prompt": """Classify the user's intent for WB Digital Solutions chatbot.

Company services: websites, e-commerce, automation, AI solutions, EAD platforms.

User message: "{{user_input}}"
User language: {{language}}
Current page: {{current_page}}

CLASSIFICATION RULES:

1. **greeting** - Simple greetings without questions:
   - "Oi", "Olá", "Hi", "Hello", "Hola", "Ciao"
   - NOT if includes question: "Oi, quanto custa?" → request_quote

2. **request_quote** - Asking about PRICES or BUDGET:
   - "quanto custa", "preço", "valor", "orçamento", "how much", "price", "cost"

3. **inquire_services** - Questions about SERVICES, FEATURES, TIMELINES:
   - "quais serviços", "vocês fazem", "quanto tempo", "como funciona"
   - Questions about specific services (websites, automation, AI, EAD)

4. **share_contact** - Wants CONTACT INFO:
   - "como falo com vocês", "contato", "whatsapp", "telefone"

5. **chat_with_agent** - Wants to talk to a HUMAN:
   - "falar com humano", "atendente", "pessoa real"

6. **off_topic** - UNRELATED to business/tech:
   - General knowledge, math, weather, sports, etc.
   - "capital do Brasil", "2+2", "que horas são"

Return ONLY one word: greeting, request_quote, inquire_services, share_contact, chat_with_agent, off_topic""",
        "config": {"model": "deepseek-chat", "temperature": 0.1},
    },

    # ========== SAUDAÇÃO ==========
    "generate_greeting": {
        "type": "text",
        "prompt": """Generate a friendly greeting for WB Digital Solutions chatbot.

Language: {{language}}
Current page: {{current_page}}

RULES:
1. Be warm and welcoming
2. Briefly mention what WB does (websites, automation, AI)
3. ALWAYS include WhatsApp contact at the end
4. Keep it short (2-3 sentences max)
5. Use appropriate emoji (1-2 max)

CONTACT FORMAT (ALWAYS include):
📲 WhatsApp {{whatsapp}} - respondemos em até 2h!

Language-specific:
- pt-BR: Respond in Brazilian Portuguese
- en: Respond in English
- es: Respond in Spanish
- it: Respond in Italian

Generate the greeting:""",
        "config": {"model": "deepseek-chat", "temperature": 0.7},
    },

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
4. ALWAYS end with WhatsApp contact
5. Use bullet points for lists
6. Use appropriate emoji

SERVICES TO MENTION (if relevant):
- 🌐 Websites: institutional, landing pages, PWA
- 🛒 E-commerce: online stores, payment integration
- ⚙️ Automation: process automation, integrations, chatbots
- 🤖 AI Solutions: data analysis, ML, virtual assistants
- 🎓 EAD Platforms: LMS, online courses, virtual classrooms

CONTACT (ALWAYS include at end):
📲 WhatsApp {{whatsapp}} - respondemos em até 2h!

Generate response in {{language}}:""",
        "config": {"model": "deepseek-chat", "temperature": 0.7},
    },

    # ========== RESPOSTA SOBRE PREÇOS ==========
    "generate_pricing_response": {
        "type": "text",
        "prompt": """Generate a response about pricing for WB Digital Solutions.

User question: "{{user_input}}"
Language: {{language}}
Current page: {{current_page}}

PRICING REFERENCE (use as guide, not fixed):
- Landing Page: R$ 3.000+ / $600+ USD
- Institutional Website: R$ 6.000-15.000 / $1,200-3,000 USD
- E-commerce: R$ 12.000+ / $2,400+ USD
- Automation: R$ 5.000+ / $1,000+ USD
- AI Projects: Custom quote
- EAD Platform: R$ 15.000+ / $3,000+ USD

TIMELINES:
- Landing Page: 1-2 weeks
- Website: 4-6 weeks
- E-commerce: 8-12 weeks
- Automation: 2-4 weeks
- AI/EAD: 6-12 weeks

RULES:
1. Give price ranges, not exact prices
2. Explain that final price depends on requirements
3. Mention what affects price (features, complexity, timeline)
4. ALWAYS invite them to get a personalized quote
5. ALWAYS end with WhatsApp contact
6. Be transparent and helpful

CONTACT (ALWAYS include):
📲 WhatsApp {{whatsapp}} - orçamento personalizado em até 2h!

Generate response in {{language}}:""",
        "config": {"model": "deepseek-chat", "temperature": 0.7},
    },

    # ========== COMPARTILHAR CONTATO ==========
    "generate_contact_response": {
        "type": "text",
        "prompt": """Generate a response sharing WB Digital Solutions contact info.

User question: "{{user_input}}"
Language: {{language}}

CONTACT INFO:
- WhatsApp: {{whatsapp}}
- Email: {{email}}
- Response time: Within 2 hours (business hours)

RULES:
1. Be warm and welcoming
2. Provide all contact options clearly
3. Emphasize fast response time
4. Make it easy to contact (include clickable links format)
5. Invite them to reach out

Generate response in {{language}}:""",
        "config": {"model": "deepseek-chat", "temperature": 0.7},
    },

    # ========== SISTEMA DE GERAÇÃO (para casos complexos) ==========
    "generate_response_system": {
        "type": "chat",
        "prompt": [
            {
                "role": "system",
                "content": """You are an assistant for WB Digital Solutions, specialized in websites, automation, and AI solutions.

LANGUAGE: {{language_instruction}}

CRITICAL RULES:
1. ALWAYS include WhatsApp contact for service/pricing questions
2. For off-topic questions, politely redirect (no contact)
3. Be concise (max 3 paragraphs)
4. Use appropriate emoji (1-2 per response)

CONTACT FORMAT:
📲 WhatsApp {{whatsapp}} - respondemos em até 2h!

CONTEXT:
- Page: {{current_page}}
- {{page_context}}

COMPANY INFO:
{{company_context}}"""
            },
            {"role": "user", "content": "{{user_input}}"}
        ],
        "config": {"model": "deepseek-chat", "temperature": 0.7},
    },

    # ========== INSTRUÇÃO DE GERAÇÃO ==========
    "generate_response_instruction": {
        "type": "text",
        "prompt": """CHECKLIST before responding:
✅ Language: Same as user ({{language}})
✅ Length: Max 3 paragraphs, ~400 characters
✅ Contact: Include WhatsApp for services/pricing
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
4. If about services/pricing and MISSING contact → ADD it
5. If contact exists → keep it (consolidate if fragmented)
6. Remove redundancy
7. Keep friendly, professional tone

CONTACT FORMAT (if needed):
📲 WhatsApp (11) 98286-4581 - respondemos em até 2h!

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
2. mentions_contact: Has WhatsApp for services/pricing? (1=yes or not needed, 0=missing when needed)
3. tone: Professional and friendly? (1=yes, 0=no)
4. language_correct: Correct language? (1=yes, 0=no)
5. concise: Not too long? (1=yes, 0=no)

JSON only:
{"relevance": 0|1, "mentions_contact": 0|1, "tone": 0|1, "language_correct": 0|1, "concise": 0|1}""",
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
