# main.py
import hmac
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from graph_config import graph
import logging
from dotenv import load_dotenv
import config
from config import QDRANT_HOST, QDRANT_API_KEY
from nodes import compute_embedding
from cache import get_cached_response, set_cached_response
from hashlib import sha256
import time
from deepseek_optimizer import (
    DeepSeekOptimizer,
    begin_request_cost,
    get_request_cost,
)
from security import enforce_chat_limits, record_spend, get_spend_snapshot
import tools
from langfuse_client import create_trace, update_trace, flush_langfuse, evaluate_response, score_trace

load_dotenv()


def docs_kwargs(is_production: bool) -> dict:
    """
    FastAPI() kwargs controlling the interactive docs.

    In production the Swagger UI (/docs), ReDoc (/redoc) and the OpenAPI schema
    (/openapi.json) are turned off: they hand an attacker a full map of the API.
    Outside production they stay on (framework defaults) for development.
    """
    if is_production:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {}


app = FastAPI(**docs_kwargs(config.IS_PRODUCTION))


async def require_admin(authorization: str = Header(default="")) -> None:
    """
    Guard for operator-only endpoints. Expects `Authorization: Bearer <ADMIN_API_TOKEN>`.

    A static bearer token is appropriate here (unlike /chat): this is called
    server-to-server by the operator, never from the browser, so the token never
    ships to a client. Fails closed if no token is configured, and uses a
    constant-time comparison so it can't be brute-forced by timing.
    """
    expected = config.ADMIN_API_TOKEN
    if not expected:
        logging.error("ADMIN_API_TOKEN is not configured; refusing admin endpoint access")
        raise HTTPException(status_code=401, detail="Unauthorized")

    prefix = "Bearer "
    provided = authorization[len(prefix):] if authorization.startswith(prefix) else ""
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


class ChatRequest(BaseModel):
    """
    The payload the site widget posts. Field names and defaults ARE the contract with
    the frontend — changing them breaks the live chat.

    - extra="ignore": the site can add a field without 422-ing the backend.
    - coerce_numbers_to_str: some widget builds send Date.now() / numeric ids.
    - The length caps are the real point: before them, nginx accepted a 10MB body and
      one /chat request fanned it out into up to 3 DeepSeek calls.
    """

    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)

    message: str
    user_id: str = Field(default="anon", max_length=128)
    language: str = Field(default="pt-BR", max_length=16)
    current_page: str = Field(default="/", max_length=256)
    page_url: str = Field(default="", max_length=2048)
    timestamp: Any = ""

    @model_validator(mode="before")
    @classmethod
    def treat_null_as_missing(cls, data: Any) -> Any:
        # The old handler read the body with body.get(key, default), so an explicit
        # null behaved exactly like an absent key. Preserve that, or a widget that
        # sends "page_url": null starts getting 422s.
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if value is not None}
        return data

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        # Read from `config` at validation time (not as a Field(max_length=...) bound
        # at class-definition time) so MAX_MESSAGE_LENGTH stays runtime-configurable.
        value = value.strip()
        if not value:
            raise ValueError("message must not be empty")
        if len(value) > config.MAX_MESSAGE_LENGTH:
            raise ValueError(f"message must be at most {config.MAX_MESSAGE_LENGTH} characters")
        return value


@app.on_event("shutdown")
async def shutdown_event():
    """Flush Langfuse on app shutdown."""
    flush_langfuse()

# CORS configuration - permitir apenas domínios específicos.
# FastAPI is the single source of CORS headers; nginx no longer adds its own.
# allow_credentials is False (the chatbot uses no cookies, so reflecting credentials
# was pure downside), and only the verbs the widget actually uses are allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.wbdigitalsolutions.com",
        "https://wbdigitalsolutions.com",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:8000"
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/chat")
async def chat(payload: ChatRequest, client_ip: str = Depends(enforce_chat_limits)):
    # enforce_chat_limits already raised 429/503 if this IP is over its rate limit or
    # the daily budget is spent. Being here means the request is allowed to cost money.
    begin_request_cost()
    tools.set_client_ip(client_ip)  # so create_lead can enforce a per-IP lead cap
    try:
        return await _handle_chat(payload)
    finally:
        # In a finally block so a request that dies mid-graph still bills whatever
        # DeepSeek calls it already made — a crashing request is not a free one.
        await record_spend(client_ip, get_request_cost())


async def _handle_chat(payload: ChatRequest):
    user_input = payload.message
    user_id = payload.user_id
    language = payload.language
    current_page = payload.current_page
    page_url = payload.page_url
    timestamp = payload.timestamp

    # Log dos dados recebidos para debug
    logging.info(f"Request received - User: {user_id}, Language: {language}, Page: {current_page}")

    # VERIFICAÇÃO: Cache Redis para mensagens exatas (mantido para performance)
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

    # Create Langfuse trace for this chat interaction
    langfuse_trace = create_trace(
        name="chatbot-interaction",
        user_id=user_id,
        session_id=user_id,
        input_data={"message": user_input, "language": language, "current_page": current_page},
        metadata={"page_url": page_url, "page_context": page_context},
    )

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
        "qdrant_client": qdrant,
        "langfuse_trace": langfuse_trace,
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

    # Update Langfuse trace with final output
    update_trace(
        langfuse_trace,
        output={"response": full_response, "intent": result.get("intent")},
        metadata={"final_step": result.get("step"), "cached": False},
    )

    # Run evaluation asynchronously (non-blocking)
    # Only evaluate non-cached responses that went through LLM
    if langfuse_trace and result.get("step") not in ["cached_response", "revision_skipped"]:
        try:
            await evaluate_response(
                trace=langfuse_trace,
                user_input=user_input,
                response=full_response,
                intent=result.get("intent", "unknown"),
                llm_client=True,  # Enable LLM evaluation
            )
        except Exception as e:
            logging.warning(f"Evaluation failed: {e}")

    await set_cached_response(cache_key, response_data)

    return response_data


@app.get("/usage-report")
async def get_usage_report(_: None = Depends(require_admin)):
    """Relatório de uso e custos da API DeepSeek. Operator-only (see require_admin)."""
    report = DeepSeekOptimizer.get_usage_report()
    return {
        "status": "success",
        "report": report,
        "spend": await get_spend_snapshot(),
        "message": f"{'🎉 Desconto de 50% ATIVO!' if report['current_discount'] else '⚠️ Fora do horário de desconto'}"
    }

