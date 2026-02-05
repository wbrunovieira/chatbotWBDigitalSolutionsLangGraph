# langfuse_client.py
"""
Langfuse client for tracing LLM calls and prompt management.
Provides a singleton client instance and helper functions.
"""
import logging
import json
from typing import Optional, Dict, Any, List
from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

# Initialize Langfuse client (lazy)
_langfuse_client = None

# Local fallback prompts (used when Langfuse is unavailable)
LOCAL_PROMPTS = {
    "detect_intent": {
        "type": "text",
        "template": """Analyze this message and determine if it's related to business/technology services or not.

Context: WB Digital Solutions provides websites, automation, and AI solutions for businesses.

Message: "{user_input}"

Question: Is this message asking about business services, technology, websites, automation, AI, pricing, or contacting the company?

If YES (related to business/tech): determine the specific intent:
- "greeting" if just saying hello
- "inquire_services" if asking about services
- "request_quote" if asking about prices
- "chat_with_agent" if wants human contact
- "schedule_meeting" if wants to schedule

If NO (NOT related): return "off_topic"

Return ONLY the intent word, nothing else:""",
    },
    "generate_response_instruction": {
        "type": "text",
        "template": """Before answering, always make sure to:
- Preserve the user's original language
- Ignore typos, missing punctuation, or spacing errors
- Focus on understanding the user's intent clearly
- Keep responses concise (max 3-4 paragraphs)
- If including contact, use ONE line: 'WhatsApp (11) 98286-4581 - respondemos em 2h!'
- Focus on value and benefits for the customer
- End with a clear next step when appropriate""",
    },
    "revise_response": {
        "type": "text",
        "template": """Rewrite the following response to make it clearer and friendlier, keeping a professional tone.

IMPORTANT RULES:
1. Maximum 3 paragraphs or sections
2. If there's contact info (WhatsApp/email), consolidate in ONE line with a benefit
3. Keep the main message focused on value to the customer
4. Maximum 500 characters total
5. Preserve the original language
6. End with a clear call-to-action when appropriate

Reply ONLY with the improved text, no explanations.

Original response: {response}""",
    },
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
        """Compile the prompt with variables."""
        if self.type == "text":
            return self.template.format(**kwargs)
        else:
            # For chat type, return as-is (not implemented in fallback)
            return self.template


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


def log_llm_generation(
    trace,
    name: str,
    model: str,
    input_messages: List[Dict[str, str]],
    output_content: str,
    usage: Optional[Dict[str, int]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    prompt=None,
):
    """
    Log an LLM generation to a trace.

    Args:
        trace: Langfuse trace object
        name: Generation name
        model: Model used
        input_messages: Input messages
        output_content: Generated output
        usage: Token usage dict
        metadata: Additional metadata
        prompt: Optional Langfuse prompt object to link
    """
    if not trace:
        return None
    try:
        gen_kwargs = {
            "name": name,
            "model": model,
            "input": input_messages,
            "output": output_content,
            "metadata": metadata,
        }

        if usage:
            gen_kwargs["usage"] = {
                "input": usage.get("prompt_tokens", 0),
                "output": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }

        # Link prompt if provided and not a fallback
        if prompt and hasattr(prompt, "is_fallback") is False:
            gen_kwargs["prompt"] = prompt

        return trace.generation(**gen_kwargs)
    except Exception as e:
        logging.warning(f"Failed to log Langfuse generation: {e}")
        return None


def log_span(
    trace,
    name: str,
    input_data: Optional[Dict[str, Any]] = None,
    output_data: Optional[Dict[str, Any]] = None,
):
    """Log a span (non-LLM step) to a trace."""
    if not trace:
        return None
    try:
        span = trace.span(name=name, input=input_data)
        if output_data:
            span.end(output=output_data)
        return span
    except Exception as e:
        logging.warning(f"Failed to log Langfuse span: {e}")
        return None


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


def score_trace_by_id(
    trace_id: str,
    name: str,
    value: float,
    comment: Optional[str] = None,
):
    """Add a score to a trace by ID (for async evaluation)."""
    client = get_langfuse()
    if not client:
        return
    try:
        client.score(trace_id=trace_id, name=name, value=float(value), comment=comment)
    except Exception as e:
        logging.warning(f"Failed to score Langfuse trace by ID: {e}")


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

        # Call LLM for evaluation
        import httpx
        from config import DEEPSEEK_API_KEY

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": compiled}],
                    "temperature": 0.1,
                },
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
