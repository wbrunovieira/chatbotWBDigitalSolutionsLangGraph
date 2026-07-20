# langfuse_client.py
"""
Langfuse client for tracing LLM calls and prompt management.
Provides a singleton client instance and helper functions.
"""
import contextvars
import logging
import json
import re
from typing import Optional, Dict, Any, List
from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
from langfuse_prompts_v3 import PROMPTS_V3
from guardrails import redact_pii


def _redact_messages(messages):
    """Redact PII from LLM input messages before tracing — both the text `content` and the
    tool-call `arguments` (which carry the real lead name/phone/email create_lead sends the CRM)."""
    out = []
    for m in messages:
        if not isinstance(m, dict):
            out.append(m)
            continue
        m2 = dict(m)
        if isinstance(m2.get("content"), str):
            m2["content"] = redact_pii(m2["content"])
        if m2.get("tool_calls"):
            m2["tool_calls"] = [
                {**tc, "function": {**tc["function"], "arguments": redact_pii(tc["function"]["arguments"])}}
                if isinstance(tc, dict) and isinstance(tc.get("function", {}).get("arguments"), str)
                else tc
                for tc in m2["tool_calls"]
            ]
        out.append(m2)
    return out

# Initialize Langfuse client (lazy)
_langfuse_client = None

# The per-request Langfuse trace, carried in a ContextVar rather than in the graph state.
# A trace is a live, non-serializable object; keeping it out of state is what lets the
# LangGraph checkpointer serialize the state to persist conversation memory. The context
# propagates into the graph's async nodes the same way the request-cost/client-ip
# ContextVars already do.
_current_trace: contextvars.ContextVar = contextvars.ContextVar("langfuse_trace", default=None)


def set_current_trace(trace) -> None:
    _current_trace.set(trace)


def get_current_trace():
    return _current_trace.get()

# Local fallback prompts, DERIVED from the single canonical source
# (langfuse_prompts_v3.PROMPTS_V3). Used when Langfuse is unreachable. Deriving instead
# of hand-copying means this fallback can never silently drift from the uploaded prompts —
# there is exactly one place a prompt is defined.
LOCAL_PROMPTS = {
    name: {"type": data["type"], "template": data["prompt"]}
    for name, data in PROMPTS_V3.items()
}


