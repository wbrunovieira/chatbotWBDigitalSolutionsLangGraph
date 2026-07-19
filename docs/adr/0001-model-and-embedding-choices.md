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

- **Cost.** DeepSeek is roughly an order of magnitude cheaper per token than *frontier* models
  (GPT-4o / Claude Sonnet), and it runs a **50% off-peak discount (16:30–00:30 UTC)** that the
  `deepseek_optimizer` exploits. Budget models like `gpt-4o-mini` or Claude Haiku sit in a
  *similar* price tier — DeepSeek wins there on the off-peak discount and on not adding a
  second vendor account/dependency, not on raw token price.
- **Migration path.** DeepSeek exposes an **OpenAI-compatible** REST API, so each call is a
  thin `httpx` POST using the OpenAI `tools` / `tool_calls` shape. The endpoint is currently
  hardcoded at ~4 call sites; centralizing it behind a small client abstraction (planned —
  see "When we'd revisit") turns a provider swap into a one-line change.
- **Function calling.** `deepseek-chat` supports tool/function calling, which the agent loop
  (`_run_tool_loop`, `max_iters=3`) depends on — a hard requirement, not a nice-to-have.
- **Trade-off accepted:** on the hardest reasoning/instruction-following, DeepSeek trails the
  frontier models. For this domain (short grounded answers + clear tool triggers) that gap
  is not worth ~10× the cost.

### 2. Embeddings: FastEmbed (ONNX) `all-MiniLM-L6-v2`, 384-dim — **no PyTorch**

- **Why ONNX/FastEmbed over `sentence-transformers`.** SentenceTransformers pulls in PyTorch,
  which dominated the image. The image shrank in two steps: first `.dockerignore` + a
  multi-stage build + CPU-only wheels (~10.5 GB → ~3 GB, commit `6365a46`), then dropping
  PyTorch entirely for FastEmbed / ONNX Runtime (commit `9fdc5c0`). The **current image
  measures ~780 MB** (`docker images wb-chatbot`), with the *same* model weights and 384-dim
  vector space — a pure win on host cost and deploy/pull time.
- **Why MiniLM-L6.** 384-dim, tiny, fast on CPU, and the KB is small (~20 chunks after
  chunking `company_info.md`), so a heavier embedder buys little retrieval quality here.
- **Known trade-off (observed during RAG bring-up, not yet eval-backed):** `all-MiniLM-L6-v2`
  is English-centric. Our KB is in English while queries are multilingual, so cross-lingual
  cosine scores are compressed — during the RAG work, relevant pt→en matches were seen around
  ~0.20–0.40 while off-topic sat ~0.15, which is why the retrieval score threshold is a low,
  env-tunable **0.2** (`config.COMPANY_SCORE_THRESHOLD`, used in `retrieve_company_context`).
  Retrieval is correct today, but the headroom is thin; a RAG-quality eval set would put real
  numbers on this.

### 3. Runtime: `python:3.11-slim`, CPU-only

No GPU, no PyTorch. All embedding is ONNX-on-CPU; all generation is a remote API call. Keeps
the box cheap and the image small.

### 4. Data handling (accepted risk, called out explicitly)

User messages — and whatever a visitor volunteers to `create_lead` (name / business / contact)
— are sent over TLS to `api.deepseek.com`, an **offshore (China-based) provider**. For a
pt-BR / EU-facing bot this carries LGPD/GDPR weight, so the position is stated rather than
hidden:

- The bot captures **only what the user volunteers**; it never solicits sensitive personal
  data (the KB's own "Security Guidelines for Chatbot Interactions" enforce this).
- PII currently lands in `chat_logs` with no TTL and in traces — a **known gap**, tracked
  separately (PII redaction + a retention policy are backlog items, not yet shipped).
- We do not intentionally send data for training; DeepSeek's own data-usage terms are the
  residual risk accepted in exchange for the cost profile.
- If a client ever requires data residency or a no-offshore guarantee, the provider-swap path
  (model routing, below) is the mitigation — route those tenants to an EU/US provider.

## Consequences

**Positive**
- Very low per-conversation cost; worst case additionally bounded by the spend circuit-breaker.
- ~780 MB image, fast pulls/restarts, runs comfortably alongside other services on one VPS.
- Provider-swappable LLM layer (OpenAI-compatible) and a stable 384-dim vector space.

**Negative / risks**
- Ceiling on answer quality vs frontier models (accepted for this domain).
- English-centric embeddings cap cross-lingual retrieval quality; the low threshold is a
  workaround, not a fix.
- Single provider / single embedder = a dependency risk with no automatic fallback yet.
- Data residency: user text + lead PII leave the region (see §4).
- **Not yet quantified here:** DeepSeek's context-window headroom under large RAG stuffing,
  p50/p95 latency (traced in Langfuse but not held to an SLO), and API rate limits against a
  hostile public endpoint. Fine at current scale; unmeasured.

## Alternatives considered

- **OpenAI `gpt-4o-mini` / Anthropic Claude Haiku** — comparable price tier and better
  instruction-following, but they'd add a second vendor and don't get DeepSeek's off-peak
  discount. Reconsider for the *generation step only* (below).
- **`sentence-transformers` (PyTorch)** — identical model, but the PyTorch dependency made the
  image several GB larger for no retrieval gain.
- **A multilingual embedder (e.g. `multilingual-e5`)** — would fix the cross-lingual score
  compression, at a larger model / bigger image. Deferred until retrieval quality (not cost)
  becomes the bottleneck.

## When we'd revisit

- **Model routing + fallback** (backlog): a cheap/fast model for intent + a stronger model for
  *generation only*, plus a secondary provider as a fallback if DeepSeek is down. This is
  where a frontier model earns its cost — on the one step users read closely — and it's also
  the natural home for the client abstraction that removes the ~4 hardcoded endpoints.
- **Multilingual embeddings:** swap `all-MiniLM-L6-v2` for a multilingual model if the KB
  grows or cross-lingual retrieval quality starts costing leads.
- **RAG-quality evals** (backlog): faithfulness + recall@k would replace the "observed"
  cross-lingual figures above with measured ones and catch a bad embedder swap.
- **Prompt-cache economics:** if DeepSeek's off-peak discount or pricing changes materially,
  re-tune the `deepseek_optimizer` caching aggressiveness.
