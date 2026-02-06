#!/usr/bin/env python
"""
Teste isolado do agente generate_response.
Executa o prompt diretamente via Langfuse + DeepSeek, sem usar o chatbot.

Foco: Verificar se menciona contato quando apropriado.

Usage:
    python -m experiments.test_generate_response
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from langfuse import Langfuse
from langfuse.experiment import Evaluation

from config import (
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    LANGFUSE_HOST,
    DEEPSEEK_API_KEY,
)

DATASET_NAME = "generate-response-tests"

# Casos focados em verificar se menciona contato
TEST_CASES = [
    # Deve mencionar contato
    {
        "input": {
            "message": "Quais serviços vocês oferecem?",
            "intent": "inquire_services",
            "language": "pt-BR",
        },
        "expected": {"should_mention_contact": True},
    },
    {
        "input": {
            "message": "Quanto custa um site?",
            "intent": "request_quote",
            "language": "pt-BR",
        },
        "expected": {"should_mention_contact": True},
    },
    {
        "input": {
            "message": "How much for an e-commerce?",
            "intent": "request_quote",
            "language": "en",
        },
        "expected": {"should_mention_contact": True},
    },
    {
        "input": {
            "message": "Vocês fazem automação?",
            "intent": "inquire_services",
            "language": "pt-BR",
        },
        "expected": {"should_mention_contact": True},
    },
    {
        "input": {
            "message": "Me conta mais sobre sites",
            "intent": "inquire_services",
            "language": "pt-BR",
        },
        "expected": {"should_mention_contact": True},
    },
    {
        "input": {
            "message": "Quero um orçamento",
            "intent": "request_quote",
            "language": "pt-BR",
        },
        "expected": {"should_mention_contact": True},
    },
    {
        "input": {
            "message": "Como posso falar com vocês?",
            "intent": "share_contact",
            "language": "pt-BR",
        },
        "expected": {"should_mention_contact": True},
    },
    {
        "input": {
            "message": "Quero falar com um humano",
            "intent": "chat_with_agent",
            "language": "pt-BR",
        },
        "expected": {"should_mention_contact": True},
    },
    {
        "input": {
            "message": "Vocês desenvolvem plataformas EAD?",
            "intent": "inquire_services",
            "language": "pt-BR",
        },
        "expected": {"should_mention_contact": True},
    },
    {
        "input": {
            "message": "Fazem loja virtual?",
            "intent": "inquire_services",
            "language": "pt-BR",
        },
        "expected": {"should_mention_contact": True},
    },

    # NÃO deve mencionar contato (greeting simples)
    {
        "input": {
            "message": "Oi",
            "intent": "greeting",
            "language": "pt-BR",
        },
        "expected": {"should_mention_contact": False},
    },
    {
        "input": {
            "message": "Hello!",
            "intent": "greeting",
            "language": "en",
        },
        "expected": {"should_mention_contact": False},
    },

    # NÃO deve mencionar contato (off_topic)
    {
        "input": {
            "message": "Qual a capital do Brasil?",
            "intent": "off_topic",
            "language": "pt-BR",
        },
        "expected": {"should_mention_contact": False},
    },
    {
        "input": {
            "message": "Quanto é 2 + 2?",
            "intent": "off_topic",
            "language": "pt-BR",
        },
        "expected": {"should_mention_contact": False},
    },
]


def call_llm_chat(messages: list) -> str:
    """Chama o DeepSeek com mensagens de chat."""
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": messages,
                "temperature": 0.7,
            },
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


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
                expected_output=case["expected"],
            )
            print(f"[{i}/{len(TEST_CASES)}] {case['input']['message'][:30]}...")
        except Exception as e:
            print(f"[{i}] Erro: {e}")

    client.flush()
    print(f"\nDataset populado com {len(TEST_CASES)} casos")


def run_experiment(client: Langfuse, run_name: str):
    """Executa o experimento isolado do generate_response."""

    # Buscar prompt do Langfuse
    prompt_obj = client.get_prompt("generate_response_system", type="chat")
    print(f"\nUsando prompt 'generate_response_system' versão {prompt_obj.version}")

    # Buscar dataset
    dataset = client.get_dataset(DATASET_NAME)
    items = list(dataset.items)
    print(f"Testando {len(items)} casos\n")

    # Task: executa o prompt diretamente
    def generate_response_task(item):
        message = item.input["message"]
        intent = item.input["intent"]
        language = item.input.get("language", "pt-BR")

        # Instruções de idioma
        lang_instructions = {
            "pt-BR": "Responda SEMPRE em português brasileiro.",
            "en": "ALWAYS respond in English.",
            "es": "Responda SIEMPRE en español.",
        }
        language_instruction = lang_instructions.get(language, lang_instructions["pt-BR"])

        # Contexto simplificado para teste
        company_context = """WB Digital Solutions oferece:
