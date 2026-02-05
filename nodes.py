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
from langfuse_client import log_llm_generation, get_prompt, evaluate_response, score_trace


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
    user_input = state["user_input"]
    lower_input = user_input.lower()
    
    # Detecção rápida de saudações simples (sem chamar API)
    greeting_patterns = [
        "oi", "olá", "ola", "oie", "oii", "oiii",
        "hi", "hello", "hey", "hii", "hiii",
        "hola", "holaa",
        "ciao", "salve", "ciaoo"
    ]
    
    # Se for apenas uma saudação simples (menos de 15 caracteres e contém padrão de saudação)
    if len(user_input.strip()) < 15 and any(greet in lower_input for greet in greeting_patterns):
        return {**state, "intent": "greeting", "step": "detect_intent"}

    if any(p in lower_input for p in ["falar com um humano", "fale com um humano", "humano", "quero falar com alguém"]):
        intent = "chat_with_agent"
    elif any(p in lower_input for p in ["solicitar orçamento", "quero um orçamento", "fazer um orçamento"]):
        intent = "request_quote"
    elif any(p in lower_input for p in ["ver serviços", "quais serviços", "serviços disponíveis"]):
        intent = "inquire_services"
    else:
        # Get prompt from Langfuse (with local fallback)
        intent_prompt = get_prompt("detect_intent")
        if intent_prompt:
            prompt = intent_prompt.compile(user_input=user_input)
        else:
            # Hardcoded fallback if no prompt available
            prompt = f"""Analyze this message and determine if it's related to business/technology services or not.

Context: WB Digital Solutions provides websites, automation, and AI solutions for businesses.

Message: "{user_input}"

Return ONLY the intent word: greeting, inquire_services, request_quote, chat_with_agent, schedule_meeting, or off_topic"""

        try:
            # Adicionar headers de otimização
            optimization_headers = DeepSeekOptimizer.get_optimization_headers()
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                        **optimization_headers  # Headers de otimização
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1
                    }
                )
                data = response.json()

                # Rastrear uso de tokens
                usage = data.get("usage", {})
                if usage:
                    DeepSeekOptimizer.update_usage(
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                        cache_hit=response.headers.get("X-Cache-Status") == "hit"
                    )

                raw_intent = data["choices"][0]["message"]["content"].strip().lower()
                intent = raw_intent if raw_intent in {"greeting", "request_quote", "inquire_services", "chat_with_agent", "schedule_meeting", "off_topic"} else "inquire_services"

                # Log to Langfuse
                trace = state.get("langfuse_trace")
                if trace:
                    log_llm_generation(
                        trace=trace,
                        name="detect_intent",
                        model="deepseek-chat",
                        input_messages=[{"role": "user", "content": prompt}],
                        output_content=raw_intent,
                        usage=usage,
                        metadata={"temperature": 0.1, "detected_intent": intent},
                        prompt=intent_prompt if intent_prompt else None,
                    )
        except Exception as e:
            logging.error(f"Error in intent detection: {e}")
            intent = "inquire_services"
            intent_prompt = None  

    # Adicionar flag de fast track para perguntas diretas sobre serviços
    fast_track_patterns = [
        "plataforma", "ensino", "ead", "curso", "lms", "educacional",
        "loja virtual", "ecommerce", "e-commerce", "vender online",
        "automação", "automatizar", "integração", "api", "webhook",
        "quanto custa", "preço", "valor", "orçamento", "investimento",
        "quais serviços", "o que fazem", "o que oferecem", "portfolio"
    ]

    should_fast_track = any(pattern in lower_input for pattern in fast_track_patterns)

    return {**state, "intent": intent, "step": "detect_intent", "fast_track": should_fast_track}

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
    company_context = state.get("company_context", "")
    user_context = state.get("user_context", "")
    user_input = state.get("user_input", "")
    language = state.get("language", "pt-BR")
    page_context = state.get("page_context", "")
    current_page = state.get("current_page", "/")
    
    # Determinar instrução de idioma
    language_instruction = ""
    if language == "en":
        language_instruction = "IMPORTANT: Respond in English."
    elif language == "es":
        language_instruction = "IMPORTANTE: Responde en español."
    elif language == "it":
        language_instruction = "IMPORTANTE: Rispondi in italiano."
    else:  # pt-BR or default
        language_instruction = "IMPORTANTE: Responda em português brasileiro."
    
    # Adicionar contexto específico da página
    page_specific_context = ""
    if current_page == "/websites":
        page_specific_context = "The user is currently viewing our web development services page. Focus on website features, technologies, and development process."
    elif current_page == "/automation":
        page_specific_context = "The user is exploring our automation services. Emphasize workflow optimization, time savings, and integration capabilities."
    elif current_page == "/ai":
        page_specific_context = "The user is interested in AI solutions. Highlight machine learning models, AI integrations, and intelligent automation."
    elif current_page == "/contact":
        page_specific_context = "The user is on the contact page, likely ready to reach out. Be more direct about contact options."
    
    augmented = f"""
    You are an assistant from WB Digital Solutions, a company specialized in creating premium custom websites, business automation, and AI-driven solutions.
    
    {language_instruction}
    
    CRITICAL RULE: If the user asks about something COMPLETELY UNRELATED to our services (like geography, general knowledge, math, sports, etc.), politely redirect them to our services. DO NOT answer off-topic questions directly.
    
    Current Context:
    - User is on page: {current_page}
    - {page_context}
    {page_specific_context}
    
    If the user's question clearly indicates interest in requesting a quote, detailed pricing, project specifics, or hiring services directly, provide detailed information and emphasize our fast response time and personalized service.
    Based on the company context and the user's question, provide a clear, professional, friendly response.

    Always consider these important aspects if relevant:
    - Typical timelines (4 to 12 weeks) based on complexity.
    - Detailed project phases: Discovery, Design, Development, Testing & Launch.
    - Ongoing post-launch support and hosting options.
    - Robust security practices including Kubernetes, Rust, and LGPD/GDPR compliance.
    - SEO optimization and multilingual capabilities.
    - Suggest contacting our team directly for a detailed and tailored discussion.

    Company Context:
    {company_context}

    User's Previous Interaction Context:
    {user_context}

    User's Current Question:
    {user_input}
    """
    
    return {**state, "augmented_input": augmented, "step": "augment_query"}

