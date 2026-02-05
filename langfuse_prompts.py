# langfuse_prompts.py
"""
Script para criar/atualizar prompts no Langfuse.
Execute este script para versionar os prompts do chatbot.

Usage:
    python langfuse_prompts.py
"""
import logging
from langfuse import Langfuse
from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Prompt definitions
PROMPTS = {
    "detect_intent": {
        "type": "text",
        "prompt": """Analyze this message and determine if it's related to business/technology services or not.

Context: WB Digital Solutions provides websites, automation, and AI solutions for businesses.

Message: "{{user_input}}"

Question: Is this message asking about business services, technology, websites, automation, AI, pricing, or contacting the company?

If YES (related to business/tech): determine the specific intent:
- "greeting" if just saying hello
- "inquire_services" if asking about services
- "request_quote" if asking about prices
- "chat_with_agent" if wants human contact
- "schedule_meeting" if wants to schedule

If NO (NOT related): return "off_topic"

Examples:
- "What is the capital of Brazil?" → off_topic
- "How much for a website?" → request_quote
- "What services do you offer?" → inquire_services

Return ONLY the intent word, nothing else:""",
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

CRITICAL RULE: If the user asks about something COMPLETELY UNRELATED to our services (like geography, general knowledge, math, sports, etc.), politely redirect them to our services. DO NOT answer off-topic questions directly.

Current Context:
- User is on page: {{current_page}}
- {{page_context}}
{{page_specific_context}}

If the user's question clearly indicates interest in requesting a quote, detailed pricing, project specifics, or hiring services directly, provide detailed information and emphasize our fast response time and personalized service.

Always consider these important aspects if relevant:
- Typical timelines (4 to 12 weeks) based on complexity.
- Detailed project phases: Discovery, Design, Development, Testing & Launch.
- Ongoing post-launch support and hosting options.
- Robust security practices including Kubernetes, Rust, and LGPD/GDPR compliance.
- SEO optimization and multilingual capabilities.
- Suggest contacting our team directly for a detailed and tailored discussion.

Company Context:
{{company_context}}

User's Previous Interaction Context:
{{user_context}}""",
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
        "prompt": """Before answering, always make sure to:
- Preserve the user's original language
- Ignore typos, missing punctuation, or spacing errors
- Focus on understanding the user's intent clearly
- Keep responses concise (max 3-4 paragraphs)
- If including contact, use ONE line: 'WhatsApp (11) 98286-4581 - respondemos em 2h!'
- Focus on value and benefits for the customer
- End with a clear next step when appropriate""",
        "config": {},
    },
    "revise_response": {
        "type": "text",
        "prompt": """Rewrite the following response to make it clearer and friendlier, keeping a professional tone.

IMPORTANT RULES:
1. Maximum 3 paragraphs or sections
2. If there's contact info (WhatsApp/email), consolidate in ONE line with a benefit
   Example: 'WhatsApp (11) 98286-4581 - respondemos em até 2h!'
3. Keep the main message focused on value to the customer
4. Maximum 500 characters total
5. Preserve the original language
6. End with a clear call-to-action when appropriate
7. Do NOT fragment contact info into multiple parts

Reply ONLY with the improved text, no explanations.

Original response: {{response}}""",
        "config": {
            "model": "deepseek-chat",
            "temperature": 0.5,
        },
    },
    "evaluate_response": {
        "type": "text",
        "prompt": """Evaluate the chatbot response on these criteria. Score each 0 or 1.

User question: {{user_input}}
Chatbot response: {{response}}
Detected intent: {{intent}}

Criteria:
1. **relevance**: Does the response address the user's question or intent?
2. **mentions_contact**: Does it mention WhatsApp/contact info when the intent suggests interest in services?
3. **tone**: Is the tone professional, friendly, and helpful?
4. **on_topic**: Is the response about WB Digital Solutions services (not off-topic)?
5. **concise**: Is the response concise (not overly verbose)?

Respond ONLY with valid JSON, no explanations:
{"relevance": 0 or 1, "mentions_contact": 0 or 1, "tone": 0 or 1, "on_topic": 0 or 1, "concise": 0 or 1}""",
        "config": {
            "model": "deepseek-chat",
            "temperature": 0.1,
        },
    },
}


def upload_prompts():
    """Upload all prompts to Langfuse with production label."""
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        logger.error("Langfuse credentials not configured")
        return False

    client = Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
    )

    for name, data in PROMPTS.items():
        try:
            logger.info(f"Uploading prompt: {name}")
            client.create_prompt(
                name=name,
                type=data["type"],
                prompt=data["prompt"],
                config=data.get("config", {}),
                labels=["production"],
            )
            logger.info(f"Successfully uploaded: {name}")
        except Exception as e:
            logger.error(f"Failed to upload {name}: {e}")

    client.flush()
    logger.info("All prompts uploaded successfully")
    return True


def list_prompts():
    """List all prompts from Langfuse."""
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        logger.error("Langfuse credentials not configured")
        return

    client = Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
    )

    for name in PROMPTS.keys():
        try:
            prompt = client.get_prompt(name)
            logger.info(f"Prompt '{name}': version={prompt.version}, type={prompt.type}")
        except Exception as e:
            logger.warning(f"Prompt '{name}' not found: {e}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "list":
        list_prompts()
    else:
        upload_prompts()
