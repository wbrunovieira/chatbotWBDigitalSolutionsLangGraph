# graph_config.py
from langgraph.graph import StateGraph, END
from nodes import (
    detect_intent,
    generate_greeting_response,
    retrieve_company_context,
    retrieve_user_context,
    augment_query,
    generate_response,
    revise_response,
    save_log_qdrant,
    send_contact_whatsapp
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
workflow.add_edge("generate_greeting_response", END)

workflow.set_entry_point("intent_detection")


workflow.add_conditional_edges(
    "intent_detection",
    lambda state: state.get("intent", ""),
    {
        "greeting": "generate_greeting_response",
        "chat_with_agent": END,
        "schedule_meeting": END,
        "inquire_services": "retrieve_company_context",
        "request_quote": "retrieve_company_context",
        "share_contact": "send_contact_whatsapp" 
    }
)

workflow.add_edge("retrieve_company_context", "retrieve_user_context")
workflow.add_edge("retrieve_user_context", "augment_query")
workflow.add_edge("augment_query", "response_generation")
workflow.add_edge("response_generation", "response_revision")
workflow.add_edge("response_revision", "log_saving")
workflow.add_node("send_contact_whatsapp", send_contact_whatsapp)

workflow.add_edge("send_contact_whatsapp", END)
workflow.add_edge("log_saving", END)

graph = workflow.compile()