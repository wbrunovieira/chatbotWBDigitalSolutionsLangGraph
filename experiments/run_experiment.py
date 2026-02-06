#!/usr/bin/env python
# experiments/run_experiment.py
"""
Runner de experimentos para o chatbot WB Digital Solutions.
Usa o método run_experiment do Langfuse SDK v3.

Usage:
    # Criar dataset (primeira vez)
    python -m experiments.run_experiment --seed-only

    # Rodar experimento
    python -m experiments.run_experiment --run-name "prompt-v1"

    # Rodar sem recriar dataset
    python -m experiments.run_experiment --skip-seed --run-name "prompt-v2"
"""
import asyncio
import argparse
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import json
import logging
from langfuse import Langfuse
from langfuse.experiment import Evaluation

from config import (
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    LANGFUSE_HOST,
    DEEPSEEK_API_KEY,
)
from experiments.chatbot_dataset import DATASET_NAME, TEST_CASES, seed_dataset
from experiments.chatbot_evaluator import (
    format_scores,
    calculate_summary,
    print_summary,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# URL do chatbot (produção ou local)
CHATBOT_URL = os.getenv("CHATBOT_URL", "https://chatbot.wbdigitalsolutions.com")


def call_chatbot_sync(
    message: str,
    language: str,
    current_page: str,
    user_id: str = "experiment",
) -> dict:
    """
    Chama o endpoint do chatbot de forma síncrona.
    """
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            f"{CHATBOT_URL}/chat",
            json={
                "message": message,
                "user_id": user_id,
                "language": language,
                "current_page": current_page,
            },
        )
        return response.json()


def call_evaluator_sync(
    user_message: str,
    language: str,
    current_page: str,
    response: str,
    detected_intent: str,
    expected_intent: str,
    expected_mention_contact: bool,
) -> dict:
    """
    Avalia uma resposta usando LLM-as-judge de forma síncrona.
    """
    eval_prompt = f"""You are evaluating a chatbot response. Score each criterion 0 or 1.

User Message: {user_message}
Language: {language}
Page: {current_page}
Response: {response}
Detected Intent: {detected_intent}
Expected Intent: {expected_intent}
Should Mention Contact: {expected_mention_contact}

Criteria:
1. intent_correct: Does detected intent match expected?
2. relevance: Does response address the question?
3. mentions_contact: Appropriately mentions WhatsApp/contact?
4. tone: Professional and friendly?
5. language_match: Response in correct language?
6. concise: Not overly verbose?

Respond ONLY with JSON: {{"intent_correct": 0|1, "relevance": 0|1, "mentions_contact": 0|1, "tone": 0|1, "language_match": 0|1, "concise": 0|1}}"""

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": eval_prompt}],
                    "temperature": 0.1,
                },
            )
            data = resp.json()
            eval_text = data["choices"][0]["message"]["content"].strip()

            # Clean markdown
            if eval_text.startswith("```"):
                eval_text = eval_text.split("```")[1]
                if eval_text.startswith("json"):
                    eval_text = eval_text[4:]
            eval_text = eval_text.strip()

            return json.loads(eval_text)
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        return {}


def chatbot_task(item) -> dict:
    """
    Task function para o experimento.
    Recebe um item do dataset e retorna o output do chatbot.
    """
    input_data = item.input
    message = input_data["message"]
    language = input_data.get("language", "pt-BR")
    current_page = input_data.get("current_page", "/")

    result = call_chatbot_sync(
        message=message,
        language=language,
        current_page=current_page,
        user_id="experiment",
    )

    return {
        "response": result.get("revised_response", result.get("raw_response", "")),
        "detected_intent": result.get("detected_intent", "unknown"),
        "cached": result.get("cached", False),
        "final_step": result.get("final_step", "unknown"),
    }