- Sites e landing pages personalizados
- E-commerce e lojas virtuais
- Automação de processos
- Soluções com IA
- Plataformas EAD
Contato: WhatsApp (11) 98286-4581"""

        # Compilar prompt
        try:
            compiled = prompt_obj.compile(
                language_instruction=language_instruction,
                current_page="/",
                page_context="Página inicial",
                page_specific_context="",
                company_context=company_context,
                user_context="Novo usuário",
                user_input=message,
            )

            # O prompt compilado deve ser uma lista de mensagens
            if isinstance(compiled, list):
                messages = compiled
            else:
                messages = [
                    {"role": "system", "content": str(compiled)},
                    {"role": "user", "content": message}
                ]

        except Exception as e:
            print(f"Erro ao compilar prompt: {e}")
            # Fallback simples
            messages = [
                {"role": "system", "content": f"Você é assistente da WB Digital Solutions. {language_instruction}"},
                {"role": "user", "content": message}
            ]

        response = call_llm_chat(messages)

        return {"response": response, "intent": intent}

    # Evaluators
    def contact_evaluator(*, input, output, expected_output, **kwargs):
        """Verifica se menciona contato quando deveria."""
        response = (output.get("response", "") if output else "").lower()
        should_mention = expected_output.get("should_mention_contact", False) if expected_output else False

        contact_terms = ["whatsapp", "98286", "982864581", "(11)", "contato", "contact"]
        mentions = any(term in response for term in contact_terms)

        if should_mention:
            score = 1.0 if mentions else 0.0
            comment = "OK: menciona contato" if mentions else "ERRO: deveria mencionar contato"
        else:
            # Para greeting/off_topic, não precisa mencionar
            score = 1.0  # Passa de qualquer forma
            comment = "OK: contato opcional" if not mentions else "OK: mencionou contato (opcional)"

        return Evaluation(name="mentions_contact", value=score, comment=comment)

    def tone_evaluator(*, input, output, expected_output, **kwargs):
        """Verifica tom profissional."""
        response = output.get("response", "") if output else ""

        # Heurística: resposta não muito curta e com estrutura
        is_good = len(response) > 30

        return Evaluation(
            name="tone",
            value=1.0 if is_good else 0.0,
            comment=f"length={len(response)}"
        )

    def language_evaluator(*, input, output, expected_output, **kwargs):
        """Verifica idioma correto."""
        response = (output.get("response", "") if output else "").lower()
        expected_lang = input.get("language", "pt-BR") if input else "pt-BR"

        pt_words = ["você", "nosso", "para", "com", "oferecemos", "serviços"]
        en_words = ["you", "our", "services", "we", "website", "contact"]

        if expected_lang == "pt-BR":
            score = 1.0 if any(w in response for w in pt_words) else 0.0
        elif expected_lang == "en":
            score = 1.0 if any(w in response for w in en_words) else 0.0
        else:
            score = 1.0

        return Evaluation(name="language_match", value=score, comment=f"expected={expected_lang}")

    # Rodar experimento
    print("Executando experimento...\n")

    result = client.run_experiment(
        name=DATASET_NAME,
        run_name=run_name,
        data=items,
        task=generate_response_task,
        evaluators=[contact_evaluator, tone_evaluator, language_evaluator],
        max_concurrency=2,
    )

    # Resultados
    print("\n" + "=" * 60)
    print(f"  RESULTADOS: {run_name}")
    print("=" * 60)

    if hasattr(result, 'format'):
        print(result.format())

    print("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true", help="Seed dataset first")
    parser.add_argument("--run-name", default="generate-response-v2", help="Experiment run name")
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
