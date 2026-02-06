# experiments/chatbot_evaluator.py
"""
LLM-as-judge evaluator para o chatbot WB Digital Solutions.
Avalia respostas em múltiplos critérios de qualidade.
"""
import json
import httpx
import logging
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EVAL_PROMPT = """You are a quality evaluator for a customer service chatbot for WB Digital Solutions (a web development and AI company).

You will receive:
- The user's message
- The chatbot's response
- The detected intent
- Expected behavior

Evaluate the response on these criteria. Score each 0 or 1:

1. **intent_correct**: Does the detected intent match the expected intent?
   - "greeting" for hello/hi messages
   - "inquire_services" for questions about services
   - "request_quote" for pricing questions
   - "off_topic" for unrelated questions
   - "share_contact" or "chat_with_agent" for contact requests

2. **relevance**: Does the response address the user's question or need?
   - For greetings: welcomes and offers help = 1
   - For services: explains relevant services = 1
   - For pricing: mentions prices or asks for details = 1
   - For off_topic: politely redirects to services = 1

3. **mentions_contact**: Does it appropriately mention WhatsApp/contact?
   - Required for: pricing, services, contact requests
   - NOT required for: greetings, off_topic redirects
   - Score based on expected_should_mention_contact

4. **tone**: Is the tone professional, friendly, and helpful?
   - Uses appropriate emojis (not excessive)
   - Polite and welcoming
   - Not robotic or cold

5. **language_match**: Is the response in the correct language?
   - Must match the user's language (pt-BR, en, es, it)

6. **concise**: Is the response appropriately concise?
   - Not overly verbose
   - Key information is present
   - Max 3-4 paragraphs for detailed responses

---

User Message: {{user_message}}
Language: {{language}}
Current Page: {{current_page}}

Chatbot Response:
{{response}}

Detected Intent: {{detected_intent}}
Expected Intent: {{expected_intent}}
Expected Should Mention Contact: {{expected_mention_contact}}

---

Respond ONLY with valid JSON (no explanations):
{"intent_correct": 0 or 1, "relevance": 0 or 1, "mentions_contact": 0 or 1, "tone": 0 or 1, "language_match": 0 or 1, "concise": 0 or 1}"""


async def evaluate_chatbot_response(
    user_message: str,
    language: str,
    current_page: str,
    response: str,
    detected_intent: str,
    expected_intent: str,
    expected_mention_contact: bool,
    api_key: str,
) -> Optional[Dict[str, int]]:
    """
    Avalia uma resposta do chatbot usando LLM-as-judge.

    Args:
        user_message: Mensagem original do usuário
        language: Idioma esperado
        current_page: Página atual do usuário
        response: Resposta do chatbot
        detected_intent: Intent detectado pelo chatbot
        expected_intent: Intent esperado
        expected_mention_contact: Se deve mencionar contato
        api_key: DeepSeek API key

    Returns:
        Dict com scores (0 ou 1) para cada critério
    """
    prompt = EVAL_PROMPT.replace("{{user_message}}", user_message)
    prompt = prompt.replace("{{language}}", language)
    prompt = prompt.replace("{{current_page}}", current_page)
    prompt = prompt.replace("{{response}}", response)
    prompt = prompt.replace("{{detected_intent}}", detected_intent)
    prompt = prompt.replace("{{expected_intent}}", expected_intent)
    prompt = prompt.replace("{{expected_mention_contact}}", str(expected_mention_contact))

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                },
            )
            data = resp.json()
            eval_text = data["choices"][0]["message"]["content"].strip()

            # Limpar possíveis markdown code blocks
            if eval_text.startswith("```"):
                eval_text = eval_text.split("```")[1]
                if eval_text.startswith("json"):
                    eval_text = eval_text[4:]
            eval_text = eval_text.strip()

            scores = json.loads(eval_text)
            return scores

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse evaluation JSON: {e}")
        logger.error(f"Raw response: {eval_text}")
        return None
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        return None


def format_scores(scores: Dict[str, int]) -> str:
    """Formata scores para exibição."""
    if not scores:
        return "ERRO"

    parts = []
    for name, value in scores.items():
        emoji = "✓" if value == 1 else "✗"
        parts.append(f"{name}={emoji}")
    return " ".join(parts)


def calculate_summary(all_scores: list) -> Dict[str, Dict[str, int]]:
    """
    Calcula resumo estatístico dos scores.

    Returns:
        Dict com {criterio: {passed: N, total: N, percent: N}}
    """
    if not all_scores:
        return {}

    criteria = all_scores[0].keys()
    summary = {}

    for criterion in criteria:
        passed = sum(1 for s in all_scores if s.get(criterion) == 1)
        total = len(all_scores)
        summary[criterion] = {
            "passed": passed,
            "total": total,
            "percent": round(passed / total * 100) if total > 0 else 0,
        }

    return summary


def print_summary(summary: Dict[str, Dict[str, int]], run_name: str):
    """Imprime resumo formatado."""
    print("\n" + "=" * 60)
    print(f"  Experiment: {run_name}")
    print("=" * 60)

    for criterion, stats in summary.items():
        bar = "█" * (stats["percent"] // 5) + "░" * (20 - stats["percent"] // 5)
        print(f"  {criterion:20} {bar} {stats['percent']:3}% ({stats['passed']}/{stats['total']})")

    print("=" * 60)

    # Overall score
    total_passed = sum(s["passed"] for s in summary.values())
    total_possible = sum(s["total"] for s in summary.values())
    overall = round(total_passed / total_possible * 100) if total_possible > 0 else 0
    print(f"  OVERALL SCORE: {overall}%")
    print("=" * 60)
