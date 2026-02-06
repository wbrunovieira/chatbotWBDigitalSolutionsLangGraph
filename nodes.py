# nodes.py
import httpx
import re
import time
import uuid
import logging
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
from config import DEEPSEEK_API_KEY
from sentence_transformers import SentenceTransformer
from langdetect import detect
from deepseek_optimizer import DeepSeekOptimizer, estimate_tokens, should_skip_api_call
from langfuse_client import start_llm_generation, end_llm_generation, get_prompt, evaluate_response, score_trace


embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

def compute_embedding(text: str) -> list:
    """
    Computes a real embedding for the given text using Sentence Transformers.
    Returns a list of floats.
    """
    # Limitar o texto para evitar problemas de performance
    # O modelo tem limite de contexto e textos muito grandes demoram muito
    max_length = 512  # Limite de tokens para performance
    if len(text) > max_length * 4:  # Aproximadamente 4 chars por token
        text = text[:max_length * 4]
    
    # Desabilitar progress bar que pode causar lentidão
    embedding = embedding_model.encode(text, show_progress_bar=False)
    return embedding.tolist()


async def detect_intent(state: dict) -> dict:
    """
    Detecta intent usando prompt do Langfuse.
    Sem bypass hardcoded - sempre usa o prompt para consistência.
    """
    user_input = state["user_input"]
    language = state.get("language", "pt-BR")
    current_page = state.get("current_page", "/")

    # Get prompt from Langfuse (with local fallback)
    intent_prompt = get_prompt("detect_intent")
    if intent_prompt:
        try:
            prompt = intent_prompt.compile(
                user_input=user_input,
                language=language,
                current_page=current_page,
            )
        except:
            # Fallback se compile falhar (variáveis não existem no prompt)
            prompt = intent_prompt.compile(user_input=user_input)
    else:
        # Hardcoded fallback if no prompt available
        prompt = f"""Classify intent for: "{user_input}"
Return ONLY: greeting, inquire_services, request_quote, chat_with_agent, share_contact, or off_topic"""

    intent = "inquire_services"  # default
    trace = state.get("langfuse_trace")

    try:
        optimization_headers = DeepSeekOptimizer.get_optimization_headers()

        # Start generation BEFORE LLM call (captures start time)
        generation = start_llm_generation(
            trace=trace,
            name="detect_intent",
            model="deepseek-chat",
            input_messages=[{"role": "user", "content": prompt}],
            metadata={"temperature": 0.1},
            prompt=intent_prompt,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                    **optimization_headers
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1
                }
            )
        data = response.json()

        usage = data.get("usage", {})
        if usage:
            DeepSeekOptimizer.update_usage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                cache_hit=response.headers.get("X-Cache-Status") == "hit"
            )

        raw_intent = data["choices"][0]["message"]["content"].strip().lower()

        # Extrair intent válido da resposta
        valid_intents = {"greeting", "request_quote", "inquire_services", "chat_with_agent", "share_contact", "off_topic"}
        for valid in valid_intents:
            if valid in raw_intent:
                intent = valid
                break

        # End generation AFTER LLM call (captures end time)
        end_llm_generation(
            generation=generation,
            output_content=raw_intent,
            usage=usage,
            metadata={"detected_intent": intent},
        )
    except Exception as e:
        logging.error(f"Error in intent detection: {e}")
        intent = "inquire_services"

    return {**state, "intent": intent, "step": "detect_intent"}

async def retrieve_company_context(state: dict) -> dict:
    """
    Searches the Qdrant collection 'company_info' for the company context
    using the embedding of the user's query.
    """
    embedding = compute_embedding(state["user_input"])
    try:
        results = state["qdrant_client"].search(
            collection_name="company_info",
            query_vector=embedding,
            limit=1
        )
        if results:
            company_context = results[0].payload.get("company_info", "")
        else:
            company_context = ""
    except Exception as e:
        logging.error("Error retrieving company context: %s", e)
        company_context = ""
    return {**state, "company_context": company_context, "step": "retrieve_company_context"}

