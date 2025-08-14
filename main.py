# main.py
from fastapi import FastAPI, Request
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
from fastapi.middleware.cors import CORSMiddleware
from graph_config import graph
import os
import logging
from dotenv import load_dotenv
from config import QDRANT_HOST, QDRANT_API_KEY
from nodes import compute_embedding  
from cache import get_cached_response, set_cached_response
from hashlib import sha256
import time

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    
    # Extrair todos os campos enviados pelo frontend
    user_input = body.get("message")
    user_id = body.get("user_id", "anon")
    language = body.get("language", "pt-BR")
    current_page = body.get("current_page", "/")
    page_url = body.get("page_url", "")
    timestamp = body.get("timestamp", "")
    
    # Log dos dados recebidos para debug
    logging.info(f"Request received - User: {user_id}, Language: {language}, Page: {current_page}")

    # Cache key inclui página e idioma para respostas contextualizadas
    cache_data = f"{user_input}_{language}_{current_page}"
    cache_key = sha256(cache_data.encode('utf-8')).hexdigest()

    cached_result = await get_cached_response(cache_key)
    if cached_result:
        return {**cached_result, "cached": True}



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

    # Criar contexto enriquecido com base na página
    page_context = ""
    if current_page == "/websites":
        page_context = "O usuário está vendo a página de serviços de desenvolvimento web"
    elif current_page == "/automation":
        page_context = "O usuário está interessado em automação de processos"
    elif current_page == "/ai":
        page_context = "O usuário está explorando soluções de IA e Machine Learning"
    elif current_page == "/contact":
        page_context = "O usuário está na página de contato"
    elif current_page.startswith("/blog"):
        page_context = "O usuário está lendo o blog"
    else:
        page_context = "O usuário está na página inicial"

    state = {
        "user_input": user_input,
        "user_id": user_id,
        "language": language,
        "current_page": current_page,
        "page_context": page_context,
        "messages": [],
        "memory": {},
        "metadata": {
            "page_url": page_url,
            "timestamp": timestamp,
            "language": language,
            "current_page": current_page
        },
        "qdrant_client": qdrant
    }

    result = await graph.ainvoke(state)


    response_data = {
        "raw_response": result.get("response"),
        "revised_response": result.get("revised_response"),
        "detected_intent": result.get("intent"),
        "final_step": result.get("step"),
        "language_used": language,
        "context_page": current_page,
        "cached": False
    }


    await set_cached_response(cache_key, response_data)

    return response_data