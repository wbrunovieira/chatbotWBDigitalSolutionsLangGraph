# main.py
from fastapi import FastAPI, Request
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
from graph_config import graph
import os
import logging
from dotenv import load_dotenv
from config import QDRANT_HOST, QDRANT_API_KEY
from nodes import compute_embedding  
import time

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
        col_logs = qdrant.get_collection(collection_name="chat_logs")
        current_dim = None
        if hasattr(col_logs, "config") and col_logs.config and hasattr(col_logs.config, "vectors"):
            current_dim = col_logs.config.vectors.size
        if current_dim != 384:
            logging.info("Collection 'chat_logs' has dimension %s (expected 384). Deleting and recreating...", current_dim)
            qdrant.delete_collection(collection_name="chat_logs")
            raise Exception("Recreate collection")
    except Exception as e:
        logging.info("Collection 'chat_logs' not found or recreated. Creating collection...")
        qdrant.create_collection(
            collection_name="chat_logs",
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )
    
 
    try:
        col_info = qdrant.get_collection(collection_name="company_info")
        current_dim = None
        if hasattr(col_info, "config") and col_info.config and hasattr(col_info.config, "vectors"):
            current_dim = col_info.config.vectors.size
        if current_dim != 384:
            logging.info("Collection 'company_info' has dimension %s (expected 384). Deleting and recreating...", current_dim)
            qdrant.delete_collection(collection_name="company_info")
            raise Exception("Recreate collection")
    except Exception as e:
        logging.info("Collection 'company_info' not found or recreated. Creating collection and upserting company info...")
        qdrant.create_collection(
            collection_name="company_info",
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )
        try:
            with open("company_info.md", "r", encoding="utf-8") as f:
                info = f.read()
        except Exception as ex:
            logging.error("Error reading company_info.md: %s", ex)
            info = "No company information available."
        embedding = compute_embedding(info)
        point = {
            "id": 1,
            "vector": embedding,
            "payload": {"company_info": info}
        }
        qdrant.upsert(collection_name="company_info", points=[point])

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