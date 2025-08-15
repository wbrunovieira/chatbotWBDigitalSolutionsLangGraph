# main.py
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
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
from cached_responses import detect_cached_intent
from hashlib import sha256
import time
import asyncio
import json as json_lib
from deepseek_optimizer import DeepSeekOptimizer

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
    
    # PRIMEIRA VERIFICAÇÃO: Cache de respostas frequentes (< 100ms)
    cached_intent = detect_cached_intent(user_input, language)
    if cached_intent:
        logging.info(f"Cache hit for pattern: {cached_intent['cache_key']}")
        return {
            "raw_response": cached_intent["response"],
            "revised_response": cached_intent["response"],
            "response_parts": cached_intent["response_parts"],
            "detected_intent": cached_intent["intent"],
            "final_step": "cached_response",
            "language_used": language,
            "context_page": current_page,
            "is_greeting": False,
            "cached": True,
            "cache_type": "pattern_match"
        }

    # SEGUNDA VERIFICAÇÃO: Cache Redis para mensagens exatas
    cache_data = f"{user_input}_{language}_{current_page}"
    cache_key = sha256(cache_data.encode('utf-8')).hexdigest()

    cached_result = await get_cached_response(cache_key)
    if cached_result:
        return {**cached_result, "cached": True, "cache_type": "redis"}



    qdrant = QdrantClient(
        url=QDRANT_HOST,
        api_key=QDRANT_API_KEY,
    )


    try:
        col_logs = qdrant.get_collection(collection_name="chat_logs")
        # Coleção existe, não precisa fazer nada
    except Exception as e:
        # Coleção não existe, criar
        logging.info("Collection 'chat_logs' not found. Creating collection...")
        try:
            qdrant.create_collection(
                collection_name="chat_logs",
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)
            )
        except Exception as create_error:
            # Se falhar ao criar, provavelmente já existe
            logging.info("Collection 'chat_logs' already exists or error creating: %s", create_error)
    
 
    try:
        col_info = qdrant.get_collection(collection_name="company_info")
        # Verificar se já tem dados
        points_count = col_info.points_count if hasattr(col_info, 'points_count') else 0
        if points_count == 0:
            # Coleção existe mas está vazia, adicionar dados
            logging.info("Collection 'company_info' is empty. Adding company data...")
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
    except Exception as e:
        # Coleção não existe, criar e adicionar dados
        logging.info("Collection 'company_info' not found. Creating and adding data...")
        try:
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
        except Exception as create_error:
            logging.info("Error with company_info collection: %s", create_error)

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


    # Estruturar resposta para permitir exibição natural no frontend
    # Dividir resposta em partes se for muito longa
    full_response = result.get("revised_response", result.get("response", ""))
    
    # Para saudações simples, enviar resposta estruturada
    response_parts = []
    if result.get("intent") == "greeting":
        # Dividir saudação em partes naturais
        lines = full_response.split(".")
        for line in lines:
            if line.strip():
                response_parts.append(line.strip() + ".")
    else:
        # Para outras respostas, dividir em parágrafos ou frases
        # Preservar quebras de linha e estrutura
        paragraphs = full_response.split("\n\n")
        for para in paragraphs:
            if para.strip():
                response_parts.append(para.strip())
    
    response_data = {
        "raw_response": result.get("response"),
        "revised_response": full_response,
        "response_parts": response_parts,  # Array de partes da mensagem
        "detected_intent": result.get("intent"),
        "final_step": result.get("step"),
        "language_used": language,
        "context_page": current_page,
        "is_greeting": result.get("intent") == "greeting",
        "cached": False
    }


    await set_cached_response(cache_key, response_data)

    return response_data


@app.post("/chat/stream")
async def chat_stream(request: Request):
    """Endpoint de streaming para respostas mais naturais"""
    body = await request.json()
    
    # Extrair campos
    user_input = body.get("message")
    user_id = body.get("user_id", "anon") 
    language = body.get("language", "pt-BR")
    current_page = body.get("current_page", "/")
    
    async def generate():
        # Primeiro evento: confirmação de recebimento
        yield f"data: {json_lib.dumps({'type': 'acknowledgment', 'message': 'Recebi sua mensagem! 😊'})}\n\n"
        await asyncio.sleep(0.5)
        
        # Processar mensagem (chamar o fluxo normal)
        # Aqui você processaria a mensagem normalmente
        # Por simplicidade, vamos simular uma resposta
        
        # Segundo evento: processando
        yield f"data: {json_lib.dumps({'type': 'thinking', 'message': 'Estou pensando na melhor resposta...'})}\n\n"
        await asyncio.sleep(1)
        
        # Terceiro evento: resposta final em partes
        if "oi" in user_input.lower() or "olá" in user_input.lower():
            # Saudação em partes
            parts = [
                "Olá! 👋 Eu sou o assistente virtual da WB Digital Solutions.",
                "Ajudamos empresas a crescer com sites rápidos, automações inteligentes e soluções com IA.",
                "Me conta o que você precisa — um orçamento, saber mais sobre algum serviço ou tirar dúvidas? 😊"
            ]
            
            for i, part in enumerate(parts):
                yield f"data: {json_lib.dumps({'type': 'message', 'content': part, 'part': i+1, 'total': len(parts)})}\n\n"
                await asyncio.sleep(0.8)  # Delay natural entre partes
        
        # Evento final
        yield f"data: {json_lib.dumps({'type': 'complete', 'message': 'Resposta completa'})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/usage-report")
async def get_usage_report():
    """Endpoint para visualizar relatório de uso e custos da API DeepSeek"""
    report = DeepSeekOptimizer.get_usage_report()
    return {
        "status": "success",
        "report": report,
        "message": f"{'🎉 Desconto de 50% ATIVO!' if report['current_discount'] else '⚠️ Fora do horário de desconto'}"
    }