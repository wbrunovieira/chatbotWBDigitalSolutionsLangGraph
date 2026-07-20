# graph_config.py
from typing import Any, List

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing_extensions import TypedDict

from nodes import (
    detect_intent,
    generate_greeting_response,
    generate_off_topic_response,
    retrieve_company_context,
    retrieve_user_context,
    augment_query,
    generate_response,
    revise_response,
    save_log_qdrant
)


class ChatState(TypedDict, total=False):
    """
    The graph state. `total=False` so nodes can return partial updates. `messages` is the
    short-term conversation history (raw user/assistant turns, no system prompt) that the
    checkpointer persists per thread_id — that is the working memory.
    """
    user_input: str
    user_id: str
    language: str
    current_page: str
    page_context: str
    behavior: dict
    messages: List[dict]
    memory: dict
    metadata: dict
    intent: str
    company_context: str
    user_context: str
    augmented_input: str
    response: str
    revised_response: str
    tool_results: list
    rag_sources: list
    instruction_prompt: Any
    step: str
    cached: bool


workflow = StateGraph(ChatState)

workflow.add_node("intent_detection", detect_intent)
workflow.add_node("retrieve_company_context", retrieve_company_context)
workflow.add_node("retrieve_user_context", retrieve_user_context)
workflow.add_node("augment_query", augment_query)
workflow.add_node("response_generation", generate_response)
workflow.add_node("response_revision", revise_response)
workflow.add_node("log_saving", save_log_qdrant)
workflow.add_node("generate_greeting_response", generate_greeting_response)
workflow.add_node("generate_off_topic_response", generate_off_topic_response)
workflow.add_edge("generate_greeting_response", "log_saving")
workflow.add_edge("generate_off_topic_response", "log_saving")

workflow.set_entry_point("intent_detection")


def route_after_intent(state):
    """Route after intent detection. Greetings/off-topic short-circuit to a canned node;
    chat_with_agent ends (the frontend takes over); everything else runs the full RAG flow."""
    intent = state.get("intent", "")

    if intent == "greeting":
        return "generate_greeting_response"
    elif intent == "off_topic":
        return "generate_off_topic_response"
    elif intent == "chat_with_agent":
        return END

    return "retrieve_company_context"

workflow.add_conditional_edges(
    "intent_detection",
    route_after_intent,
    {
        "generate_greeting_response": "generate_greeting_response",
        "generate_off_topic_response": "generate_off_topic_response",
        END: END,
        "retrieve_company_context": "retrieve_company_context"  # Normal flow
    }
)

workflow.add_edge("retrieve_company_context", "retrieve_user_context")
workflow.add_edge("retrieve_user_context", "augment_query")
workflow.add_edge("augment_query", "response_generation")
workflow.add_edge("response_generation", "response_revision")
workflow.add_edge("response_revision", "log_saving")
workflow.add_edge("log_saving", END)

# MemorySaver = in-process checkpointer: persists state per thread_id across requests so the
# agent remembers the conversation. Prod runs a single uvicorn worker, so one process holds
# all threads; the trade-off is that memory resets on restart/deploy (fine for short sales
# chats). A persistent Redis/Postgres checkpointer needs a langgraph major bump (see ADR).
graph = workflow.compile(checkpointer=MemorySaver())


def evict_thread(thread_id: str) -> None:
    """
    Drop a thread's checkpoints from the in-process MemorySaver. Used for single-use
    ephemeral (anonymous) threads so they don't accumulate for the process lifetime.

    Reaches into MemorySaver internals (`.storage` / `.writes`) because langgraph 0.3.18
    has no public delete_thread; guarded so a langgraph-internals change can't crash a
    request. (When the persistent Redis/Postgres checkpointer lands with TTLs, drop this.)
    """
    import logging

    saver = graph.checkpointer
    try:
        storage = getattr(saver, "storage", None)
        if storage is not None:
            storage.pop(thread_id, None)
        writes = getattr(saver, "writes", None)
        if writes is not None:
            for key in [k for k in writes if k and k[0] == thread_id]:
                writes.pop(key, None)
    except Exception as exc:  # never let eviction break a request
        logging.warning("evict_thread(%s) failed: %s", thread_id, exc)