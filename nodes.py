# nodes.py
import httpx
import json
import re
import time
import uuid
import logging
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
from config import DEEPSEEK_API_KEY, COMPANY_TOP_K, COMPANY_SCORE_THRESHOLD
from fastembed import TextEmbedding
from langdetect import detect
from deepseek_optimizer import DeepSeekOptimizer, estimate_tokens, should_skip_api_call
from langfuse_client import start_llm_generation, end_llm_generation, get_prompt, evaluate_response, score_trace, update_trace
import tools
import guardrails
from db import get_qdrant_client


# FastEmbed - lightweight ONNX-based embeddings (no PyTorch required).
#
# Built lazily: instantiating TextEmbedding downloads the ONNX model, and doing that
# at import time means merely importing this module hits the network.
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_embedding_model = None


def get_embedding_model() -> TextEmbedding:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = TextEmbedding(EMBEDDING_MODEL_NAME)
    return _embedding_model


def compute_embedding(text: str) -> list:
    """
    Computes embedding using FastEmbed (ONNX-based, no PyTorch).
    Returns a list of floats with 384 dimensions.
    """
    # Limitar o texto para evitar problemas de performance
    max_length = 512
    if len(text) > max_length * 4:
        text = text[:max_length * 4]

    # FastEmbed retorna um generator, pegamos o primeiro resultado
    embeddings = list(get_embedding_model().embed([text]))
    return embeddings[0].tolist()


# Order matters: off_topic is LAST so that if a service word also appears we prefer the
# service intent — a sales bot must never deflect a real inquiry to off_topic.
VALID_INTENTS = [
    "greeting",
    "request_quote",
    "inquire_services",
    "share_contact",
    "chat_with_agent",
    "off_topic",
]
DEFAULT_INTENT = "inquire_services"


def _exact_intent(value) -> str | None:
    if isinstance(value, str) and value.strip().lower() in VALID_INTENTS:
        return value.strip().lower()
    return None


def parse_intent(raw: str) -> str:
    """
    Robustly extract the intent from the classifier output.

    Tolerant to a JSON object ({"intent": "..."}), a bare word, or messy prose, so the
    code doesn't break if the prompt/response format drifts.

    A structured, exact match wins first: if the model returns
    {"intent": "request_quote", "reason": "not just a greeting"}, we must return
    request_quote — NOT let the word "greeting" inside the reasoning field hijack it.
    Only when there is no exact intent value do we fall back to a greedy substring scan
    over the raw text (off_topic last, so a stray service word wins). Falls back to
    inquire_services rather than off_topic — assuming a service question is the safer
    default for a sales bot.
    """
    if not raw:
        return DEFAULT_INTENT

    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        obj = None

    if isinstance(obj, dict):
        # Prefer the canonical keys, then any value that is exactly a valid intent.
        for key in ("intent", "result", "label", "category"):
            hit = _exact_intent(obj.get(key))
            if hit:
                return hit
        for value in obj.values():
            hit = _exact_intent(value)
            if hit:
                return hit
    else:
        hit = _exact_intent(obj if isinstance(obj, str) else raw)
        if hit:
            return hit

    # Fallback: greedy scan over the raw text only (never the parsed sub-fields).
    norm = re.sub(r"[^a-z]+", "_", raw.lower())
    for intent in VALID_INTENTS:
        if intent in norm:
            return intent
    return DEFAULT_INTENT


