from fastapi import FastAPI, Request
from langgraph.graph import StateGraph, END, START
from typing import TypedDict, List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
import httpx
import os
import re
from dotenv import load_dotenv
import logging
import time

# Logging configuration
logging.basicConfig(level=logging.INFO)

load_dotenv()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# -------------------------------
# Define the graph state
# -------------------------------
class GraphState(TypedDict, total=False):
    user_input: str
    response: str
    revised_response: str
    messages: List[Dict[str, str]]
    intent: str
    memory: Dict[str, Any]
    user_id: str
    metadata: Dict[str, Any]
    step: str
    qdrant_client: QdrantClient

# -------------------------------
# Node: Detect intent
# -------------------------------
async def detect_intent(state: GraphState) -> GraphState:
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
    
    # Try to extract the intent between quotes, if possible
    match = re.search(r'"([^"]+)"', raw_intent)
    intent = match.group(1) if match else raw_intent

    # Define the expected intents; if not recognized, use a default
    expected_intents = {"request_quote", "inquire_services", "chat_with_agent", "schedule_meeting"}
    if intent not in expected_intents:
        logging.error("Unrecognized intent: %s. Using 'inquire_services' as default.", intent)
        intent = "inquire_services"
    
    return {**state, "intent": intent, "step": "detect_intent"}

# -------------------------------
# Node: Generate response with DeepSeek
# -------------------------------
async def generate_response(state: GraphState) -> GraphState:
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

# -------------------------------
# Node: Revise response
# -------------------------------
async def revise_response(state: GraphState) -> GraphState:
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

# -------------------------------
# Node: Save log to Qdrant
# -------------------------------
async def save_log_qdrant(state: GraphState) -> GraphState:
    # Extract data to be saved
    data_to_save = {
        "user_id": state.get("user_id"),
        "user_input": state.get("user_input"),
        "response": state.get("response"),
        "revised_response": state.get("revised_response"),
        "intent": state.get("intent"),
        "messages": state.get("messages")
    }
    # Log data before saving
    logging.info("Saving to Qdrant: %s", data_to_save)
    print("Data sent to Qdrant:", data_to_save)
    
    # Example point to save (ensure that the collection 'chat_logs' exists)
    point = {
        "id": int(time.time()),
        "vector": [0.0] * 128,  # dummy vector; adjust as needed
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

# -------------------------------
# Build the graph
# -------------------------------
workflow = StateGraph(GraphState)

workflow.add_node("intent_detection", detect_intent)
workflow.add_node("response_generation", generate_response)
workflow.add_node("response_revision", revise_response)
workflow.add_node("log_saving", save_log_qdrant)

workflow.set_entry_point("intent_detection")

# Route based on intent
workflow.add_conditional_edges(
    "intent_detection",
    lambda state: state.get("intent", ""),
    {
        "request_quote": "response_generation",
        "inquire_services": "response_generation",
        "chat_with_agent": END,
        "schedule_meeting": "response_generation"
    }
)

# After generating response, always revise
workflow.add_edge("response_generation", "response_revision")
# After revision, save log to Qdrant
workflow.add_edge("response_revision", "log_saving")
# End after saving log
workflow.add_edge("log_saving", END)

graph = workflow.compile()

# -------------------------------
# FastAPI application
# -------------------------------
app = FastAPI()

@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    user_input = body.get("message")
    user_id = body.get("user_id", "anon")

    # Instantiate the Qdrant Cloud client
    qdrant = QdrantClient(
        url=os.getenv("QDRANT_HOST"),
        api_key=os.getenv("QDRANT_API_KEY"),
    )

    # Check if the 'chat_logs' collection exists; if not, create it.
    try:
        qdrant.get_collection(collection_name="chat_logs")
    except Exception as e:
        logging.info("Collection 'chat_logs' not found. Creating collection...")
        qdrant.create_collection(
            collection_name="chat_logs",
            vectors_config=VectorParams(size=128, distance=Distance.COSINE)
        )

    state = {
        "user_input": user_input,
        "user_id": user_id,
        "messages": [],
        "memory": {},
        "metadata": {},
        "qdrant_client": qdrant
    }

    result = await graph.ainvoke(state)

    return {
        "raw_response": result.get("response"),
        "revised_response": result.get("revised_response"),
        "detected_intent": result.get("intent"),
        "final_step": result.get("step")
    }