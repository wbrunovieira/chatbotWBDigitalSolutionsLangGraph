"""Query augmentation + the tool-calling generation loop."""

import httpx
import json
import logging

from core import behavior as behavior_ctx
from providers import deepseek_client  # noqa: F401  (tests patch nodes.deepseek_client; llm delegates to it)
from safety import guardrails
from observability import langfuse_client
from providers import llm
from agents import tools
from config import MAX_HISTORY_MESSAGES
from providers.deepseek_optimizer import DeepSeekOptimizer


# Per-language answer instruction (#23). Emphatic ("ONLY", "regardless of the context")
# because the knowledge base is in English — without this a pt/es/it question tends to drift
# into an English answer. Exported so the language-consistency eval guards this exact string.
LANGUAGE_INSTRUCTIONS = {
    "en": "IMPORTANT: Reply ONLY in English, regardless of the language of the context or examples.",
    "es": "IMPORTANTE: Responde SOLO en español, sin importar el idioma del contexto o de los ejemplos.",
    "it": "IMPORTANTE: Rispondi SOLO in italiano, indipendentemente dalla lingua del contesto o degli esempi.",
    "pt-BR": "IMPORTANTE: Responda SOMENTE em português brasileiro, independentemente do idioma do contexto ou dos exemplos.",
}


def language_instruction_for(language: str) -> str:
    return LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["pt-BR"])


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

    # Determinar instrução de idioma (#23 — single source, exported + eval-guarded)
    language_instruction = language_instruction_for(language)

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
    system_prompt = langfuse_client.get_prompt("generate_services_response")

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
    "wants a proposal — capture them as a lead. If they show clear interest but haven't shared "
    "details yet, ask for their name + a contact (WhatsApp/email) so our team (Bruno) can reach "
    "out, then capture.\n"
    "- schedule_meeting: when the user wants to talk, meet, or get a proposal — give them the booking link.\n"
    "- handoff_to_human: when the user explicitly asks to talk to a person, OR asks for our "
    "contact / WhatsApp / phone / email — this is how they get our contact details.\n"
    "When the user explicitly picks a channel (schedule / talk to a person / give contact), use "
    "that tool directly. Only pass details the user actually gave; never invent a name, phone or "
    "email. Do NOT discuss prices — if asked about price, capture the lead or offer to schedule "
    "instead of giving a number."
)


async def _deepseek_chat(messages: list, temperature: float = 0.7, use_tools: bool = False) -> dict:
    """Single DeepSeek chat call. Returns the parsed JSON. Offers the tools when asked."""
    resp = await llm.chat_completion(
        messages,
        task="generation",  # stronger model for generation (#13)
        temperature=temperature,
        tools=tools.TOOL_SPECS if use_tools else None,
        extra_headers=DeepSeekOptimizer.get_optimization_headers(),
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
        generation = langfuse_client.start_llm_generation(
            trace=trace, name="generate_response", model="deepseek-v4-flash",
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
            langfuse_client.end_llm_generation(generation=generation, output_content="", usage=usage)
            return "Desculpe, tive um problema técnico. Fale com a gente no WhatsApp (11) 98286-4581.", tool_results

        langfuse_client.end_llm_generation(generation=generation, output_content=msg.get("content") or "", usage=usage)

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
    generation = langfuse_client.start_llm_generation(
        trace=trace, name="generate_response", model="deepseek-v4-flash",
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
    langfuse_client.end_llm_generation(generation=generation, output_content=content, usage=usage)
    return content, tool_results


_DEFAULT_INSTRUCTION = (
    "Before answering, always make sure to:\n"
    "- Preserve the user's original language\n"
    "- Keep responses concise (max 3-4 paragraphs)\n"
    "- Only include contact info if the user asked for it or wants a human\n\n"
)


def build_llm_messages(state: dict):
    """Assemble the [system, ...history, user] messages for the generation call.

    Shared by the graph node (generate_response) and the streaming endpoint so both send the
    identical hardened system prompt, personalization hint (#8b), replayed history, and the
    RAG-augmented current turn. Returns (messages, instruction_prompt) — the latter is passed
    to Langfuse for prompt linkage.
    """
    user_input = state["user_input"]
    augmented_input = state.get("augmented_input")

    instruction_prompt = langfuse_client.get_prompt("generate_response_instruction")
    instruction = (instruction_prompt.compile() + "\n\n") if instruction_prompt else _DEFAULT_INSTRUCTION
    query = f"{instruction}{augmented_input}" if augmented_input else f"{instruction}{user_input}"

    # `history` = accumulated prior turns (raw user/assistant text, no system prompt), replayed
    # for short-term memory. The current turn is sent AUGMENTED (RAG context); only the RAW user
    # text is persisted, so past turns don't carry stale retrieval context.
    history = state.get("messages", [])
    # Light personalization (#8b): a behavioral hint that forbids revealing we track browsing.
    system_prompt = guardrails.harden_system_prompt(TOOL_SYSTEM_PROMPT)
    hint = behavior_ctx.personalization_hint(state.get("behavior"))
    if hint:
        system_prompt = f"{system_prompt}\n\n{hint}"

    messages = (
        [{"role": "system", "content": system_prompt}]
        + history
        + [{"role": "user", "content": query}]
    )
    return messages, instruction_prompt


async def generate_response(state: dict) -> dict:
    user_input = state["user_input"]
    augmented_input = state.get("augmented_input")
    trace = langfuse_client.get_current_trace()

    # Input guardrail (#15): an unambiguous jailbreak / prompt-extraction attempt is refused
    # up front — no LLM call, so it can't cost money or leak, regardless of what it asked.
    if guardrails.is_injection_attempt(user_input):
        logging.warning("input guardrail: injection attempt refused pre-LLM")
        return {
            **state,
            "response": guardrails.refusal(state.get("language", "pt-BR")),
            "tool_results": [],
            "step": "input_guardrail_refusal",
        }

    llm_messages, instruction_prompt = build_llm_messages(state)

    try:
        reply, tool_results = await _run_tool_loop(llm_messages, trace, instruction_prompt)
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

    # Re-read the prior turns here (build_llm_messages owns its own copy) to append this turn.
    history = state.get("messages", [])
    new_history = (
        history
        + [{"role": "user", "content": user_input}, {"role": "assistant", "content": reply}]
    )[-MAX_HISTORY_MESSAGES:]

    return {
        **state,
        "response": reply,
        "tool_results": tool_results,
        "messages": new_history,
        "step": "generate_response",
        # NOTE: instruction_prompt is intentionally NOT returned — it's a live, unserializable
        # prompt object (would break the checkpointer) and nothing downstream reads it.
    }
