#!/usr/bin/env python
"""
Teste isolado do agente detect_intent.
Executa o prompt diretamente via Langfuse + DeepSeek, sem usar o chatbot.

Usage:
    python -m experiments.test_detect_intent
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import json
from langfuse import Langfuse
from langfuse.experiment import Evaluation

from config import (
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    LANGFUSE_HOST,
    DEEPSEEK_API_KEY,
)

# Dataset específico para detect_intent
DATASET_NAME = "detect-intent-tests"

TEST_CASES = [
    # GREETINGS
    {"input": {"message": "Oi"}, "expected": "greeting"},
    {"input": {"message": "Hello!"}, "expected": "greeting"},
    {"input": {"message": "Hola, buenos días"}, "expected": "greeting"},
    {"input": {"message": "Ciao!"}, "expected": "greeting"},

    # INQUIRE_SERVICES
    {"input": {"message": "Quais serviços vocês oferecem?"}, "expected": "inquire_services"},
    {"input": {"message": "What services do you provide?"}, "expected": "inquire_services"},
    {"input": {"message": "Vocês fazem sites?"}, "expected": "inquire_services"},
    {"input": {"message": "Trabalham com automação?"}, "expected": "inquire_services"},
    {"input": {"message": "Vocês desenvolvem plataformas de ensino EAD?"}, "expected": "inquire_services"},
    {"input": {"message": "Fazem loja virtual e-commerce?"}, "expected": "inquire_services"},
    {"input": {"message": "Quanto tempo demora para fazer um site?"}, "expected": "inquire_services"},
    {"input": {"message": "Me conta mais"}, "expected": "inquire_services"},
    {"input": {"message": "Quero saber mais"}, "expected": "inquire_services"},
    {"input": {"message": "Vocês usam React ou Vue?"}, "expected": "inquire_services"},
    {"input": {"message": "Os sites são responsivos?"}, "expected": "inquire_services"},

    # REQUEST_QUOTE
    {"input": {"message": "Quanto custa um site?"}, "expected": "request_quote"},
    {"input": {"message": "How much for an e-commerce website?"}, "expected": "request_quote"},
    {"input": {"message": "Qual o valor de uma automação?"}, "expected": "request_quote"},
    {"input": {"message": "Quero um orçamento para landing page"}, "expected": "request_quote"},
    {"input": {"message": "quantu custa um siti?"}, "expected": "request_quote"},  # typo

    # CONTACT
    {"input": {"message": "Como posso falar com vocês?"}, "expected": "share_contact"},
    {"input": {"message": "Quero falar com um humano"}, "expected": "chat_with_agent"},

    # OFF_TOPIC
    {"input": {"message": "Qual a capital do Brasil?"}, "expected": "off_topic"},
    {"input": {"message": "What's the weather like today?"}, "expected": "off_topic"},
    {"input": {"message": "Quanto é 2 + 2?"}, "expected": "off_topic"},

    # TYPOS
    {"input": {"message": "vcs fazem automassao?"}, "expected": "inquire_services"},
]


def call_llm(prompt: str) -> str:
    """Chama o DeepSeek diretamente."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            },
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip().lower()


def seed_dataset(client: Langfuse):
    """Cria o dataset no Langfuse."""
    try:
        client.create_dataset(name=DATASET_NAME)
        print(f"Dataset '{DATASET_NAME}' criado")
    except:
        print(f"Dataset '{DATASET_NAME}' já existe")

    for i, case in enumerate(TEST_CASES, 1):
        try:
            client.create_dataset_item(
                dataset_name=DATASET_NAME,
                input=case["input"],
                expected_output={"intent": case["expected"]},
            )
            print(f"[{i}/{len(TEST_CASES)}] {case['input']['message'][:30]}...")
        except Exception as e:
            print(f"[{i}] Erro: {e}")

    client.flush()
    print(f"\nDataset populado com {len(TEST_CASES)} casos")


def run_experiment(client: Langfuse, run_name: str):
    """Executa o experimento isolado do detect_intent."""

    # Buscar prompt do Langfuse
    prompt_obj = client.get_prompt("detect_intent")
    print(f"\nUsando prompt 'detect_intent' versão {prompt_obj.version}")

    # Buscar dataset
    dataset = client.get_dataset(DATASET_NAME)
    items = list(dataset.items)
    print(f"Testando {len(items)} casos\n")

    # Task: executa o prompt diretamente
    def detect_intent_task(item):
        message = item.input["message"]
        compiled_prompt = prompt_obj.compile(user_input=message)

        detected = call_llm(compiled_prompt)

        # Normalizar resposta
        valid_intents = ["greeting", "inquire_services", "request_quote",
                        "chat_with_agent", "share_contact", "schedule_meeting", "off_topic"]

        # Limpar resposta
        detected = detected.strip().lower()
        if detected not in valid_intents:
            # Tentar extrair intent da resposta
            for intent in valid_intents:
                if intent in detected:
                    detected = intent
                    break
            else:
                detected = "unknown"

        return {"detected_intent": detected}

    # Evaluator
    def intent_evaluator(*, input, output, expected_output, **kwargs):
        detected = output.get("detected_intent", "unknown") if output else "unknown"
        expected = expected_output.get("intent", "unknown") if expected_output else "unknown"

        # Equivalências
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

    # Rodar experimento
    print("Executando experimento...\n")

    result = client.run_experiment(
        name=DATASET_NAME,
        run_name=run_name,
        data=items,
        task=detect_intent_task,
        evaluators=[intent_evaluator],
        max_concurrency=3,
    )

    # Resultados
    print("\n" + "=" * 60)
    print(f"  RESULTADOS: {run_name}")
    print("=" * 60)

    if hasattr(result, 'format'):
        print(result.format())

    # Calcular estatísticas manualmente
    if hasattr(result, 'item_results') and result.item_results:
        correct = 0
        total = len(result.item_results)

        print("\nDetalhes:")
        for i, item_result in enumerate(result.item_results):
            inp = item_result.input.get("message", "?") if hasattr(item_result, 'input') else "?"
            out = item_result.output.get("detected_intent", "?") if hasattr(item_result, 'output') else "?"
            exp = item_result.expected_output.get("intent", "?") if hasattr(item_result, 'expected_output') else "?"

            is_correct = False
            if hasattr(item_result, 'evaluations') and item_result.evaluations:
                for ev in item_result.evaluations:
                    if ev.value >= 0.5:
                        is_correct = True
                        correct += 1
                        break

            status = "✓" if is_correct else "✗"
            print(f"  {status} \"{inp[:30]}\" → {out} (esperado: {exp})")

        print(f"\n  SCORE: {correct}/{total} ({correct/total*100:.1f}%)")

    print("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true", help="Seed dataset first")
    parser.add_argument("--run-name", default="detect-intent-v2", help="Experiment run name")
    args = parser.parse_args()

    client = Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
    )

    if args.seed:
        seed_dataset(client)

    run_experiment(client, args.run_name)


if __name__ == "__main__":
    main()
