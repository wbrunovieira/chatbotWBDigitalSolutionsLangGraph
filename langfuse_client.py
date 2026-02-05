# langfuse_client.py
"""
Langfuse client for tracing LLM calls.
Provides a singleton client instance and helper functions for tracing.
"""
import logging
from typing import Optional, Dict, Any, List
from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

# Initialize Langfuse client (lazy)
_langfuse_client = None


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
):
    """Log an LLM generation to a trace."""
    if not trace:
        return None
    try:
        return trace.generation(
            name=name,
            model=model,
            input=input_messages,
            output=output_content,
            usage={
                "input": usage.get("prompt_tokens", 0) if usage else 0,
                "output": usage.get("completion_tokens", 0) if usage else 0,
                "total": usage.get("total_tokens", 0) if usage else 0,
            } if usage else None,
            metadata=metadata,
        )
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


def score_trace(trace, name: str, value: float, comment: Optional[str] = None):
    """Add a score to a trace."""
    if not trace:
        return
    try:
        trace.score(name=name, value=value, comment=comment)
    except Exception as e:
        logging.warning(f"Failed to score Langfuse trace: {e}")