async def detect_intent(state: dict) -> dict:
    """
    Detecta intent usando prompt do Langfuse.
    Sem bypass hardcoded - sempre usa o prompt para consistência.
    """
    user_input = state["user_input"]
    language = state.get("language", "pt-BR")
    current_page = state.get("current_page", "/")

    # Get prompt from Langfuse (with local fallback)
    intent_prompt = get_prompt("detect_intent")
    if intent_prompt:
        try:
            prompt = intent_prompt.compile(
                user_input=user_input,
                language=language,
                current_page=current_page,
            )
        except:
            # Fallback se compile falhar (variáveis não existem no prompt)
            prompt = intent_prompt.compile(user_input=user_input)
    else:
        # Hardcoded fallback if no prompt available. Asks for JSON to match the
        # response_format below (DeepSeek's json_object mode requires "json" in the prompt).
        prompt = f"""Classify the intent of this message for a digital-services chatbot: "{user_input}"

A time-of-day greeting ("bom dia", "boa tarde", "boa noite", "good evening") is a
greeting. Anything about websites, e-commerce, automation, AI/agents or e-learning —
even misspelled — is inquire_services (or request_quote if it asks about price), never
off_topic.

Respond with ONLY JSON: {{"intent": "<greeting|request_quote|inquire_services|share_contact|chat_with_agent|off_topic>"}}"""

    intent = "inquire_services"  # default
    trace = state.get("langfuse_trace")

    try:
        optimization_headers = DeepSeekOptimizer.get_optimization_headers()

        # Start generation BEFORE LLM call (captures start time)
        generation = start_llm_generation(
            trace=trace,
            name="detect_intent",
            model="deepseek-chat",
            input_messages=[{"role": "user", "content": prompt}],
            metadata={"temperature": 0.1},
            prompt=intent_prompt,
        )

        request_body = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        # DeepSeek's json_object mode 400s unless the prompt contains the word "json".
        # Only request it when the (possibly Langfuse-served, possibly stale) prompt
        # actually asks for JSON; otherwise let parse_intent handle free text. This
        # keeps a prompt/code mismatch from silently breaking intent detection.
        if "json" in prompt.lower():
            request_body["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                    **optimization_headers
                },
                json=request_body,
            )
        data = response.json()

        usage = data.get("usage", {})
        if usage:
            DeepSeekOptimizer.update_usage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                cache_hit=response.headers.get("X-Cache-Status") == "hit"
            )

        # Guard against API errors (429/500 return JSON without "choices" -> KeyError).
        try:
            raw_intent = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            logging.error("detect_intent: unexpected DeepSeek response: %s", str(data)[:200])
            raw_intent = ""

        intent = parse_intent(raw_intent)

        # End generation AFTER LLM call (captures end time)
        end_llm_generation(
            generation=generation,
            output_content=raw_intent,
            usage=usage,
            metadata={"detected_intent": intent},
        )
    except Exception as e:
        logging.error(f"Error in intent detection: {e}")
        intent = "inquire_services"

    return {**state, "intent": intent, "step": "detect_intent"}

# Top-k retrieval over the chunked knowledge base (see ingest.py). The score threshold
# drops weak matches; cosine similarity, so higher is closer. Retrieval only runs for
# on-topic intents (off_topic short-circuits earlier), so this is a relevance floor, not
# an off-topic filter. Both are env-tunable via config so the threshold can be
# re-calibrated from prod traces; the default suits the multilingual-query / English-KB
# cross-lingual score range (relevant pt->en ~0.20-0.40, off-topic ~0.15).


async def retrieve_company_context(state: dict) -> dict:
    """
    Retrieve the most relevant company-knowledge chunks for the user's query from the
    Qdrant 'company_info' collection: top-k over chunks, above a score threshold, joined
    into the grounding context. The source chunks (section + score) are attached to the
    Langfuse trace as citations and logged, so the threshold can be re-calibrated from
    real traffic.
    """
    embedding = compute_embedding(state["user_input"])
    chunks, sources = [], []
    try:
        results = get_qdrant_client().search(
            collection_name="company_info",
            query_vector=embedding,
            limit=COMPANY_TOP_K,
            score_threshold=COMPANY_SCORE_THRESHOLD,
        )
        for r in results:
            # "text" is the chunked schema; fall back to the legacy single-doc "company_info"
            # key so retrieval keeps working before the first chunked ingest runs.
            text = r.payload.get("text") or r.payload.get("company_info", "")
            if text:
                chunks.append(text)
                sources.append({"section": r.payload.get("section"), "score": round(r.score, 4)})
    except Exception as e:
        logging.error("Error retrieving company context: %s", e)

    logging.info("RAG retrieval for %r -> %s", state.get("user_input", "")[:60], sources)
    company_context = "\n\n---\n\n".join(chunks)
    if sources:
        update_trace(state.get("langfuse_trace"), metadata={"rag_sources": sources})
    return {
        **state,
        "company_context": company_context,
        "rag_sources": sources,
        "step": "retrieve_company_context",
    }