async def generate_response(state: dict) -> dict:
    user_input = state["user_input"]
    augmented_input = state.get("augmented_input")

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
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                    **optimization_headers  # Headers de otimização
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

    # Log to Langfuse
    trace = state.get("langfuse_trace")
    if trace:
        log_llm_generation(
            trace=trace,
            name="generate_response",
            model="deepseek-chat",
            input_messages=messages,
            output_content=reply,
            usage=usage,
            metadata={"temperature": 0.7},
            prompt=instruction_prompt if instruction_prompt else None,
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
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                    **optimization_headers  # Headers de otimização
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

    # Log to Langfuse
    trace = state.get("langfuse_trace")
    if trace:
        log_llm_generation(
            trace=trace,
            name="revise_response",
            model="deepseek-chat",
            input_messages=[{"role": "user", "content": prompt}],
            output_content=revised,
            usage=usage,
            metadata={"temperature": 0.5},
            prompt=revise_prompt if revise_prompt else None,
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
    Resposta educada para perguntas fora do escopo, sem gastar com API
    """
    language = state.get("language", "pt-BR")
    
    # Respostas por idioma
    responses = {
        "pt-BR": (
            "Desculpe, sou um assistente especializado em soluções digitais da WB Digital Solutions. "
            "Posso ajudar com informações sobre:\n\n"
            "🌐 **Desenvolvimento de Sites** (e-commerce, institucional, landing pages)\n"
            "🤖 **Automação de Processos** (chatbots, integração de sistemas)\n"
            "🧠 **Soluções com IA** (análise de dados, machine learning)\n"
            "💰 **Orçamentos e Prazos** para projetos digitais\n\n"
            "Como posso ajudar com seus projetos digitais hoje?"
        ),
        "en": (
            "Sorry, I'm a specialized assistant for WB Digital Solutions' digital services. "
            "I can help you with:\n\n"
            "🌐 **Website Development** (e-commerce, corporate, landing pages)\n"
            "🤖 **Process Automation** (chatbots, system integration)\n"
            "🧠 **AI Solutions** (data analysis, machine learning)\n"
            "💰 **Quotes and Timelines** for digital projects\n\n"
            "How can I help with your digital projects today?"
        ),
        "es": (
            "Lo siento, soy un asistente especializado en soluciones digitales de WB Digital Solutions. "
            "Puedo ayudarte con:\n\n"
            "🌐 **Desarrollo Web** (e-commerce, corporativo, landing pages)\n"
            "🤖 **Automatización de Procesos** (chatbots, integración de sistemas)\n"
            "🧠 **Soluciones con IA** (análisis de datos, machine learning)\n"
            "💰 **Presupuestos y Plazos** para proyectos digitales\n\n"
            "¿Cómo puedo ayudarte con tus proyectos digitales hoy?"
        ),
        "it": (
            "Mi dispiace, sono un assistente specializzato in soluzioni digitali di WB Digital Solutions. "
            "Posso aiutarti con:\n\n"
            "🌐 **Sviluppo Web** (e-commerce, aziendale, landing page)\n"
            "🤖 **Automazione Processi** (chatbot, integrazione sistemi)\n"
            "🧠 **Soluzioni AI** (analisi dati, machine learning)\n"
            "💰 **Preventivi e Tempi** per progetti digitali\n\n"
            "Come posso aiutarti con i tuoi progetti digitali oggi?"
        )
    }
    
    # Mapear language code
    lang_map = {"en": "en", "es": "es", "it": "it"}
    response_lang = lang_map.get(language, "pt-BR")
    
    response = responses.get(response_lang, responses["pt-BR"])
    
    return {
        **state,
        "response": response,
        "revised_response": response,
        "step": "generate_off_topic_response",
        "intent": "off_topic"
    }

async def generate_greeting_response(state: dict) -> dict:
    user_input = state.get("user_input", "")
    # Usar o idioma enviado pelo frontend em vez de detectar
    language = state.get("language", "pt-BR")
    current_page = state.get("current_page", "/")
    
    # Mapear language code para langdetect format
    if language == "en":
        detected_lang = "en"
    elif language == "es":
        detected_lang = "es"
    elif language == "it":
        detected_lang = "it"
    else:  # pt-BR or default
        detected_lang = "pt"

    # Adicionar contexto da página na saudação
    page_hint = ""
    if current_page == "/websites":
        page_hint = {"en": "I see you're interested in our web development services!", 
                     "es": "¡Veo que estás interesado en nuestros servicios de desarrollo web!",
                     "it": "Vedo che sei interessato ai nostri servizi di sviluppo web!",
                     "pt": "Vejo que você está interessado em nossos serviços de desenvolvimento web!"}
    elif current_page == "/automation":
        page_hint = {"en": "I see you're exploring our automation solutions!",
                     "es": "¡Veo que estás explorando nuestras soluciones de automatización!",
                     "it": "Vedo che stai esplorando le nostre soluzioni di automazione!",
                     "pt": "Vejo que você está explorando nossas soluções de automação!"}
    elif current_page == "/ai":
        page_hint = {"en": "I see you're interested in AI solutions!",
                     "es": "¡Veo que estás interesado en soluciones de IA!",
                     "it": "Vedo che sei interessato alle soluzioni AI!",
                     "pt": "Vejo que você está interessado em soluções de IA!"}

    # Adicionar contexto da página se disponível
    context_addition = ""
    if page_hint and detected_lang in page_hint:
        context_addition = f" {page_hint[detected_lang]}"

    if detected_lang == "en":
        response = (
            "Hello! 👋 I'm the virtual assistant from WB Digital Solutions. "
            "We help companies grow with fast websites, smart automations, and AI-powered tools."
            f"{context_addition} "
            "Tell me what you're looking for — a quote, a specific service, or just some questions? 😊"
        )

    elif detected_lang == "es":
        response = (
            "¡Hola! 👋 Soy el asistente virtual de WB Digital Solutions. "
            "Ayudamos a las empresas a crecer con sitios web rápidos, automatizaciones inteligentes y soluciones con IA."
            f"{context_addition} "
            "¿En qué puedo ayudarte? ¿Quieres una cotización, información sobre un servicio o tienes alguna duda? 😊"
        )

    elif detected_lang == "it":
        response = (
            "Ciao! 👋 Sono l'assistente virtuale di WB Digital Solutions. "
            "Aiutiamo le aziende a crescere con siti web veloci, automazioni intelligenti e soluzioni basate sull'intelligenza artificiale."
            f"{context_addition} "
            "Dimmi come posso aiutarti — vuoi un preventivo, informazioni su un servizio, o hai delle domande? 😊"
        )

    else:
        response = (
            "Olá! 👋 Sou o assistente da WB Digital Solutions. "
            "Criamos sites, automações e soluções com IA para empresas crescerem. "
            f"{context_addition} "
            "Como posso ajudar você hoje? 💬 WhatsApp (11) 98286-4581 - resposta em 2h!"
        )

    return {
        **state,
        "response": response,
        "revised_response": response,
        "step": "generate_greeting_response"
    }



