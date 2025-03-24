# graph_config.py
from langgraph.graph import StateGraph, END
from nodes import detect_intent, generate_response, revise_response, save_log_qdrant
from typing import Any, Dict


GraphState = Dict[str, Any]

workflow = StateGraph(GraphState)

workflow.add_node("intent_detection", detect_intent)
workflow.add_node("response_generation", generate_response)
workflow.add_node("response_revision", revise_response)
workflow.add_node("log_saving", save_log_qdrant)

workflow.set_entry_point("intent_detection")


workflow.add_conditional_edges(
    "intent_detection",
    lambda state: state.get("intent", ""),
    {
        "request_quote": "response_generation",
        "inquire_services": "response_generation",
        "chat_with_agent": END,
        "schedule_meeting": "response_generation"
    }
)


workflow.add_edge("response_generation", "response_revision")

workflow.add_edge("response_revision", "log_saving")

workflow.add_edge("log_saving", END)

graph = workflow.compile()