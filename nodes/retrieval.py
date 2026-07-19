"""RAG retrieval: company-knowledge chunks + prior-user context from Qdrant."""

import logging

import langfuse_client
import nodes.embeddings as embeddings
from config import COMPANY_SCORE_THRESHOLD, COMPANY_TOP_K
from db import get_qdrant_client

# Top-k retrieval over the chunked knowledge base (see ingest.py). The score threshold
# drops weak matches; cosine similarity, so higher is closer. Retrieval only runs for
# on-topic intents (off_topic short-circuits earlier), so this is a relevance floor, not
# an off-topic filter. Both are env-tunable via config so the threshold can be
# re-calibrated from prod traces; the default suits the multilingual-query / English-KB
# cross-lingual score range (relevant pt->en ~0.20-0.40, off-topic ~0.15).


async def retrieve_company_context(state: dict) -> dict:
    """
    Retrieve the most relevant company-knowledge chunks for the user's query from the
    Qdrant 'company_info' collection: top-k over chunks, above a score threshold, joined
    into the grounding context. The source chunks (section + score) are attached to the
    Langfuse trace as citations and logged, so the threshold can be re-calibrated from
    real traffic.
    """
    embedding = embeddings.compute_embedding(state["user_input"])
    chunks, sources = [], []
    try:
        results = get_qdrant_client().search(
            collection_name="company_info",
            query_vector=embedding,
            limit=COMPANY_TOP_K,
            score_threshold=COMPANY_SCORE_THRESHOLD,
        )
        for r in results:
            # "text" is the chunked schema; fall back to the legacy single-doc "company_info"
            # key so retrieval keeps working before the first chunked ingest runs.
            text = r.payload.get("text") or r.payload.get("company_info", "")
            if text:
                chunks.append(text)
                sources.append({"section": r.payload.get("section"), "score": round(r.score, 4)})
    except Exception as e:
        logging.error("Error retrieving company context: %s", e)

    logging.info("RAG retrieval for %r -> %s", state.get("user_input", "")[:60], sources)
    company_context = "\n\n---\n\n".join(chunks)
    if sources:
        langfuse_client.update_trace(state.get("langfuse_trace"), metadata={"rag_sources": sources})
    return {
        **state,
        "company_context": company_context,
        "rag_sources": sources,
        "step": "retrieve_company_context",
    }


async def retrieve_user_context(state: dict) -> dict:
    """
    Searches the Qdrant collection 'chat_logs' for previous conversations
    from the same user (based on user_id) and combines them into a context.
    """

    query_filter = {"must": [{"key": "user_id", "match": {"value": state.get("user_id")}}]}

    dummy_vector = [0.0] * 384
    try:
        results = get_qdrant_client().search(
            collection_name="chat_logs",
            query_vector=dummy_vector,
            limit=5,
            query_filter=query_filter
        )

        if results:
            user_context = "\n".join([r.payload.get("response", "") for r in results])
        else:
            user_context = ""
    except Exception as e:
        logging.error("Error retrieving user context: %s", e)
        user_context = ""
    return {**state, "user_context": user_context, "step": "retrieve_user_context"}
