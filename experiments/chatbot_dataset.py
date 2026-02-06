# experiments/chatbot_dataset.py
"""
Dataset de testes para o chatbot WB Digital Solutions.
Casos de teste cobrindo diferentes intents, idiomas e edge cases.
"""

DATASET_NAME = "chatbot-wb-tests"

# Casos de teste organizados por categoria
TEST_CASES = [
    # ========== SAUDAÇÕES (greeting) ==========
    {
        "input": {"message": "Oi", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "greeting",
            "should_mention_services": True,
            "should_mention_contact": False,
        },
        "metadata": {"category": "greeting", "language": "pt-BR"},
    },
    {
        "input": {"message": "Hello!", "language": "en", "current_page": "/"},
        "expected_output": {
            "intent": "greeting",
            "should_mention_services": True,
            "should_mention_contact": False,
        },
        "metadata": {"category": "greeting", "language": "en"},
    },
    {
        "input": {"message": "Hola, buenos días", "language": "es", "current_page": "/"},
        "expected_output": {
            "intent": "greeting",
            "should_mention_services": True,
            "should_mention_contact": False,
        },
        "metadata": {"category": "greeting", "language": "es"},
    },
    {
        "input": {"message": "Ciao!", "language": "it", "current_page": "/"},
        "expected_output": {
            "intent": "greeting",
            "should_mention_services": True,
            "should_mention_contact": False,
        },
        "metadata": {"category": "greeting", "language": "it"},
    },
    # ========== CONSULTA DE SERVIÇOS (inquire_services) ==========
    {
        "input": {"message": "Quais serviços vocês oferecem?", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "inquire_services",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "services", "language": "pt-BR"},
    },
    {
        "input": {"message": "What services do you provide?", "language": "en", "current_page": "/"},
        "expected_output": {
            "intent": "inquire_services",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "services", "language": "en"},
    },
    {
        "input": {"message": "Vocês fazem sites?", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "inquire_services",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "services", "language": "pt-BR"},
    },
    {
        "input": {"message": "Trabalham com automação?", "language": "pt-BR", "current_page": "/automation"},
        "expected_output": {
            "intent": "inquire_services",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "services", "language": "pt-BR", "page_context": True},
    },
    {
        "input": {"message": "Vocês desenvolvem plataformas de ensino EAD?", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "inquire_services",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "services", "subcategory": "education", "language": "pt-BR"},
    },
    {
        "input": {"message": "Fazem loja virtual e-commerce?", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "inquire_services",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "services", "subcategory": "ecommerce", "language": "pt-BR"},
    },
    # ========== ORÇAMENTO (request_quote) ==========
    {
        "input": {"message": "Quanto custa um site?", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "request_quote",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "pricing", "language": "pt-BR"},
    },
    {
        "input": {"message": "How much for an e-commerce website?", "language": "en", "current_page": "/"},
        "expected_output": {
            "intent": "request_quote",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "pricing", "language": "en"},
    },
    {
        "input": {"message": "Qual o valor de uma automação?", "language": "pt-BR", "current_page": "/automation"},
        "expected_output": {
            "intent": "request_quote",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "pricing", "language": "pt-BR"},
    },
    {
        "input": {"message": "Quero um orçamento para landing page", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "request_quote",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "pricing", "language": "pt-BR"},
    },
    # ========== PRAZOS (timeline) ==========
    {
        "input": {"message": "Quanto tempo demora para fazer um site?", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "inquire_services",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "timeline", "language": "pt-BR"},
    },
    {
        "input": {"message": "What's the delivery timeline?", "language": "en", "current_page": "/"},
        "expected_output": {
            "intent": "inquire_services",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "timeline", "language": "en"},
    },
    # ========== CONTATO (share_contact / chat_with_agent) ==========
    {
        "input": {"message": "Como posso falar com vocês?", "language": "pt-BR", "current_page": "/contact"},
        "expected_output": {
            "intent": "share_contact",
            "should_mention_services": False,
            "should_mention_contact": True,
        },
        "metadata": {"category": "contact", "language": "pt-BR"},
    },
    {
        "input": {"message": "Quero falar com um humano", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "chat_with_agent",
            "should_mention_services": False,
            "should_mention_contact": True,
        },
        "metadata": {"category": "contact", "language": "pt-BR"},
    },
    # ========== OFF-TOPIC (deve redirecionar) ==========
    {
        "input": {"message": "Qual a capital do Brasil?", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "off_topic",
            "should_mention_services": True,  # Deve redirecionar
            "should_mention_contact": False,
        },
        "metadata": {"category": "off_topic", "language": "pt-BR"},
    },
    {
        "input": {"message": "What's the weather like today?", "language": "en", "current_page": "/"},
        "expected_output": {
            "intent": "off_topic",
            "should_mention_services": True,  # Deve redirecionar
            "should_mention_contact": False,
        },
        "metadata": {"category": "off_topic", "language": "en"},
    },
    {
        "input": {"message": "Quanto é 2 + 2?", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "off_topic",
            "should_mention_services": True,  # Deve redirecionar
            "should_mention_contact": False,
        },
        "metadata": {"category": "off_topic", "language": "pt-BR"},
    },
    # ========== TYPOS E ERROS ==========
    {
        "input": {"message": "quantu custa um siti?", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "request_quote",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "typos", "language": "pt-BR"},
    },
    {
        "input": {"message": "vcs fazem automassao?", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "inquire_services",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "typos", "language": "pt-BR"},
    },
    # ========== CONTEXTO DE PÁGINA ==========
    {
        "input": {"message": "Me conta mais", "language": "pt-BR", "current_page": "/ai"},
        "expected_output": {
            "intent": "inquire_services",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "page_context", "language": "pt-BR", "page": "/ai"},
    },
    {
        "input": {"message": "Quero saber mais", "language": "pt-BR", "current_page": "/websites"},
        "expected_output": {
            "intent": "inquire_services",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "page_context", "language": "pt-BR", "page": "/websites"},
    },
    # ========== PERGUNTAS TÉCNICAS ==========
    {
        "input": {"message": "Vocês usam React ou Vue?", "language": "pt-BR", "current_page": "/"},
        "expected_output": {
            "intent": "inquire_services",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "technical", "language": "pt-BR"},
    },
    {
        "input": {"message": "Os sites são responsivos?", "language": "pt-BR", "current_page": "/websites"},
        "expected_output": {
            "intent": "inquire_services",
            "should_mention_services": True,
            "should_mention_contact": True,
        },
        "metadata": {"category": "technical", "language": "pt-BR"},
    },
]


def seed_dataset(langfuse_client):
    """
    Cria o dataset e adiciona todos os casos de teste.

    Args:
        langfuse_client: Cliente Langfuse inicializado
    """
    # Criar dataset
    try:
        langfuse_client.create_dataset(name=DATASET_NAME)
        print(f"Dataset '{DATASET_NAME}' criado com sucesso")
    except Exception as e:
        print(f"Dataset já existe ou erro: {e}")

    # Adicionar casos de teste
    for i, case in enumerate(TEST_CASES, 1):
        try:
            langfuse_client.create_dataset_item(
                dataset_name=DATASET_NAME,
                input=case["input"],
                expected_output=case["expected_output"],
                metadata=case["metadata"],
            )
            print(f"[{i}/{len(TEST_CASES)}] Adicionado: {case['input']['message'][:40]}...")
        except Exception as e:
            print(f"[{i}/{len(TEST_CASES)}] Erro ao adicionar: {e}")

    langfuse_client.flush()
    print(f"\nDataset '{DATASET_NAME}' populado com {len(TEST_CASES)} casos de teste")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "..")
    from langfuse import Langfuse
    from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

    client = Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
    )
    seed_dataset(client)