async def retrieve_user_context(state: dict) -> dict:
    """
    Searches the Qdrant collection 'chat_logs' for previous conversations
    from the same user (based on user_id) and combines them into a context.
    """

    query_filter = {"must": [{"key": "user_id", "match": {"value": state.get("user_id")}}]}

    dummy_vector = [0.0] * 384
    try:
        results = get_qdrant_client().search(
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
    """
    Prepara o contexto para geração de resposta usando prompt do Langfuse.
    """
    company_context = state.get("company_context", "")
    user_context = state.get("user_context", "")
    user_input = state.get("user_input", "")
    language = state.get("language", "pt-BR")
    page_context = state.get("page_context", "")
    current_page = state.get("current_page", "/")
    intent = state.get("intent", "inquire_services")

    # Determinar instrução de idioma
    language_instructions = {
        "en": "IMPORTANT: Respond in English.",
        "es": "IMPORTANTE: Responde en español.",
        "it": "IMPORTANTE: Rispondi in italiano.",
        "pt-BR": "IMPORTANTE: Responda em português brasileiro.",
    }
    language_instruction = language_instructions.get(language, language_instructions["pt-BR"])

    # Contexto da página
    page_contexts = {
        "/websites": "User viewing web development services page.",
        "/automation": "User exploring automation services.",
        "/ai": "User interested in AI solutions.",
        "/contact": "User on contact page, ready to reach out.",
    }
    page_specific_context = page_contexts.get(current_page, "User on home page.")

    # Prices are no longer quoted in chat: a price question is a hot lead, so we route
    # it through the same services prompt and let the tool loop capture the lead / offer
    # scheduling instead of giving a number.
    system_prompt = get_prompt("generate_services_response")

    if system_prompt:
        try:
            augmented = system_prompt.compile(
                user_input=user_input,
                language=language,
                language_instruction=language_instruction,
                current_page=current_page,
                page_context=page_specific_context,
                company_context=company_context or "WB Digital Solutions - websites, automation, AI",
                user_context=user_context,
                intent=intent,
            )
        except Exception as e:
            logging.warning(f"Error compiling system prompt: {e}")
            # Fallback simples
            augmented = f"""You are WB Digital Solutions assistant. {language_instruction}
Answer: {user_input}
End with a helpful next step. Do NOT paste a phone number; if the user asks for contact or to talk to someone, offer to connect them with our team or share the booking link."""
    else:
        # Fallback se não encontrar prompt no Langfuse
        augmented = f"""You are WB Digital Solutions assistant specializing in websites, automation, and AI.
{language_instruction}
Context: {company_context}
User question: {user_input}
End with a helpful next step. Do NOT include a phone number or WhatsApp; if the user asks for contact or to talk to a person, offer to connect them with our team or share the booking link."""

    return {**state, "augmented_input": augmented, "step": "augment_query"}

TOOL_SYSTEM_PROMPT = (
    "You are the WB Digital Solutions assistant. You have tools — use them when they fit:\n"
    "- create_lead: when the user shares who they are (name/company) or a contact, or clearly "
    "wants a proposal — capture them as a lead.\n"
    "- schedule_meeting: when the user wants to talk, meet, or get a proposal — give them the booking link.\n"
    "- handoff_to_human: when the user explicitly asks to talk to a person, OR asks for our "
    "contact / WhatsApp / phone / email — this is how they get our contact details.\n"
    "Only pass details the user actually gave; never invent a name, phone or email. Do NOT discuss "
    "prices — if asked about price, capture the lead or offer to schedule instead of giving a number."
)


async def _deepseek_chat(messages: list, temperature: float = 0.7, use_tools: bool = False) -> dict:
    """Single DeepSeek chat call. Returns the parsed JSON. Offers the tools when asked."""
    body = {"model": "deepseek-chat", "messages": messages, "temperature": temperature}
    if use_tools:
        body["tools"] = tools.TOOL_SPECS
        body["tool_choice"] = "auto"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
                **DeepSeekOptimizer.get_optimization_headers(),
            },
            json=body,
        )
    try:
        return resp.json()
    except ValueError:
        # A 5xx that returns HTML instead of JSON — don't crash; the loop's choices-guard
        # then produces a graceful fallback.
        logging.error("DeepSeek returned non-JSON (status %s): %s", resp.status_code, resp.text[:200])
        return {}


