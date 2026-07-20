"""
Graph node functions, split into focused submodules (embeddings, intent, retrieval,
generation, revision, logging_node, offtopic, greeting).

This package re-exports every public name the rest of the codebase used when `nodes` was a
single module, so `import nodes; nodes.X` keeps working. `deepseek_client` is imported here
too so `nodes.deepseek_client` stays a live module handle (tests patch it).
"""

import deepseek_client  # noqa: F401  (kept so nodes.deepseek_client resolves for test patches)

# Import submodules so `nodes.generation`, `nodes.embeddings`, etc. resolve (tests patch there).
from nodes import (  # noqa: F401
    embeddings,
    generation,
    greeting,
    intent,
    logging_node,
    offtopic,
    retrieval,
    revision,
)
from nodes.embeddings import EMBEDDING_MODEL_NAME, compute_embedding, get_embedding_model
from nodes.generation import (
    LANGUAGE_INSTRUCTIONS,
    TOOL_SYSTEM_PROMPT,
    _deepseek_chat,
    _run_tool_loop,
    augment_query,
    build_llm_messages,
    generate_response,
    language_instruction_for,
)
from nodes.greeting import GREETINGS, generate_greeting_response
from nodes.intent import (
    DEFAULT_INTENT,
    VALID_INTENTS,
    _exact_intent,
    detect_intent,
    parse_intent,
)
from nodes.logging_node import save_log_qdrant
from nodes.offtopic import generate_off_topic_response
from nodes.retrieval import (
    COMPANY_SCORE_THRESHOLD,
    COMPANY_TOP_K,
    retrieve_company_context,
    retrieve_user_context,
)
from nodes.revision import needs_revision, revise_response