async def retrieve_user_context(state: dict) -> dict:
    """
    Searches the Qdrant collection 'chat_logs' for previous conversations
    from the same user (based on user_id) and combines them into a context.
    """

    query_filter = {"must": [{"key": "user_id", "match": {"value": state.get("user_id")}}]}

    dummy_vector = [0.0] * 384
    try:
        results = state["qdrant_client"].search(
            collection_name="chat_logs",
            query_vector=dummy_vector,
            limit=5,
            query_filter=query_filter
        )

        if results:
            user_context = "\n".join([r.payload.get("response", "") for r in results])
        else:
            user_context = ""
    except Exception as e:
        logging.error("Error retrieving user context: %s", e)
        user_context = ""
    return {**state, "user_context": user_context, "step": "retrieve_user_context"}

async def augment_query(state: dict) -> dict:
    """
    Prepara o contexto para geração de resposta usando prompt do Langfuse.
    """
    company_context = state.get("company_context", "")
    user_context = state.get("user_context", "")
    user_input = state.get("user_input", "")
    language = state.get("language", "pt-BR")
    page_context = state.get("page_context", "")
    current_page = state.get("current_page", "/")
    intent = state.get("intent", "inquire_services")

    # Determinar instrução de idioma
    language_instructions = {
        "en": "IMPORTANT: Respond in English.",
        "es": "IMPORTANTE: Responde en español.",
        "it": "IMPORTANTE: Rispondi in italiano.",
        "pt-BR": "IMPORTANTE: Responda em português brasileiro.",
    }
    language_instruction = language_instructions.get(language, language_instructions["pt-BR"])

    # Contexto da página
    page_contexts = {
        "/websites": "User viewing web development services page.",
        "/automation": "User exploring automation services.",
        "/ai": "User interested in AI solutions.",
        "/contact": "User on contact page, ready to reach out.",
    }
    page_specific_context = page_contexts.get(current_page, "User on home page.")

    # Buscar prompt do Langfuse baseado no intent
    if intent == "request_quote":
        system_prompt = get_prompt("generate_pricing_response")
    else:
        system_prompt = get_prompt("generate_services_response")

    if system_prompt:
        try:
            augmented = system_prompt.compile(
                user_input=user_input,
                language=language,
                language_instruction=language_instruction,
                current_page=current_page,
                page_context=page_specific_context,
                company_context=company_context or "WB Digital Solutions - websites, automation, AI",
                user_context=user_context,
                intent=intent,
                whatsapp="(11) 98286-4581",
                email="bruno@wbdigitalsolutions.com",
            )
        except Exception as e:
            logging.warning(f"Error compiling system prompt: {e}")
            # Fallback simples
            augmented = f"""You are WB Digital Solutions assistant. {language_instruction}
Answer: {user_input}
Include WhatsApp (11) 98286-4581 at the end."""
    else:
        # Fallback se não encontrar prompt no Langfuse
        augmented = f"""You are WB Digital Solutions assistant specializing in websites, automation, and AI.
{language_instruction}
Context: {company_context}
User question: {user_input}
IMPORTANT: Always include WhatsApp (11) 98286-4581 at the end of your response."""

    return {**state, "augmented_input": augmented, "step": "augment_query"}

async def generate_response(state: dict) -> dict:
    user_input = state["user_input"]
    augmented_input = state.get("augmented_input")
    trace = state.get("langfuse_trace")

    # Get instruction prompt from Langfuse
    instruction_prompt = get_prompt("generate_response_instruction")
    if instruction_prompt:
        instruction = instruction_prompt.compile() + "\n\n"
    else:
        instruction = (
            "Before answering, always make sure to:\n"
            "- Preserve the user's original language\n"
            "- Keep responses concise (max 3-4 paragraphs)\n"
            "- If including contact, use ONE line: 'WhatsApp (11) 98286-4581 - respondemos em 2h!'\n\n"
        )

    query = f"{instruction}{augmented_input}" if augmented_input else f"{instruction}{user_input}"

    messages = state.get("messages", []) + [{"role": "user", "content": query}]

    try:
        # Adicionar headers de otimização
        optimization_headers = DeepSeekOptimizer.get_optimization_headers()

        # Start generation BEFORE LLM call
        generation = start_llm_generation(
            trace=trace,
            name="generate_response",
            model="deepseek-chat",
            input_messages=messages,
            metadata={"temperature": 0.7},
            prompt=instruction_prompt if instruction_prompt else None,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                    **optimization_headers
                },
                json={
                    "model": "deepseek-chat",
                    "messages": messages,
                    "temperature": 0.7
                }
            )
    except httpx.ReadTimeout:
        logging.error("Request timed out in DeepSeek API call for response generation")
        return {
            **state,
            "response": "Sorry, the service is taking too long to respond. Please try again later.",
            "step": "error_timeout"
        }

    data = response.json()

    # Rastrear uso de tokens
    usage = data.get("usage", {})
    if usage:
        DeepSeekOptimizer.update_usage(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cache_hit=response.headers.get("X-Cache-Status") == "hit"
        )

    reply = data["choices"][0]["message"]["content"]

    # End generation AFTER LLM call
    end_llm_generation(
        generation=generation,
        output_content=reply,
        usage=usage,
    )

    return {
        **state,
        "response": reply,
        "messages": messages + [{"role": "assistant", "content": reply}],
        "step": "generate_response",
        "instruction_prompt": instruction_prompt,
    }
