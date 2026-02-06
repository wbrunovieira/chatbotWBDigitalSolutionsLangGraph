#!/usr/bin/env python
"""
Teste isolado do agente revise_response.
Executa o prompt diretamente via Langfuse + DeepSeek, sem usar o chatbot.

Foco: Verificar se mantém/adiciona contato e mantém qualidade.

Usage:
    python -m experiments.test_revise_response
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

DATASET_NAME = "revise-response-tests"

# Casos para testar revisão de respostas
TEST_CASES = [
    # Resposta com contato fragmentado - deve consolidar
    {
        "input": {
            "original_response": """Olá! A WB Digital Solutions oferece diversos serviços de desenvolvimento web e automação.

Nossos principais serviços incluem:
- Sites e landing pages
- E-commerce
- Automação de processos
- Soluções com IA

Para mais informações, entre em contato pelo WhatsApp.
O número é (11) 98286-4581.
Ou envie email para bruno@wbdigitalsolutions.com.
Respondemos em até 2 horas!""",
        },
        "expected": {
            "should_have_contact": True,
            "max_length": 600,
        },
    },

    # Resposta SEM contato sobre serviços - deve ADICIONAR
    {
        "input": {
            "original_response": """A WB Digital Solutions é especializada em desenvolvimento web e soluções digitais.

Oferecemos sites personalizados, e-commerce, automação de processos e integração com IA.

Nossos projetos são desenvolvidos com as melhores tecnologias do mercado.""",
        },
        "expected": {
            "should_have_contact": True,  # DEVE adicionar contato
            "max_length": 600,
        },
    },

    # Resposta muito longa - deve encurtar
    {
        "input": {
            "original_response": """Olá! Seja muito bem-vindo à WB Digital Solutions! É um prazer enorme tê-lo aqui conosco!

A WB Digital Solutions é uma empresa especializada em criar soluções digitais inovadoras e personalizadas para empresas de todos os tamanhos e segmentos. Nossa equipe é composta por profissionais altamente qualificados e experientes, prontos para transformar suas ideias em realidade.

Nossos serviços incluem:

1. Desenvolvimento de Sites e Landing Pages
Criamos sites modernos, responsivos e otimizados para SEO. Cada projeto é único e desenvolvido especificamente para atender às necessidades do seu negócio.

2. E-commerce e Lojas Virtuais
Desenvolvemos plataformas completas de e-commerce com integração de pagamentos, gestão de estoque e muito mais.

3. Automação de Processos
Automatizamos tarefas repetitivas para aumentar a produtividade da sua empresa.

4. Soluções com Inteligência Artificial
Implementamos chatbots, análise de dados e outras soluções baseadas em IA.

5. Plataformas EAD
Criamos sistemas completos de ensino a distância.

Entre em contato pelo WhatsApp (11) 98286-4581 para saber mais! Respondemos em até 2 horas!""",
        },
        "expected": {
            "should_have_contact": True,
            "max_length": 600,
        },
    },

    # Resposta de saudação simples - não precisa de contato
    {
        "input": {
            "original_response": """Olá! Bem-vindo à WB Digital Solutions! 👋

Somos especialistas em desenvolvimento web, automação e soluções com IA.

Como posso ajudá-lo hoje?""",
        },
        "expected": {
            "should_have_contact": False,  # Saudação, contato opcional
            "max_length": 600,
        },
    },

    # Resposta off-topic - não deve ter contato
    {
        "input": {
            "original_response": """Essa pergunta foge um pouco da minha área de especialidade! 😊

Sou um assistente especializado em ajudar com questões sobre desenvolvimento web, automação e soluções digitais.

Posso ajudá-lo com algum projeto digital?""",
        },
        "expected": {
            "should_have_contact": False,
            "max_length": 600,
        },
    },

    # Resposta em inglês - deve manter idioma
    {
        "input": {
            "original_response": """Hello! WB Digital Solutions offers a wide range of digital services.

Our main services include:
- Custom websites and landing pages
- E-commerce platforms
- Process automation
- AI-powered solutions

Contact us on WhatsApp at +55 11 98286-4581 for more information!""",
        },
        "expected": {
            "should_have_contact": True,
            "max_length": 600,
            "language": "en",
        },
    },
]


def call_llm(prompt: str) -> str:
    """Chama o DeepSeek diretamente."""
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5,
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
            original = case["input"]["original_response"][:40]
            print(f"[{i}/{len(TEST_CASES)}] {original}...")
        except Exception as e:
            print(f"[{i}] Erro: {e}")

    client.flush()
    print(f"\nDataset populado com {len(TEST_CASES)} casos")


def run_experiment(client: Langfuse, run_name: str):
    """Executa o experimento isolado do revise_response."""

    # Buscar prompt do Langfuse
    prompt_obj = client.get_prompt("revise_response")
    print(f"\nUsando prompt 'revise_response' versão {prompt_obj.version}")

    # Buscar dataset
    dataset = client.get_dataset(DATASET_NAME)
    items = list(dataset.items)
    print(f"Testando {len(items)} casos\n")

    # Task: executa o prompt diretamente
    def revise_response_task(item):
        original = item.input["original_response"]

        compiled = prompt_obj.compile(response=original)
        revised = call_llm(compiled)

        return {
            "revised_response": revised,
            "original_length": len(original),
            "revised_length": len(revised),
        }

    # Evaluators
    def contact_evaluator(*, input, output, expected_output, **kwargs):
        """Verifica se tem contato quando deveria."""
        revised = (output.get("revised_response", "") if output else "").lower()
        should_have = expected_output.get("should_have_contact", True) if expected_output else True

        contact_terms = ["whatsapp", "98286", "982864581", "(11)"]
        has_contact = any(term in revised for term in contact_terms)

        if should_have:
            score = 1.0 if has_contact else 0.0
            comment = "OK: tem contato" if has_contact else "ERRO: deveria ter contato"
        else:
            score = 1.0  # Opcional
            comment = "OK: contato opcional"

        return Evaluation(name="has_contact", value=score, comment=comment)

    def length_evaluator(*, input, output, expected_output, **kwargs):
        """Verifica se respeitou limite de caracteres."""
        revised = output.get("revised_response", "") if output else ""
        max_length = expected_output.get("max_length", 600) if expected_output else 600

        score = 1.0 if len(revised) <= max_length else 0.0
        comment = f"length={len(revised)}, max={max_length}"

        return Evaluation(name="length_ok", value=score, comment=comment)

    def quality_evaluator(*, input, output, expected_output, **kwargs):
        """Verifica qualidade básica."""
        revised = output.get("revised_response", "") if output else ""

        # Não deve estar vazio e deve ter pelo menos 50 chars
        is_good = len(revised) >= 50

        return Evaluation(
            name="quality",
            value=1.0 if is_good else 0.0,
            comment=f"length={len(revised)}"
        )

    # Rodar experimento
    print("Executando experimento...\n")

    result = client.run_experiment(
        name=DATASET_NAME,
        run_name=run_name,
        data=items,
        task=revise_response_task,
        evaluators=[contact_evaluator, length_evaluator, quality_evaluator],
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
    parser.add_argument("--run-name", default="revise-response-v2", help="Experiment run name")
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
