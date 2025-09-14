# graph_config.py
from langgraph.graph import StateGraph, END
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
from typing import Any, Dict

GraphState = Dict[str, Any]

workflow = StateGraph(GraphState)

workflow.add_node("intent_detection", detect_intent)
workflow.add_node("retrieve_company_context", retrieve_company_context)
workflow.add_node("retrieve_user_context", retrieve_user_context)
workflow.add_node("augment_query", augment_query)
workflow.add_node("response_generation", generate_response)
workflow.add_node("response_revision", revise_response)
workflow.add_node("log_saving", save_log_qdrant)
workflow.add_node("generate_greeting_response", generate_greeting_response)
workflow.add_node("generate_off_topic_response", generate_off_topic_response)
workflow.add_edge("generate_greeting_response", END)
workflow.add_edge("generate_off_topic_response", END)

workflow.set_entry_point("intent_detection")


def route_after_intent(state):
    """
    Decide o roteamento após detecção de intent.
    Implementa fast track para perguntas diretas sobre serviços.
    """
    intent = state.get("intent", "")

    # Casos especiais que não precisam de contexto
    if intent == "greeting":
        return "generate_greeting_response"
    elif intent == "off_topic":
        return "generate_off_topic_response"
    elif intent == "chat_with_agent":
        return END
    elif intent == "schedule_meeting":
        return END

    # Fast track: pula busca de contexto para perguntas diretas
    if state.get("fast_track", False):
        return "response_generation"  # Pula direto para geração

    # Fluxo normal: busca contexto
    return "retrieve_company_context"

workflow.add_conditional_edges(
    "intent_detection",
    route_after_intent,
    {
        "generate_greeting_response": "generate_greeting_response",
        "generate_off_topic_response": "generate_off_topic_response",
        END: END,
        "response_generation": "response_generation",  # Fast track
        "retrieve_company_context": "retrieve_company_context"  # Normal flow
    }
)

workflow.add_edge("retrieve_company_context", "retrieve_user_context")
workflow.add_edge("retrieve_user_context", "augment_query")
workflow.add_edge("augment_query", "response_generation")
workflow.add_edge("response_generation", "response_revision")
workflow.add_edge("response_revision", "log_saving")
workflow.add_edge("log_saving", END)

graph = workflow.compile()