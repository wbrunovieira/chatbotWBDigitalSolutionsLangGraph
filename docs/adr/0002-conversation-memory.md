# ADR 0002 — Two-tier conversation memory

- **Status:** Accepted
- **Date:** 2026-07-19
- **Context owner:** Bruno (WB Digital Solutions)

## Context

The bot had no working memory. Every `/chat` request built a fresh state, so the agent
couldn't remember what was said two messages ago ("and how much does *that* cost?" had no
referent). There was a `retrieve_user_context` node, but it searched `chat_logs` with a
**zero vector** — a semantically meaningless ranking that returned arbitrary rows.

Memory has two genuinely different jobs, and one mechanism can't do both well:

- **Short-term** — "what did we just say" within the current conversation. Needs the last
  few turns, verbatim, cheaply, every turn.
- **Long-term** — "what did this user ask us last week / before the last deploy". Needs
  semantic recall across sessions, and it must survive a process restart.

## Decision

Two tiers, each with the right tool.

### Tier 1 — short-term: a LangGraph checkpointer (`MemorySaver`), keyed by `thread_id`

The graph is compiled with a checkpointer and invoked with `thread_id = user_id`, so LangGraph
persists the state per conversation and replays it on the next turn. The state carries a
`messages` list (raw user/assistant turns, no system prompt); `generate_response` replays it
as history and appends the new turn, capped at `MAX_HISTORY_MESSAGES` (last ~5 turns) to bound
context/cost. This is the idiomatic LangGraph memory primitive.

**Backend = `MemorySaver` (in-process), not Redis — deliberately.** The persistent
`langgraph-checkpoint-redis` requires `langgraph-checkpoint >= 4.1`, i.e. a **major LangGraph
upgrade** from the pinned `0.3.18`, which would destabilize the whole graph. Since production
runs a **single uvicorn worker**, one process holds all threads and in-process memory works
across requests. The accepted trade-off: **memory resets on restart/deploy** — fine for short
sales chats, and Tier 2 recovers the important context anyway. Redis-backed persistence is a
fast-follow gated on a LangGraph upgrade.

**Prerequisite work this forced (and why it's good on its own):** the checkpointer *serializes*
the state, so non-serializable objects had to leave it — the live Qdrant client became a
singleton (`db.get_qdrant_client()`, ADR-adjacent) and the Langfuse trace moved to a
ContextVar. `instruction_prompt` (a live prompt object) was dropped from the returned state.

### Tier 2 — long-term: semantic recall from Qdrant `chat_logs`

`retrieve_user_context` now embeds the **actual query** (not a zero vector) and does top-k
recall of *this user's* most relevant past exchanges, above a score floor, returning
`User: … / Assistant: …` pairs into the grounding context. It **skips shared/anonymous
`user_id`s** (`anon`, `experiment`, empty) so one visitor never sees another's history. This
is persistent (Qdrant), so it survives restarts and bridges sessions — exactly what Tier 1's
in-process saver can't.

## Consequences

**Positive**
- The agent follows a conversation ("and the price?" resolves) via Tier 1.
- Returning users / post-deploy context is recovered via Tier 2.
- State is now fully serializable — a cleaner, checkpointer-ready design.
- Both tiers are env-tunable (`MAX_HISTORY_MESSAGES`, `USER_CONTEXT_TOP_K/SCORE_THRESHOLD`).

**Negative / limits**
- Tier 1 memory is lost on restart/deploy (in-process). Documented; Redis is the upgrade path.
- `MemorySaver` is an **unbounded in-process store** — it retains every `thread_id`'s
  checkpoints for the process lifetime and never evicts, so the restart/deploy that loses
  memory is also its only garbage collection. At single-worker scale with regular deploys
  this is acceptable (each thread is itself capped at `MAX_HISTORY_MESSAGES`), but a
  long-uptime worker with many distinct users would grow unbounded → a periodic thread
  sweep (or the Redis checkpointer with TTLs) is the fix when it matters.
- Tier 2 recall quality is capped by the `chat_logs` embedding (a combined user+response+intent
  blob) and the English-centric embedder — decent, not great. A dedicated turn-level embedding
  would improve it.
- No cross-worker sharing (irrelevant at single-worker scale; would need Redis when scaling out).

## When we'd revisit

- **Scale past one worker**, or want memory to survive deploys → adopt the Redis/Postgres
  checkpointer (needs the LangGraph major bump).
- **Better long-term recall** → embed each turn on its own and/or a multilingual embedder
  (ties into the RAG-quality eval work).