def create_evaluators(langfuse: Langfuse):
    """
    Cria funções de avaliação para o experimento.
    Signature: (*, input, output, expected_output, metadata, **kwargs) -> Evaluation
    """

    def intent_evaluator(*, input, output, expected_output, metadata=None, **kwargs):
        """Avalia se o intent está correto."""
        detected = output.get("detected_intent", "unknown") if output else "unknown"
        expected = expected_output.get("intent", "unknown") if expected_output else "unknown"

        # Alguns intents são equivalentes
        equivalent = {
            "share_contact": ["share_contact", "chat_with_agent"],
            "chat_with_agent": ["share_contact", "chat_with_agent"],
        }

        if expected in equivalent:
            score = 1.0 if detected in equivalent[expected] else 0.0
        else:
            score = 1.0 if detected == expected else 0.0

        return Evaluation(
            name="intent_correct",
            value=score,
            comment=f"detected={detected}, expected={expected}"
        )

    def contact_evaluator(*, input, output, expected_output, metadata=None, **kwargs):
        """Avalia se menciona contato quando apropriado."""
        response = (output.get("response", "") if output else "").lower()
        should_mention = expected_output.get("should_mention_contact", False) if expected_output else False

        mentions = any(
            term in response
            for term in ["whatsapp", "11 98286", "982864581", "bruno@"]
        )

        if should_mention:
            score = 1.0 if mentions else 0.0
            comment = "Mentions contact" if mentions else "Missing contact info"
        else:
            score = 1.0  # Não precisa mencionar, então passa
            comment = "Contact not required"

        return Evaluation(name="mentions_contact", value=score, comment=comment)

    def tone_evaluator(*, input, output, expected_output, metadata=None, **kwargs):
        """Avalia o tom da resposta."""
        response = output.get("response", "") if output else ""

        # Heurística simples: verifica se tem emojis e não é muito curta
        has_emoji = any(c in response for c in "👋😊🚀💡📱✅🌐🤖🧠💎⚙️📋📲🎓🛒")
        not_too_short = len(response) > 50

        score = 1.0 if (has_emoji or not_too_short) else 0.0
        comment = f"emoji={has_emoji}, length={len(response)}"

        return Evaluation(name="tone", value=score, comment=comment)

    def language_evaluator(*, input, output, expected_output, metadata=None, **kwargs):
        """Avalia se a resposta está no idioma correto."""
        response = output.get("response", "") if output else ""
        expected_lang = input.get("language", "pt-BR") if input else "pt-BR"

        # Heurística por palavras-chave
        pt_words = ["você", "nosso", "nossa", "para", "com", "que", "oferecemos"]
        en_words = ["you", "our", "for", "with", "that", "we offer", "services"]
        es_words = ["usted", "nuestro", "para", "con", "que", "ofrecemos"]

        response_lower = response.lower()

        if expected_lang == "pt-BR":
            score = 1.0 if any(w in response_lower for w in pt_words) else 0.0
        elif expected_lang == "en":
            score = 1.0 if any(w in response_lower for w in en_words) else 0.0
        elif expected_lang == "es":
            score = 1.0 if any(w in response_lower for w in es_words) else 0.0
        else:
            score = 1.0  # Default pass for other languages

        return Evaluation(
            name="language_match",
            value=score,
            comment=f"expected={expected_lang}"
        )

    def relevance_evaluator(*, input, output, expected_output, metadata=None, **kwargs):
        """Avalia relevância usando LLM."""
        if not input or not output:
            return Evaluation(name="relevance", value=0.0, comment="Missing input/output")

        scores = call_evaluator_sync(
            user_message=input.get("message", ""),
            language=input.get("language", "pt-BR"),
            current_page=input.get("current_page", "/"),
            response=output.get("response", ""),
            detected_intent=output.get("detected_intent", "unknown"),
            expected_intent=expected_output.get("intent", "unknown") if expected_output else "unknown",
            expected_mention_contact=expected_output.get("should_mention_contact", True) if expected_output else True,
        )

        return Evaluation(
            name="relevance",
            value=float(scores.get("relevance", 0)),
            comment="LLM-as-judge evaluation"
        )

    return [
        intent_evaluator,
        contact_evaluator,
        tone_evaluator,
        language_evaluator,
        relevance_evaluator,
    ]