async def _run_tool_loop(messages: list, trace, instruction_prompt, max_iters: int = 3):
    """
    Generate a reply, letting the model DECIDE to call tools. Any tool call is executed via
    tools.dispatch (validated + resilient), the result is fed back, and we loop until the
    model returns text (bounded by max_iters). Returns (reply_text, tool_results).
    """
    tool_results = []
    for _ in range(max_iters):
        generation = start_llm_generation(
            trace=trace, name="generate_response", model="deepseek-chat",
            input_messages=messages, metadata={"temperature": 0.7}, prompt=instruction_prompt,
        )
        data = await _deepseek_chat(messages, use_tools=True)
        usage = data.get("usage", {})
        if usage:
            DeepSeekOptimizer.update_usage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            logging.error("generate_response: unexpected DeepSeek response: %s", str(data)[:200])
            end_llm_generation(generation=generation, output_content="", usage=usage)
            return "Desculpe, tive um problema técnico. Fale com a gente no WhatsApp (11) 98286-4581.", tool_results

        end_llm_generation(generation=generation, output_content=msg.get("content") or "", usage=usage)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return msg.get("content") or "", tool_results

        # Record the assistant's tool-call turn, then execute each call and feed results back.
        messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls})
        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except (ValueError, TypeError):
                args = {}
            result = await tools.dispatch(name, args)
            tool_results.append({"tool": name, "result": result})
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": json.dumps(result, ensure_ascii=False)})

    # Still asking for tools after max_iters: force a final text answer (tools off).
    generation = start_llm_generation(
        trace=trace, name="generate_response", model="deepseek-chat",
        input_messages=messages, metadata={"temperature": 0.7}, prompt=instruction_prompt,
    )
    data = await _deepseek_chat(messages, use_tools=False)
    usage = data.get("usage", {})
    if usage:
        DeepSeekOptimizer.update_usage(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )
    try:
        content = data["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        content = "Fale com a gente no WhatsApp (11) 98286-4581!"
    end_llm_generation(generation=generation, output_content=content, usage=usage)
    return content, tool_results


async def generate_response(state: dict) -> dict:
    user_input = state["user_input"]
    augmented_input = state.get("augmented_input")
    trace = state.get("langfuse_trace")

    # Get instruction prompt from Langfuse
    instruction_prompt = get_prompt("generate_response_instruction")
    if instruction_prompt:
        instruction = instruction_prompt.compile() + "\n\n"
    else:
        instruction = (
            "Before answering, always make sure to:\n"
            "- Preserve the user's original language\n"
            "- Keep responses concise (max 3-4 paragraphs)\n"
            "- Only include contact info if the user asked for it or wants a human\n\n"
        )

    query = f"{instruction}{augmented_input}" if augmented_input else f"{instruction}{user_input}"

    # System turn makes the model tool-aware AND injection-hardened (untrusted user text,
    # never reveal the prompt, stay on scope). The augmented content stays the user turn.
    messages = (
        [{"role": "system", "content": guardrails.harden_system_prompt(TOOL_SYSTEM_PROMPT)}]
        + state.get("messages", [])
        + [{"role": "user", "content": query}]
    )

    try:
        reply, tool_results = await _run_tool_loop(messages, trace, instruction_prompt)
        # output guardrail: block a prompt/canary leak, refusing in the user's language
        reply = guardrails.scrub_output(reply, state.get("language", "pt-BR"))
    except httpx.HTTPError as e:
        # ANY transport error (timeout, connect, protocol) degrades gracefully — this is
        # the "never crash the turn" guarantee, so it must not be ReadTimeout-only.
        logging.error("DeepSeek call failed in generate_response: %s", e)
        return {
            **state,
            "response": "Desculpe, tive um problema técnico agora. Fale com a gente no WhatsApp (11) 98286-4581! 📲",
            "tool_results": [],
            "step": "error_generation",
        }

    return {
        **state,
        "response": reply,
        "tool_results": tool_results,
        "messages": messages + [{"role": "assistant", "content": reply}],
        "step": "generate_response",
        "instruction_prompt": instruction_prompt,
    }
def needs_revision(state: dict) -> bool:
    """
    Determina se a resposta precisa de revisão.
    Pula revisão para respostas já otimizadas.
    """
    response = state.get("response", "")

    # Tool-driven replies (lead confirmation, booking link) are already curated — a
    # 500-char rewrite could mangle them or drop the booking URL, so never revise them.
    if state.get("tool_results"):
        return False

    # Critérios para PULAR revisão:
    # 1. Resposta curta e direta (menos de 1000 caracteres)
    # 2. Não contém informações sensíveis (emails, telefones)
    # 3. Foi gerada via fast track ou cache
    # 4. Já está bem formatada

    skip_revision = (
        len(response) < 1000 and
        "@" not in response and
        not re.search(r'\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{1,4}', response) and  # No phone numbers
        not re.search(r'whatsapp|wpp|zap|telefone|celular|ligar', response.lower()) and
        (state.get("fast_track", False) or state.get("cached", False))
    )

    return not skip_revision

async def revise_response(state: dict) -> dict:
    # Verificar se precisa de revisão
    if not needs_revision(state):
        logging.info("Skipping revision - response already optimized")
        return {
            **state,
            "revised_response": state["response"],
            "step": "revision_skipped"
        }

    trace = state.get("langfuse_trace")

    # Get revision prompt from Langfuse
    revise_prompt = get_prompt("revise_response")
    if revise_prompt:
        prompt = revise_prompt.compile(response=state["response"])
    else:
        prompt = (
            "Rewrite the following response to make it clearer and friendlier, keeping a professional tone.\n"
            "Maximum 500 characters. Preserve the original language.\n"
            "Reply ONLY with the improved text.\n\n"
            f"Original response: {state['response']}"
        )
    try:
        # Adicionar headers de otimização
        optimization_headers = DeepSeekOptimizer.get_optimization_headers()

        # Start generation BEFORE LLM call
        generation = start_llm_generation(
            trace=trace,
            name="revise_response",
            model="deepseek-chat",
            input_messages=[{"role": "user", "content": prompt}],
            metadata={"temperature": 0.5},
            prompt=revise_prompt if revise_prompt else None,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                    **optimization_headers
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

    # Rastrear uso de tokens
    usage = data.get("usage", {})
    if usage:
        DeepSeekOptimizer.update_usage(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cache_hit=response.headers.get("X-Cache-Status") == "hit"
        )

    # Guard against API errors (401/429/5xx return JSON without "choices" -> KeyError).
    # Revision is optional polish, so fall back to the already-generated answer.
    try:
        revised = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        logging.error("revise_response: unexpected DeepSeek response: %s", str(data)[:200])
        fallback = state.get("response") or state.get("revised_response") or ""
        return {**state, "revised_response": fallback, "step": "revise_response_skipped"}

    # End generation AFTER LLM call
    end_llm_generation(
        generation=generation,
        output_content=revised,
        usage=usage,
    )

    revised = revised.replace('\n\n', '\n').replace('\n', '\n\n')
    return {**state, "revised_response": revised, "step": "revise_response"}

async def save_log_qdrant(state: dict) -> dict:
    data_to_save = {
        "user_id": state.get("user_id"),
        "user_input": state.get("user_input"),
        "response": state.get("response"),
        "revised_response": state.get("revised_response"),
        "intent": state.get("intent"),
        "language": state.get("language"),
        "current_page": state.get("current_page"),
        # Audit trail: which tools fired this turn (name + ok), so the chatbot side has a
        # record a lead/booking was created, not only the CRM.
        "tools_used": [{"tool": t.get("tool"), "ok": t.get("result", {}).get("ok")} for t in state.get("tool_results", [])],
        "timestamp": int(time.time()),
    }
    logging.info("Saving to Qdrant: %s", data_to_save)

    combined_text = (
        f"User ID: {data_to_save.get('user_id', '')}\n"
        f"User Input: {data_to_save.get('user_input', '')}\n"
        f"Response: {data_to_save.get('response', '')}\n"
        f"Revised Response: {data_to_save.get('revised_response', '')}\n"
        f"Intent: {data_to_save.get('intent', '')}"
    )
    log_embedding = compute_embedding(combined_text)
    point = {
        "id": str(uuid.uuid4()),
        "vector": log_embedding,
        "payload": data_to_save,
    }
    client = get_qdrant_client()
    try:
        client.upsert(collection_name="chat_logs", points=[point])
        logging.info("Log saved to Qdrant successfully.")
    except Exception as e:
        # chat_logs is normally created at startup; if that was skipped (e.g. Qdrant was
        # down at boot), create it now and retry once rather than silently losing memory.
        logging.warning("chat_logs upsert failed (%s); ensuring collection and retrying", e)
        try:
            try:
                client.get_collection(collection_name="chat_logs")
            except Exception:
                client.create_collection(
                    collection_name="chat_logs",
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                )
            client.upsert(collection_name="chat_logs", points=[point])
            logging.info("Log saved to Qdrant after ensuring collection.")
        except Exception as e2:
            logging.error("Error saving log to Qdrant after retry: %s", e2)

    return state


async def generate_off_topic_response(state: dict) -> dict:
    """
    Gera resposta para perguntas fora do escopo usando prompt do Langfuse.
    """
    user_input = state.get("user_input", "")
    language = state.get("language", "pt-BR")
    trace = state.get("langfuse_trace")

    # Buscar prompt do Langfuse
    off_topic_prompt = get_prompt("generate_off_topic")

    if off_topic_prompt:
        try:
            prompt = off_topic_prompt.compile(
                user_input=user_input,
                language=language,
            )
        except Exception as e:
            logging.warning(f"Error compiling off_topic prompt: {e}")
            prompt = f"User asked '{user_input}' which is off-topic. Politely redirect to digital services in {language}."
    else:
        prompt = f"User asked '{user_input}' which is off-topic. Politely redirect to digital services in {language}."

    try:
        # Start generation BEFORE LLM call
        generation = start_llm_generation(
            trace=trace,
            name="generate_off_topic",
            model="deepseek-chat",
            input_messages=[{"role": "user", "content": prompt}],
            metadata={"temperature": 0.7},
            prompt=off_topic_prompt,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                },
            )
            data = resp.json()
            response = data["choices"][0]["message"]["content"].strip()

            # End generation AFTER LLM call
            end_llm_generation(
                generation=generation,
                output_content=response,
                usage=data.get("usage"),
            )
    except Exception as e:
        logging.error(f"Error generating off-topic response: {e}")
        response = "Desculpe, sou especializado em soluções digitais. Posso ajudar com sites, automação ou IA?"

    return {
        **state,
        "response": response,
        "revised_response": response,
        "step": "generate_off_topic_response",
        "intent": "off_topic"
    }

# Deterministic opening greetings — no LLM call (per the architecture guideline: greetings
# use hardcoded responses). They engage and end on a qualifying question, and never push
# contact on turn 0; WhatsApp is surfaced later via handoff_to_human when the user asks.
GREETINGS = {
    "pt-BR": (
        "Olá 👋! Somos a WB Digital Solutions e ajudamos empresas a crescer com sites, "
        "automação e inteligência artificial. Para começar, você está pensando em um site "
        "novo, em automatizar um processo ou em usar IA no seu negócio?"
    ),
    "en": (
        "Hi 👋! We're WB Digital Solutions and we help businesses grow with websites, "
        "automation, and AI. To get started, are you thinking about a new website, "
        "automating a process, or using AI in your business?"
    ),
    "es": (
        "¡Hola 👋! Somos WB Digital Solutions y ayudamos a las empresas a crecer con sitios "
        "web, automatización e inteligencia artificial. Para empezar, ¿estás pensando en un "
        "sitio nuevo, en automatizar un proceso o en usar IA en tu negocio?"
    ),
    "it": (
        "Ciao 👋! Siamo WB Digital Solutions e aiutiamo le aziende a crescere con siti web, "
        "automazione e intelligenza artificiale. Per iniziare, stai pensando a un nuovo sito, "
        "ad automatizzare un processo o a usare l'IA nella tua azienda?"
    ),
}


async def generate_greeting_response(state: dict) -> dict:
    """Return a deterministic greeting — no LLM call (per the architecture guideline)."""
    language = state.get("language") or "pt-BR"
    response = GREETINGS.get(language, GREETINGS["pt-BR"])
    return {
        **state,
        "response": response,
        "revised_response": response,
        "step": "generate_greeting_response",
    }