def needs_revision(state: dict) -> bool:
    """
    Determina se a resposta precisa de revisão.
    Pula revisão para respostas já otimizadas.
    """
    response = state.get("response", "")

    # Critérios para PULAR revisão:
    # 1. Resposta curta e direta (menos de 1000 caracteres)
    # 2. Não contém informações sensíveis (emails, telefones)
    # 3. Foi gerada via fast track ou cache
    # 4. Já está bem formatada

    skip_revision = (
        len(response) < 1000 and
        "@" not in response and
        not re.search(r'\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{1,4}', response) and  # No phone numbers
        not re.search(r'whatsapp|wpp|zap|telefone|celular|ligar', response.lower()) and
        (state.get("fast_track", False) or state.get("cached", False))
    )

    return not skip_revision

async def revise_response(state: dict) -> dict:
    # Verificar se precisa de revisão
    if not needs_revision(state):
        logging.info("Skipping revision - response already optimized")
        return {
            **state,
            "revised_response": state["response"],
            "step": "revision_skipped"
        }

    trace = state.get("langfuse_trace")

    # Get revision prompt from Langfuse
    revise_prompt = get_prompt("revise_response")
    if revise_prompt:
        prompt = revise_prompt.compile(response=state["response"])
    else:
        prompt = (
            "Rewrite the following response to make it clearer and friendlier, keeping a professional tone.\n"
            "Maximum 500 characters. Preserve the original language.\n"
            "Reply ONLY with the improved text.\n\n"
            f"Original response: {state['response']}"
        )
    try:
        # Adicionar headers de otimização
        optimization_headers = DeepSeekOptimizer.get_optimization_headers()

        # Start generation BEFORE LLM call
        generation = start_llm_generation(
            trace=trace,
            name="revise_response",
            model="deepseek-chat",
            input_messages=[{"role": "user", "content": prompt}],
            metadata={"temperature": 0.5},
            prompt=revise_prompt if revise_prompt else None,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                    **optimization_headers
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5
                }
            )
    except httpx.ReadTimeout:
        logging.error("Request timed out in DeepSeek API call for response revision")
        return {
            **state,
            "revised_response": "Sorry, the service is taking too long to revise the response. Please try again later.",
            "step": "error_timeout"
        }

    data = response.json()

    # Rastrear uso de tokens
    usage = data.get("usage", {})
    if usage:
        DeepSeekOptimizer.update_usage(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cache_hit=response.headers.get("X-Cache-Status") == "hit"
        )

    revised = data["choices"][0]["message"]["content"]

    # End generation AFTER LLM call
    end_llm_generation(
        generation=generation,
        output_content=revised,
        usage=usage,
    )

    revised = revised.replace('\n\n', '\n').replace('\n', '\n\n')
    return {**state, "revised_response": revised, "step": "revise_response"}

