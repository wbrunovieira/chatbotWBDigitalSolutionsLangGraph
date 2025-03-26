# nodes.py
import httpx
import re
import time
import logging
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
from config import DEEPSEEK_API_KEY
from sentence_transformers import SentenceTransformer

# Carrega o modelo de embedding uma única vez
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

def compute_embedding(text: str) -> list:
    """
    Computes a real embedding for the given text using Sentence Transformers.
    Returns a list of floats.
    """
    embedding = embedding_model.encode(text)
    return embedding.tolist()

async def detect_intent(state: dict) -> dict:
    prompt = f"""
    Classify the intent of this message in one keyword:
    "{state['user_input']}"
    Possible intents: inquire_services, request_quote, chat_with_agent, schedule_meeting
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
                    "temperature": 0.5
                }
            )
    except httpx.ReadTimeout:
        logging.error("Request timed out in DeepSeek API call for intent detection")
        return {**state, "response": "Sorry, the service is taking too long to respond. Please try again later.", "step": "error_timeout"}
    
    data = response.json()
    raw_intent = data["choices"][0]["message"]["content"].strip()
    
    match = re.search(r'"([^"]+)"', raw_intent)
    intent = match.group(1) if match else raw_intent

    expected_intents = {"request_quote", "inquire_services", "chat_with_agent", "schedule_meeting"}
    if intent not in expected_intents:
        logging.error("Unrecognized intent: %s. Using 'inquire_services' as default.", intent)
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
    
    augmented = f"""
    You are an assistant from WB Digital Solutions, a company specialized in creating premium custom websites, business automation, and AI-driven solutions.

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
    query = state.get("augmented_input", state["user_input"])
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
    prompt = f"Rewrite the following response to make it clearer and friendlier:\n\n{state['response']}"
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
    
    # Combine key log fields into one text for semantic embedding
    combined_text = (
        f"User ID: {data_to_save.get('user_id', '')}\n"
        f"User Input: {data_to_save.get('user_input', '')}\n"
        f"Response: {data_to_save.get('response', '')}\n"
        f"Revised Response: {data_to_save.get('revised_response', '')}\n"
        f"Intent: {data_to_save.get('intent', '')}"
    )
    log_embedding = compute_embedding(combined_text)  # Now returns a vector of dimension 384
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