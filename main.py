# main.py
import asyncio
import hmac
import random
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from qdrant_client.http.models import VectorParams, Distance
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from graph_config import graph, evict_thread
import logging
from dotenv import load_dotenv
import config
import ingest
from db import get_qdrant_client
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
import guardrails
from language import resolve_language
from langfuse_client import create_trace, update_trace, flush_langfuse, evaluate_response, score_trace, set_current_trace

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: ensure the Qdrant collections exist and the knowledge base is ingested as
    chunks (idempotent — cheap when unchanged). Moving this out of the /chat hot path means
    a request no longer re-checks/creates collections on every call. Shutdown: flush Langfuse.
    """
    try:
        client = get_qdrant_client()
        # Centralized collection init. collection_exists() returns a bool, so we create only
        # on a genuine miss — auth/network errors raise and are caught below (degrade, don't
        # crash-loop) rather than being mistaken for "missing" and triggering a blind create.
        for name in ("chat_logs", "company_info"):
            if not client.collection_exists(collection_name=name):
                client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                )
        result = ingest.ingest_company_info(client)
        logging.info("Startup KB ingest: %s", result)
    except Exception as exc:  # never let startup init crash the app
        logging.error("Startup init failed (continuing): %s", exc)
    yield
    flush_langfuse()


app = FastAPI(lifespan=lifespan, **docs_kwargs(config.IS_PRODUCTION))


def _memory_thread_id(user_id: str) -> str:
    """
    Checkpointer thread key for conversation memory. A real user_id keys stable per-
    conversation memory; a SHARED/anonymous id (the "anon" default) must NOT share a thread
    — that would leak one visitor's conversation to another — so it gets an ephemeral,
    per-request thread (isolated, effectively no cross-request memory) until the frontend
    sends a stable per-session id.
    """
    if user_id in config.SHARED_USER_IDS:
        return f"ephemeral-{uuid.uuid4()}"
    return user_id


def split_greeting_bubbles(text: str) -> list:
    """
    Split a greeting into natural chat bubbles by sentence, KEEPING each sentence's own
    terminal punctuation. The previous approach (split on "." then re-append ".") mangled a
    greeting that ends on a question ("...no seu negócio?" -> "...negócio?.") and mis-split
    "WB Digital Solutions." mid-name.
    """
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s.strip()]


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


class BehaviorContext(BaseModel):
    """Optional engagement signal the Next.js server may attach (#8b): where the visitor has
    been and how far into the journey they are. Used to score/enrich the lead and lightly
    personalize the answer — never shown to the user. All fields optional so it's contract-safe.
    """

    model_config = ConfigDict(extra="ignore")

    pages_visited: list[str] = Field(default_factory=list, max_length=50)
    journey_score: float | None = None
    geo_country: str | None = Field(default=None, max_length=8)


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
    behavior: BehaviorContext | None = None
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

    @model_validator(mode="before")
    @classmethod
    def normalize_language(cls, data: Any) -> Any:
        # The widget doesn't always send `language` (button clicks post none, some builds
        # send ""), which used to log as language=None and answer in the wrong language.
        # Resolve it here: explicit value, else the page's locale segment, else pt-BR — so
        # every request reaches the graph with a supported code. Order-independent w.r.t.
        # treat_null_as_missing (a stripped/blank language is treated the same as missing).
        if isinstance(data, dict):
            data = dict(data)
            data["language"] = resolve_language(
                data.get("language"),
                data.get("page_url", ""),
                data.get("current_page", ""),
            )
        return data

    @field_validator("behavior", mode="before")
    @classmethod
    def lenient_behavior(cls, value: Any) -> Any:
        # Optional enrichment must NEVER 422 the chat. Pydantic v2 doesn't cascade the
        # parent's coerce_numbers_to_str into nested models, so a numeric page or geo from
        # a frontend serialization bug would fail validation and take the whole request
        # down. Coerce leniently here and drop anything malformed to None.
        if value is None or isinstance(value, BehaviorContext):
            return value
        if not isinstance(value, dict):
            return None
        try:
            cleaned: dict[str, Any] = {}
            pages = value.get("pages_visited")
            if isinstance(pages, list):
                # Cap list length AND each item's length so a massive string can't bloat
                # the state/prompt (truncate, don't reject — enrichment must never 422).
                cleaned["pages_visited"] = [str(p)[:2048] for p in pages if p is not None][:50]
            journey = value.get("journey_score")
            if isinstance(journey, (int, float)) and not isinstance(journey, bool):
                cleaned["journey_score"] = float(journey)
            geo = value.get("geo_country")
            if geo is not None:
                cleaned["geo_country"] = str(geo)[:8]
            return cleaned
        except Exception:  # noqa: BLE001 — enrichment is best-effort; never break chat
            return None

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

# Demo widget: a tiny chat UI served by the app itself (so it shares the origin and
# needs no CORS). Mounted ONLY outside production — it is a showcase surface, never
# something we want reachable on the live host.
if not config.IS_PRODUCTION:
    import os
    from fastapi.staticfiles import StaticFiles

    # Serve only the widget dir, not the whole demo/ (which holds the CRM stub source).
    if os.path.isdir("demo/web"):
        app.mount("/demo", StaticFiles(directory="demo/web", html=True), name="demo")

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/chat")
async def chat(payload: ChatRequest, client_ip: str = Depends(enforce_chat_limits)):
    # enforce_chat_limits already raised 429/503 if this IP is over its rate limit or
    # the daily budget is spent. Being here means the request is allowed to cost money.
    begin_request_cost()
    tools.set_client_ip(client_ip)  # so create_lead can enforce a per-IP lead cap
    tools.set_behavior(payload.behavior)  # so create_lead can score/enrich the lead (#8b)
    try:
        return await _handle_chat(payload)
    finally:
        # In a finally block so a request that dies mid-graph still bills whatever
        # DeepSeek calls it already made — a crashing request is not a free one.
        await record_spend(client_ip, get_request_cost())


# Page -> a short pt-BR context hint fed to the prompts. Data, not branching code.
PAGE_CONTEXTS = {
    "/websites": "O usuário está vendo a página de serviços de desenvolvimento web",
    "/automation": "O usuário está interessado em automação de processos",
    "/ai": "O usuário está explorando soluções de IA e Machine Learning",
    "/contact": "O usuário está na página de contato",
}


def _page_context(current_page: str) -> str:
    if current_page in PAGE_CONTEXTS:
        return PAGE_CONTEXTS[current_page]
    if current_page.startswith("/blog"):
        return "O usuário está lendo o blog"
    return "O usuário está na página inicial"


def _build_state(payload: ChatRequest, page_context: str) -> dict:
    # No "messages" on purpose — the checkpointer holds the accumulated conversation history
    # per thread_id; passing [] would clobber it each turn.
    return {
        "user_input": payload.message,
        "user_id": payload.user_id,
        "language": payload.language,
        "current_page": payload.current_page,
        "page_context": page_context,
        "behavior": payload.behavior.model_dump() if payload.behavior else None,
        "memory": {},
        "metadata": {
            "page_url": payload.page_url,
            "timestamp": payload.timestamp,
            "language": payload.language,
            "current_page": payload.current_page,
        },
    }


def _shape_response(result: dict, language: str, current_page: str) -> dict:
    """The fixed response shape the widget reads. Greetings split into bubbles; other
    answers split on blank lines."""
    full_response = result.get("revised_response", result.get("response", ""))
    if result.get("intent") == "greeting":
        response_parts = split_greeting_bubbles(full_response)
    else:
        response_parts = [p.strip() for p in full_response.split("\n\n") if p.strip()]
    return {
        "raw_response": result.get("response"),
        "revised_response": full_response,
        "response_parts": response_parts,
        "detected_intent": result.get("intent"),
        "final_step": result.get("step"),
        "language_used": language,
        "context_page": current_page,
        "is_greeting": result.get("intent") == "greeting",
        "cached": False,
    }


# Strong refs to in-flight background judge tasks so they aren't garbage-collected before
# they finish (asyncio only keeps weak refs); each removes itself on completion.
_BACKGROUND_TASKS: set = set()


async def _run_judge(langfuse_trace, user_input: str, response: str, intent: str) -> None:
    try:
        await evaluate_response(
            trace=langfuse_trace,
            user_input=user_input,
            response=response,
            intent=intent,
            llm_client=True,
        )
    except Exception as exc:
        logging.warning("Evaluation failed: %s", exc)


def _maybe_schedule_judge(langfuse_trace, user_input: str, response: str, result: dict) -> None:
    """Sample ~JUDGE_SAMPLE_RATE of LLM-driven answers and score them in a background task.

    Keeps the second LLM call off the request path (the visitor never waits on it). No-op
    when Langfuse is disabled (no trace) or for hardcoded greetings, which have no generated
    answer worth scoring.

    Note: because this runs after the request's spend is recorded, the judge's own token
    cost is not billed against the daily/per-IP cap. Moot while Langfuse is disabled (trace
    is None → no-op); revisit the spend accounting if the judge is ever turned on.
    """
    if not langfuse_trace or result.get("intent") == "greeting":
        return
    if random.random() >= config.JUDGE_SAMPLE_RATE:
        return
    task = asyncio.create_task(
        _run_judge(langfuse_trace, user_input, response, result.get("intent", "unknown"))
    )
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def _handle_chat(payload: ChatRequest):
    user_id = payload.user_id
    language = payload.language
    current_page = payload.current_page
    logging.info(f"Request received - User: {user_id}, Language: {language}, Page: {current_page}")

    # Exact-match Redis cache. The key includes user_id so one visitor's answer is never
    # served to another (responses are conversation-dependent now that memory exists); we
    # only WRITE the cache for context-free turns (below).
    cache_key = sha256(f"{payload.message}_{language}_{current_page}_{user_id}".encode("utf-8")).hexdigest()
    cached_result = await get_cached_response(cache_key)
    if cached_result:
        return {**cached_result, "cached": True, "cache_type": "redis"}

    page_context = _page_context(current_page)
    langfuse_trace = create_trace(
        name="chatbot-interaction",
        user_id=user_id,
        session_id=user_id,
        input_data={"message": guardrails.redact_pii(payload.message), "language": language, "current_page": current_page},
        metadata={"page_url": payload.page_url, "page_context": page_context},
    )
    # Carry the trace in a ContextVar, not the graph state (a live trace isn't serializable,
    # and the checkpointer serializes the state).
    set_current_trace(langfuse_trace)

    thread_id = _memory_thread_id(user_id)
    # A shared/anon user_id gets a single-use ephemeral thread; evict it after the request
    # (even on error) so the in-process MemorySaver doesn't grow one dead thread per anon
    # request. Key off the SAME predicate _memory_thread_id uses, not the thread_id string.
    is_ephemeral = user_id in config.SHARED_USER_IDS
    try:
        result = await graph.ainvoke(
            _build_state(payload, page_context),
            config={"configurable": {"thread_id": thread_id}},
        )
    finally:
        if is_ephemeral:
            evict_thread(thread_id)

    response_data = _shape_response(result, language, current_page)
    full_response = response_data["revised_response"]

    update_trace(
        langfuse_trace,
        output={"response": guardrails.redact_pii(full_response), "intent": result.get("intent")},
        metadata={"final_step": result.get("step"), "cached": False},
    )

    # LLM-as-judge scoring runs sampled and in the background, never blocking the response.
    _maybe_schedule_judge(langfuse_trace, payload.message, full_response, result)

    # Only cache CONTEXT-FREE turns: once a conversation has history (messages grows 2/turn),
    # the answer depends on it, so caching by message would serve a stale answer. First turn <= 2.
    if len(result.get("messages", [])) <= 2:
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

