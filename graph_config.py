# graph_config.py
from langgraph.graph import StateGraph, END
from nodes import (
    detect_intent,
    retrieve_company_context,
    augment_query,
    generate_response,
    revise_response,
    save_log_qdrant
)
from typing import Any, Dict

# Define the graph state as a dictionary
GraphState = Dict[str, Any]

workflow = StateGraph(GraphState)

workflow.add_node("intent_detection", detect_intent)
workflow.add_node("retrieve_company_context", retrieve_company_context)
workflow.add_node("augment_query", augment_query)
workflow.add_node("response_generation", generate_response)
workflow.add_node("response_revision", revise_response)
workflow.add_node("log_saving", save_log_qdrant)

workflow.set_entry_point("intent_detection")

# Conditional routing based on detected intent
workflow.add_conditional_edges(
    "intent_detection",
    lambda state: state.get("intent", ""),
    {
         "inquire_services": "retrieve_company_context",
         "request_quote": "retrieve_company_context",
         "chat_with_agent": END,
         "schedule_meeting": END
    }
)

workflow.add_edge("retrieve_company_context", "augment_query")
workflow.add_edge("augment_query", "response_generation")
workflow.add_edge("response_generation", "response_revision")
workflow.add_edge("response_revision", "log_saving")
workflow.add_edge("log_saving", END)

graph = workflow.compile()