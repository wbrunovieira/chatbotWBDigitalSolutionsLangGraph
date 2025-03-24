# main.py
from fastapi import FastAPI, Request
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
from graph_config import graph
import os
import logging
from dotenv import load_dotenv
from config import QDRANT_HOST, QDRANT_API_KEY

load_dotenv()

app = FastAPI()

@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    user_input = body.get("message")
    user_id = body.get("user_id", "anon")


    qdrant = QdrantClient(
        url=QDRANT_HOST,
        api_key=QDRANT_API_KEY,
    )


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