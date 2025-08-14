# nodes.py
import httpx
import re
import time
import logging
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
from config import DEEPSEEK_API_KEY, EVOLUTION_API_URL, EVOLUTION_API_KEY, MY_WHATSAPP_NUMBER
from sentence_transformers import SentenceTransformer
from langdetect import detect


embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

def compute_embedding(text: str) -> list:
    """
    Computes a real embedding for the given text using Sentence Transformers.
    Returns a list of floats.
    """
    embedding = embedding_model.encode(text)
    return embedding.tolist()


async def detect_intent(state: dict) -> dict:
    user_input = state["user_input"]
    lower_input = user_input.lower()

    phone_pattern = r'(\+?\d{1,3}\s?)?(\(?\d{2}\)?\s?)?\d{4,5}[- ]?\d{4}'
    email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'

    if any(p in lower_input for p in ["falar com um humano", "fale com um humano", "humano", "quero falar com alguém"]):
        intent = "chat_with_agent"
    elif any(p in lower_input for p in ["solicitar orçamento", "quero um orçamento", "fazer um orçamento"]):
        intent = "request_quote"
    elif any(p in lower_input for p in ["ver serviços", "quais serviços", "serviços disponíveis"]):
        intent = "inquire_services"
    elif re.search(phone_pattern, user_input) or re.search(email_pattern, user_input):
        intent = "share_contact"
    else:

        prompt = f"""
        Your task is to classify the user's intent based on their message.

        Ignore typos, slang, missing punctuation, and spacing issues.

        Choose only ONE intent from the following list:

        - "greeting" — user is just saying hello.
        - "inquire_services" — user wants to know what services are offered.
        - "request_quote" — user asks for pricing, quote, or how much something costs.
        - "chat_with_agent" — user wants to talk to a human or support agent.
        - "schedule_meeting" — user wants to book or urgently request a meeting or call.
        - "share_contact" — user provides an email or phone number.

        Message:
        "{user_input}"

        Intent:
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1
                    }
                )
                data = response.json()
                raw_intent = data["choices"][0]["message"]["content"].strip().lower()
                intent = raw_intent if raw_intent in {"greeting","request_quote", "inquire_services", "chat_with_agent", "schedule_meeting"} else "inquire_services"
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
    
    Current Context:
    - User is on page: {current_page}
    - {page_context}
    {page_specific_context}
    
    If the user's question clearly indicates interest in requesting a quote, detailed pricing, project specifics, or hiring services directly, explicitly ask the user to provide their WhatsApp number or email so that our team can quickly contact them directly.
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


    instruction = (
        "Before answering, always make sure to:\n"
        "Preserve the original language user\'s original language' "
        "- Ignore typos, missing punctuation, or spacing errors in the user's message.\n"
        "- Focus on understanding the user's intent as clearly as possible, even if the text is informal or has small issues.\n\n"
    )


    query = f"{instruction}{augmented_input}" if augmented_input else f"{instruction}{user_input}"

    messages = state.get("messages", []) + [{"role": "user", "content": query}]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
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
    reply = data["choices"][0]["message"]["content"]

    return {
        **state,
        "response": reply,
        "messages": messages + [{"role": "assistant", "content": reply}],
        "step": "generate_response"
    }
async def revise_response(state: dict) -> dict:
    prompt = (
        "Rewrite the following response to make it clearer and friendlier, keeping a professional tone. "
        "Do NOT include any explanations, introductions, or markdown (like asterisks or hashtags). "
        "Your output must contain only the final response with natural paragraph spacing. "
        "Preserve the original language of the response. "
        "Limit the response to a maximum of 600 characters, ending naturally."
        "Reply only with the improved text — do not include any extra explanations, titles, or labels like 'Response:'.\n\n"
        f"{state['response']}"
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
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
    revised = data["choices"][0]["message"]["content"]
    revised = revised.replace('\n\n', '\n').replace('\n', '\n\n') 
    return {**state, "revised_response": revised, "step": "revise_response"}

async def save_log_qdrant(state: dict) -> dict:
    data_to_save = {
        "user_id": state.get("user_id"),
        "user_input": state.get("user_input"),
        "response": state.get("response"),
        "revised_response": state.get("revised_response"),
        "intent": state.get("intent"),
        "messages": state.get("messages")
    }
    logging.info("Saving to Qdrant: %s", data_to_save)
    print("Data sent to Qdrant:", data_to_save)
    

    combined_text = (
        f"User ID: {data_to_save.get('user_id', '')}\n"
        f"User Input: {data_to_save.get('user_input', '')}\n"
        f"Response: {data_to_save.get('response', '')}\n"
        f"Revised Response: {data_to_save.get('revised_response', '')}\n"
        f"Intent: {data_to_save.get('intent', '')}"
    )
    log_embedding = compute_embedding(combined_text)  
    point = {
        "id": int(time.time()),
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

async def send_contact_whatsapp(state: dict) -> dict:
    user_contact = state["user_input"]  
    user_id = state["user_id"]

    message = f"📥 *Novo contato recebido pelo chatbot!*\n\nUsuário: {user_id}\nContato fornecido: {user_contact}"

    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "number": MY_WHATSAPP_NUMBER,
        "text": message
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
          response = await client.post(EVOLUTION_API_URL, headers=headers, json=payload)
          response.raise_for_status()
        success_message = "Thanks for sharing your contact! Our team will contact you shortly. 🚀"
    except Exception as e:
        logging.error(f"Error sending contact via WhatsApp: {e}")
        success_message = "There was an issue sending your contact, please contact us directly."

    return {
        **state,
        "response": success_message,
        "step": "send_contact_whatsapp"
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
            "Olá! 👋 Eu sou o assistente virtual da WB Digital Solutions. "
            "Ajudamos empresas a crescer com sites rápidos, automações inteligentes e soluções com IA."
            f"{context_addition} "
            "Me conta o que você precisa — um orçamento, saber mais sobre algum serviço ou tirar dúvidas? 😊"
        )

    return {
        **state,
        "response": response,
        "revised_response": response,
        "step": "generate_greeting_response"
    }



