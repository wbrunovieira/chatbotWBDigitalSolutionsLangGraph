# ADR 0001 — LLM, embedding, and runtime choices

- **Status:** Accepted
- **Date:** 2026-07-18
- **Context owner:** Bruno (WB Digital Solutions)

## Context

This is a public-facing sales chatbot embedded on the WB Digital Solutions website. It
answers short, multilingual (pt-BR / en / es / it) questions about services, grounds them in
a small company knowledge base (RAG), and decides when to call tools (`create_lead`,
`schedule_meeting`, `handoff_to_human`). The constraints that actually drive the choices:

- **Cost per conversation must stay low.** Traffic is unpredictable, the endpoint is public
  and hostile, and one `/chat` turn can fan out into multiple LLM calls. Worst-case spend is
  already capped by a daily circuit-breaker, but the *per-call* cost still has to be cheap
  enough that the bot is worth running at all.
- **Small, cheap-to-host container.** It runs on a single Contabo VPS shared with other
  services — not an ML-optimised box. Image size and cold-start matter.
- **Answer quality is "good enough for a sales concierge", not frontier reasoning.** Replies
  are 2–3 short paragraphs; the hard problems are routing, retrieval, and tool-calling, not
  long-form reasoning.

## Decision

### 1. LLM: DeepSeek (`deepseek-chat`) over OpenAI / Anthropic

- **Cost.** DeepSeek is roughly an order of magnitude cheaper per token than GPT-4-class or
  Claude models, and it runs a **50% off-peak discount (16:30–00:30 UTC)** that the
  `deepseek_optimizer` is aware of. For a high-volume, low-stakes concierge this is the
  dominant factor.
- **Drop-in migration path.** DeepSeek exposes an **OpenAI-compatible** REST API, so the
  client is a thin `httpx` call and swapping providers later (see §"When we'd revisit") is a
  base-URL/key change, not a rewrite.
- **Function calling.** `deepseek-chat` supports tool/function calling, which the agent loop
  (`_run_tool_loop`) depends on — this was a hard requirement, not a nice-to-have.
- **Trade-off accepted:** on the hardest reasoning/instruction-following, DeepSeek trails the
  frontier models. For this domain (short grounded answers + clear tool triggers) that gap
  is not worth ~10× the cost.

### 2. Embeddings: FastEmbed (ONNX) `all-MiniLM-L6-v2`, 384-dim — **no PyTorch**

- **Why ONNX/FastEmbed over `sentence-transformers`.** SentenceTransformers pulls in PyTorch,
  which dominated the image. Moving to FastEmbed (ONNX Runtime) cut the Docker image from
  **~10.5 GB to ~3 GB** (commits `6365a46`, `9fdc5c0`) with the *same* model weights and
  vector space — a pure win on host cost and deploy/pull time.
- **Why MiniLM-L6.** 384-dim, tiny, fast on CPU, and the KB is small (~20 chunks), so a
  heavier embedder buys little retrieval quality here.
- **Known trade-off (measured, not assumed):** `all-MiniLM-L6-v2` is English-centric. Our KB
  is in English while queries are multilingual, so cross-lingual cosine scores are compressed
  — during the RAG work, relevant pt→en matches landed ~0.20–0.40 while off-topic sat ~0.15,
  which is why the retrieval score threshold is a low, env-tunable 0.2 (see
  `nodes.retrieve_company_context`). Retrieval is correct today, but the headroom is thin.

### 3. Runtime: `python:3.11-slim`, CPU-only

No GPU, no PyTorch. All embedding is ONNX-on-CPU; all generation is a remote API call. Keeps
the box cheap and the image small.

## Consequences

**Positive**
- Very low per-conversation cost; worst case additionally bounded by the spend circuit-breaker.
- ~3 GB image, fast pulls/restarts, runs comfortably alongside other services on one VPS.
- Provider-swappable LLM layer (OpenAI-compatible) and a stable 384-dim vector space.

**Negative / risks**
- Ceiling on answer quality vs frontier models (accepted for this domain).
- English-centric embeddings cap cross-lingual retrieval quality; the low threshold is a
  workaround, not a fix.
- Single provider / single embedder = a dependency risk with no automatic fallback yet.

## Alternatives considered

- **OpenAI `gpt-4o-mini` / Anthropic Claude Haiku** — better instruction-following, but more
  expensive and unnecessary for 2–3-paragraph grounded replies. Reconsider for the generation
  step only (below).
- **`sentence-transformers` (PyTorch)** — identical model, but the PyTorch dependency made the
  image ~3.5× larger for no retrieval gain.
- **A multilingual embedder (e.g. `multilingual-e5`)** — would fix the cross-lingual score
  compression, at a larger model / bigger image. Deferred until retrieval quality (not cost)
  becomes the bottleneck.

## When we'd revisit

- **Model routing (planned, backlog #13):** a cheap/fast model for intent + a stronger model
  for *generation only*, plus a secondary provider as a fallback if DeepSeek is down. This is
  where a frontier model earns its cost — on the one step users read closely.
- **Multilingual embeddings:** swap `all-MiniLM-L6-v2` for a multilingual model if the KB
  grows or cross-lingual retrieval quality starts costing leads (RAG-quality evals, backlog
  #19, would surface this).
- **Prompt-cache economics:** if DeepSeek's off-peak discount or pricing changes materially,
  re-tune the `deepseek_optimizer` caching aggressiveness.