class LocalPrompt:
    """Fallback prompt class that mimics Langfuse prompt interface."""

    def __init__(self, name: str, template: str, prompt_type: str = "text"):
        self.name = name
        self.template = template
        self.type = prompt_type
        self.version = 0
        self.is_fallback = True

    def compile(self, **kwargs) -> str | List[Dict[str, str]]:
        """
        Compile a text prompt by substituting {{var}} placeholders (mustache-style, to
        match the canonical PROMPTS_V3 templates). Uses a replacement function so values
        containing backslashes / group refs are inserted literally, and leaves any
        unsupplied {{var}} untouched (a forgiving fallback, unlike str.format which raises).
        """
        if self.type != "text":
            # For chat type, return as-is (not implemented in fallback)
            return self.template
        result = self.template
        for key, value in kwargs.items():
            result = re.sub(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", lambda _m: str(value), result)
        return result


def get_langfuse():
    """Get or create Langfuse client singleton."""
    global _langfuse_client
    if _langfuse_client is None:
        if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
            try:
                from langfuse import Langfuse

                _langfuse_client = Langfuse(
                    public_key=LANGFUSE_PUBLIC_KEY,
                    secret_key=LANGFUSE_SECRET_KEY,
                    host=LANGFUSE_HOST,
                )
                logging.info(f"Langfuse initialized with host: {LANGFUSE_HOST}")
            except Exception as e:
                logging.warning(f"Failed to initialize Langfuse: {e}")
                _langfuse_client = None
        else:
            logging.info("Langfuse disabled - no credentials configured")
    return _langfuse_client


def flush_langfuse():
    """Flush pending Langfuse events. Call on app shutdown."""
    client = get_langfuse()
    if client:
        try:
            client.flush()
            logging.info("Langfuse flushed successfully")
        except Exception as e:
            logging.warning(f"Failed to flush Langfuse: {e}")


def get_prompt(name: str, prompt_type: str = "text", fallback: bool = True):
    """
    Get a prompt from Langfuse with local fallback.

    Args:
        name: Prompt name
        prompt_type: 'text' or 'chat'
        fallback: If True, use local fallback when Langfuse unavailable

    Returns:
        Langfuse prompt object or LocalPrompt fallback
    """
    client = get_langfuse()

    if client:
        try:
            prompt = client.get_prompt(name, type=prompt_type)
            logging.debug(f"Loaded prompt '{name}' from Langfuse (v{prompt.version})")
            return prompt
        except Exception as e:
            logging.warning(f"Failed to get prompt '{name}' from Langfuse: {e}")

    # Fallback to local prompt
    if fallback and name in LOCAL_PROMPTS:
        logging.info(f"Using local fallback for prompt '{name}'")
        local = LOCAL_PROMPTS[name]
        return LocalPrompt(name, local["template"], local.get("type", "text"))

    return None


def create_trace(
    name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    input_data: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Create a new trace for a chat interaction."""
    client = get_langfuse()
    if not client:
        return None
    try:
        return client.trace(
            name=name,
            user_id=user_id,
            session_id=session_id,
            input=input_data,
            metadata=metadata,
        )
    except Exception as e:
        logging.warning(f"Failed to create Langfuse trace: {e}")
        return None


def start_llm_generation(
    trace,
    name: str,
    model: str,
    input_messages: List[Dict[str, str]],
    metadata: Optional[Dict[str, Any]] = None,
    prompt=None,
):
    """
    Start an LLM generation BEFORE calling the LLM.
    Call this before making the API request to capture start time.

    Returns:
        Generation object to be ended with end_llm_generation()
    """
    if not trace:
        return None
    try:
        gen_kwargs = {
            "name": name,
            "model": model,
            "input": _redact_messages(input_messages),
            "metadata": metadata,
        }

        # Link prompt if provided and not a fallback
        if prompt and hasattr(prompt, "is_fallback") is False:
            gen_kwargs["prompt"] = prompt

        return trace.generation(**gen_kwargs)
    except Exception as e:
        logging.warning(f"Failed to start Langfuse generation: {e}")
        return None


def end_llm_generation(
    generation,
    output_content: str,
    usage: Optional[Dict[str, int]] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    End an LLM generation AFTER the LLM response is received.
    This captures the end time for latency calculation.

    Args:
        generation: Generation object from start_llm_generation()
        output_content: LLM response content
        usage: Token usage dict
        metadata: Additional metadata to merge
    """
    if not generation:
        return
    try:
        end_kwargs = {"output": redact_pii(output_content) if isinstance(output_content, str) else output_content}

        if usage:
            end_kwargs["usage"] = {
                "input": usage.get("prompt_tokens", 0),
                "output": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }

        if metadata:
            end_kwargs["metadata"] = metadata

        generation.end(**end_kwargs)
    except Exception as e:
        logging.warning(f"Failed to end Langfuse generation: {e}")


def update_trace(
    trace,
    output: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Update trace with final output."""
    if not trace:
        return
    try:
        trace.update(output=output, metadata=metadata)
    except Exception as e:
        logging.warning(f"Failed to update Langfuse trace: {e}")


def score_trace(
    trace,
    name: str,
    value: float,
    comment: Optional[str] = None,
):
    """Add a score to a trace."""
    if not trace:
        return
    try:
        trace.score(name=name, value=value, comment=comment)
    except Exception as e:
        logging.warning(f"Failed to score Langfuse trace: {e}")


async def evaluate_response(
    trace,
    user_input: str,
    response: str,
    intent: str,
    llm_client=None,
):
    """
    Evaluate a chatbot response using LLM-as-judge.

    Args:
        trace: Langfuse trace object
        user_input: Original user question
        response: Chatbot response
        intent: Detected intent
        llm_client: Optional async HTTP client for LLM calls

    Returns:
        Dict with scores or None if evaluation fails
    """
    if not trace:
        return None

    # Get evaluation prompt
    eval_prompt = get_prompt("evaluate_response", fallback=False)
    if not eval_prompt:
        logging.warning("Evaluation prompt not available")
        return None

    try:
        # Compile prompt with variables
        compiled = eval_prompt.compile(
            user_input=user_input,
            response=response,
            intent=intent,
        )

        # If no LLM client provided, just log that we would evaluate
        if not llm_client:
            logging.debug("No LLM client for evaluation - skipping")
            return None

        # Call LLM for evaluation (routed via llm.py — same model routing + provider fallback;
        # runs on a tighter timeout).
        import llm

        resp = await llm.chat_completion(
            [{"role": "user", "content": compiled}],
            task="generation",
            temperature=0.1,
            timeout=15.0,
        )
        data = resp.json()
        eval_text = data["choices"][0]["message"]["content"].strip()

        # Parse JSON response
        scores = json.loads(eval_text)

        # Log scores to trace
        for score_name, score_value in scores.items():
            score_trace(trace, score_name, float(score_value))

        logging.info(f"Evaluation scores: {scores}")
        return scores

    except json.JSONDecodeError as e:
        logging.warning(f"Failed to parse evaluation response: {e}")
        return None
    except Exception as e:
        logging.warning(f"Evaluation failed: {e}")
        return None
