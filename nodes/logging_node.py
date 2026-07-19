"""Persist each exchange (embedded) into the Qdrant chat_logs collection."""

import logging
import time
import uuid

from qdrant_client.http.models import Distance, VectorParams

import guardrails
import nodes.embeddings as embeddings
from db import get_qdrant_client


async def save_log_qdrant(state: dict) -> dict:
    # Redact PII (email/CPF/CNPJ/phone) before it is PERSISTED to chat_logs — LGPD/GDPR.
    # The live response the user already received is untouched, and create_lead has already
    # sent the real contact to the CRM; only this stored copy is masked.
    data_to_save = {
        "user_id": state.get("user_id"),
        "user_input": guardrails.redact_pii(state.get("user_input")),
        "response": guardrails.redact_pii(state.get("response")),
        "revised_response": guardrails.redact_pii(state.get("revised_response")),
        "intent": state.get("intent"),
        "language": state.get("language"),
        "current_page": state.get("current_page"),
        # Audit trail: which tools fired this turn (name + ok), so the chatbot side has a
        # record a lead/booking was created, not only the CRM.
        "tools_used": [{"tool": t.get("tool"), "ok": t.get("result", {}).get("ok")} for t in state.get("tool_results", [])],
        "timestamp": int(time.time()),
    }
    logging.info("Saving to Qdrant: %s", data_to_save)

    combined_text = (
        f"User ID: {data_to_save.get('user_id', '')}\n"
        f"User Input: {data_to_save.get('user_input', '')}\n"
        f"Response: {data_to_save.get('response', '')}\n"
        f"Revised Response: {data_to_save.get('revised_response', '')}\n"
        f"Intent: {data_to_save.get('intent', '')}"
    )
    log_embedding = embeddings.compute_embedding(combined_text)
    point = {
        "id": str(uuid.uuid4()),
        "vector": log_embedding,
        "payload": data_to_save,
    }
    client = get_qdrant_client()
    try:
        client.upsert(collection_name="chat_logs", points=[point])
        logging.info("Log saved to Qdrant successfully.")
    except Exception as e:
        # chat_logs is normally created at startup; if that was skipped (e.g. Qdrant was
        # down at boot), create it now and retry once rather than silently losing memory.
        logging.warning("chat_logs upsert failed (%s); ensuring collection and retrying", e)
        try:
            try:
                client.get_collection(collection_name="chat_logs")
            except Exception:
                client.create_collection(
                    collection_name="chat_logs",
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                )
            client.upsert(collection_name="chat_logs", points=[point])
            logging.info("Log saved to Qdrant after ensuring collection.")
        except Exception as e2:
            logging.error("Error saving log to Qdrant after retry: %s", e2)

    return state