def run_experiment_sync(run_name: str, langfuse: Langfuse):
    """
    Executa o experimento usando o método run_experiment do Langfuse.
    """
    print(f"\n{'='*60}")
    print(f"  Running experiment: {run_name}")
    print(f"  Dataset: {DATASET_NAME}")
    print(f"  Chatbot URL: {CHATBOT_URL}")
    print(f"{'='*60}\n")

    # Obter dataset
    try:
        dataset = langfuse.get_dataset(DATASET_NAME)
        items = list(dataset.items)
        print(f"Found {len(items)} test cases\n")
    except Exception as e:
        logger.error(f"Failed to get dataset: {e}")
        return

    # Criar evaluators
    evaluators = create_evaluators(langfuse)

    # Rodar experimento
    print("Running experiment (this may take a few minutes)...\n")

    try:
        result = langfuse.run_experiment(
            name=DATASET_NAME,
            run_name=run_name,
            data=items,
            task=chatbot_task,
            evaluators=evaluators,
            max_concurrency=3,  # Limitar para não sobrecarregar o chatbot
        )

        # Exibir resultados usando o método format() do SDK
        print(f"\n{'='*60}")
        print(f"  Experiment Results: {run_name}")
        print(f"{'='*60}")

        # Usar o método format() para exibir resultados
        if hasattr(result, 'format'):
            formatted = result.format()
            print(formatted)

        # Também calcular estatísticas a partir de item_results
        scores_by_name = {}

        if hasattr(result, 'item_results') and result.item_results:
            for item_result in result.item_results:
                if hasattr(item_result, 'evaluations') and item_result.evaluations:
                    for evaluation in item_result.evaluations:
                        name = evaluation.name if hasattr(evaluation, 'name') else 'unknown'
                        value = evaluation.value if hasattr(evaluation, 'value') else 0
                        if name not in scores_by_name:
                            scores_by_name[name] = []
                        scores_by_name[name].append(value)

        if scores_by_name:
            print(f"\n{'='*60}")
            print("  Summary Statistics:")
            print(f"{'='*60}")
            for name, scores_list in scores_by_name.items():
                avg = sum(scores_list) / len(scores_list) if scores_list else 0
                passed = sum(1 for s in scores_list if s and s >= 0.5)
                bar = "█" * int(avg * 20) + "░" * (20 - int(avg * 20))
                print(f"  {name:20} {bar} {avg*100:5.1f}% ({passed}/{len(scores_list)})")

            # Overall score
            total_passed = sum(sum(1 for s in scores if s and s >= 0.5) for scores in scores_by_name.values())
            total_possible = sum(len(scores) for scores in scores_by_name.values())
            overall = round(total_passed / total_possible * 100) if total_possible > 0 else 0
            print(f"\n  OVERALL SCORE: {overall}%")


        print(f"{'='*60}")
        print(f"\nExperiment completed! View detailed results at:")
        print(f"  {LANGFUSE_HOST}/datasets/{DATASET_NAME}")

    except Exception as e:
        logger.error(f"Experiment failed: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="Run chatbot experiments")
    parser.add_argument("--seed-only", action="store_true", help="Only seed the dataset")
    parser.add_argument("--skip-seed", action="store_true", help="Skip dataset seeding")
    parser.add_argument("--run-name", type=str, default="experiment-1", help="Name for this run")
    parser.add_argument("--local", action="store_true", help="Use local chatbot (localhost:8000)")

    args = parser.parse_args()

    # Configurar URL
    global CHATBOT_URL
    if args.local:
        CHATBOT_URL = "http://localhost:8000"
        print(f"Using local chatbot: {CHATBOT_URL}")

    # Verificar credenciais
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        print("ERROR: Langfuse credentials not configured")
        print("Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env")
        sys.exit(1)

    if not DEEPSEEK_API_KEY:
        print("ERROR: DeepSeek API key not configured")
        sys.exit(1)

    # Inicializar Langfuse
    langfuse = Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
    )

    # Seed dataset se necessário
    if not args.skip_seed:
        print("Seeding dataset...")
        seed_dataset(langfuse)

        if args.seed_only:
            print("\nDataset seeded successfully. Exiting.")
            return

    # Rodar experimento
    run_experiment_sync(args.run_name, langfuse)


if __name__ == "__main__":
    main()
