"""Intent detection + robust parsing of the classifier output."""

import json
import logging
import re

import deepseek_client  # noqa: F401  (tests patch nodes.deepseek_client; llm delegates to it)
import langfuse_client
import llm
from deepseek_optimizer import DeepSeekOptimizer

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
    intent_prompt = langfuse_client.get_prompt("detect_intent")
    if intent_prompt:
        try:
            prompt = intent_prompt.compile(
                user_input=user_input,
                language=language,
                current_page=current_page,
            )
        except Exception:
            # Fallback if compile fails (variables missing in the prompt)
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
    trace = langfuse_client.get_current_trace()

    try:
        optimization_headers = DeepSeekOptimizer.get_optimization_headers()

        # Start generation BEFORE LLM call (captures start time)
        generation = langfuse_client.start_llm_generation(
            trace=trace,
            name="detect_intent",
            model="deepseek-v4-flash",
            input_messages=[{"role": "user", "content": prompt}],
            metadata={"temperature": 0.1},
            prompt=intent_prompt,
        )

        # DeepSeek's json_object mode 400s unless the prompt contains the word "json".
        # Only request it when the (possibly Langfuse-served, possibly stale) prompt
        # actually asks for JSON; otherwise let parse_intent handle free text. This
        # keeps a prompt/code mismatch from silently breaking intent detection.
        response_format = {"type": "json_object"} if "json" in prompt.lower() else None

        response = await llm.chat_completion(
            [{"role": "user", "content": prompt}],
            task="intent",  # cheap/fast model for classification (#13)
            temperature=0.1,
            response_format=response_format,
            extra_headers=optimization_headers,
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
        langfuse_client.end_llm_generation(
            generation=generation,
            output_content=raw_intent,
            usage=usage,
            metadata={"detected_intent": intent},
        )
    except Exception as e:
        logging.error(f"Error in intent detection: {e}")
        intent = "inquire_services"

    return {**state, "intent": intent, "step": "detect_intent"}
