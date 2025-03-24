# nodes.py
import httpx
import re
import time
import logging
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
from config import DEEPSEEK_API_KEY

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

async def generate_response(state: dict) -> dict:
    messages = state.get("messages", []) + [{"role": "user", "content": state["user_input"]}]
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
    
    point = {
        "id": int(time.time()),
        "vector": [0.0] * 128,  
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