async def save_log_qdrant(state: dict) -> dict:
    data_to_save = {
        "user_id": state.get("user_id"),
        "user_input": state.get("user_input"),
        "response": state.get("response"),
        "revised_response": state.get("revised_response"),
        "intent": state.get("intent"),
        "language": state.get("language"),
        "current_page": state.get("current_page"),
        "timestamp": int(time.time()),
    }
    logging.info("Saving to Qdrant: %s", data_to_save)

    combined_text = (
        f"User ID: {data_to_save.get('user_id', '')}\n"
        f"User Input: {data_to_save.get('user_input', '')}\n"
        f"Response: {data_to_save.get('response', '')}\n"
        f"Revised Response: {data_to_save.get('revised_response', '')}\n"
        f"Intent: {data_to_save.get('intent', '')}"
    )
    log_embedding = compute_embedding(combined_text)
    point = {
        "id": str(uuid.uuid4()),
        "vector": log_embedding,
        "payload": data_to_save,
    }
    try:
        state["qdrant_client"].upsert(
            collection_name="chat_logs",
            points=[point]
        )
        logging.info("Log saved to Qdrant successfully.")
    except Exception as e:
        logging.error("Error saving log to Qdrant: %s", e)

    return state


async def generate_off_topic_response(state: dict) -> dict:
    """
    Gera resposta para perguntas fora do escopo usando prompt do Langfuse.
    """
    user_input = state.get("user_input", "")
    language = state.get("language", "pt-BR")
    trace = state.get("langfuse_trace")

    # Buscar prompt do Langfuse
    off_topic_prompt = get_prompt("generate_off_topic")

    if off_topic_prompt:
        try:
            prompt = off_topic_prompt.compile(
                user_input=user_input,
                language=language,
            )
        except Exception as e:
            logging.warning(f"Error compiling off_topic prompt: {e}")
            prompt = f"User asked '{user_input}' which is off-topic. Politely redirect to digital services in {language}."
    else:
        prompt = f"User asked '{user_input}' which is off-topic. Politely redirect to digital services in {language}."

    try:
        # Start generation BEFORE LLM call
        generation = start_llm_generation(
            trace=trace,
            name="generate_off_topic",
            model="deepseek-chat",
            input_messages=[{"role": "user", "content": prompt}],
            metadata={"temperature": 0.7},
            prompt=off_topic_prompt,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                },
            )
            data = resp.json()
            response = data["choices"][0]["message"]["content"].strip()

            # End generation AFTER LLM call
            end_llm_generation(
                generation=generation,
                output_content=response,
                usage=data.get("usage"),
            )
    except Exception as e:
        logging.error(f"Error generating off-topic response: {e}")
        response = "Desculpe, sou especializado em soluções digitais. Posso ajudar com sites, automação ou IA?"

    return {
        **state,
        "response": response,
        "revised_response": response,
        "step": "generate_off_topic_response",
        "intent": "off_topic"
    }

async def generate_greeting_response(state: dict) -> dict:
    """
    Gera saudação usando prompt do Langfuse.
    """
    language = state.get("language", "pt-BR")
    current_page = state.get("current_page", "/")
    trace = state.get("langfuse_trace")

    # Buscar prompt do Langfuse
    greeting_prompt = get_prompt("generate_greeting")

    if greeting_prompt:
        try:
            prompt = greeting_prompt.compile(
                language=language,
                current_page=current_page,
                whatsapp="(11) 98286-4581",
            )
        except Exception as e:
            logging.warning(f"Error compiling greeting prompt: {e}")
            prompt = f"Generate a friendly greeting in {language}. Include WhatsApp (11) 98286-4581."
    else:
        prompt = f"Generate a friendly greeting in {language}. Include WhatsApp (11) 98286-4581."

    try:
        # Start generation BEFORE LLM call
        generation = start_llm_generation(
            trace=trace,
            name="generate_greeting",
            model="deepseek-chat",
            input_messages=[{"role": "user", "content": prompt}],
            metadata={"temperature": 0.7},
            prompt=greeting_prompt,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                },
            )
            data = resp.json()
            response = data["choices"][0]["message"]["content"].strip()

            # End generation AFTER LLM call
            end_llm_generation(
                generation=generation,
                output_content=response,
                usage=data.get("usage"),
            )
    except Exception as e:
        logging.error(f"Error generating greeting: {e}")
        # Fallback minimo
        response = "Olá! 👋 Sou o assistente da WB Digital Solutions. Como posso ajudar? 📲 WhatsApp (11) 98286-4581"

    return {
        **state,
        "response": response,
        "revised_response": response,
        "step": "generate_greeting_response"
    }



