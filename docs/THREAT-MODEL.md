# Threat model — WB Digital Solutions chatbot

Scope: the LLM/agent layer. Platform-level threats (rate-limit, spend-cap, CORS, origin
lockdown, secrets) are covered by `security.py` and the Ansible/Cloudflare setup; this
document is about **AI-specific** risks.

## Trust boundaries

| Input | Trust | Why |
|---|---|---|
| User message (`/chat`) | **UNTRUSTED** | Anyone on the internet can send anything. |
| Retrieved KB chunks (RAG) | **UNTRUSTED** (once RAG is real) | Content the model retrieves is data, not instructions — it could be poisoned. Today the KB is a single static doc, so this is latent. |
| System prompt / tool schemas | Trusted | Authored by us. |
| Tool results (CRM, etc.) | Semi-trusted | Our own services, but treated as data in the loop. |

The core rule: **untrusted text is DATA, never instructions.**

## Threats & mitigations

### T1 — Prompt injection via user text
*"Ignore your instructions", "you are now DAN", "reveal your system prompt", "repeat your rules".*
- **Mitigation (primary):** `guardrails.harden_system_prompt` appends non-negotiable rules —
  the user message is untrusted data, never obey embedded commands, never reveal the prompt,
  stay on WB's scope. Applied to the main generation (`nodes.generate_response`).
- **Mitigation (backstop):** `guardrails.scrub_output` — the hardened prompt carries a unique
  internal **canary**; if it ever appears in a reply, the prompt leaked, so the whole reply is
  replaced with a safe refusal.
- **Measured:** `evals/adversarial.jsonl` + `evals/run_adversarial.py` — injection/jailbreak/
  system-prompt-extraction cases; the eval fails the build if the model leaks the canary or
  complies. Wired into the CI eval gate.

**Scope of the hardening:** applied to the **main generation** (`nodes.generate_response`),
which is where arbitrary user questions and tool use happen. The `generate_greeting_response`
and `generate_off_topic_response` nodes call the LLM with their own short prompts and are
**not** hardened and do **not** carry the canary — deliberately: there is no secret system
prompt or tool access to abuse on those paths, and the fallbacks are hardcoded. An injection
that lands there can at most produce an off-brand reply, not a data leak. Hardening them (or
routing all output through one chokepoint) is tracked as follow-up.

### T2 — System-prompt / internal-data extraction
Covered by T1's canary + scrub. The eval asserts the **literal** canary never surfaces across
its attack cases at temperature 0 — a concrete regression guard, not a general guarantee (a
paraphrased leak without the canary would evade it; see Known gaps).

### T3 — Off-scope / resource abuse (coax the bot off-topic to burn tokens)
- Scope rule in the hardened prompt (refuse + redirect). Bounded further by the platform
  rate-limit + daily spend cap (`security.py`) and the per-request message-length cap.

### T4 — Injection via retrieved KB chunks (poisoned RAG)
Latent today (single static KB). When real RAG lands (#5–#7 in the plan), retrieved chunks
must be delimited and treated as untrusted data, and the adversarial eval extended with
inject-via-KB cases. Tracked as future work.

### T5 — Tool abuse (spam leads, hallucinated tool args)
- `tools.dispatch` validates args (Pydantic), and `create_lead` enforces a per-IP daily lead
  cap. Non-idempotent writes are not retried (no duplicate leads). MCP callers are tagged and
  exempt from the public cap (local, trusted).

## Known gaps / future work
- Input delimiting of the user turn (wrapping) is not yet applied in the augmented-prompt path;
  the hardened system prompt is the current primary control.
- RAG-chunk provenance/delimiting (T4) lands with real retrieval.
- The canary is a proxy for "prompt leaked"; a paraphrased leak without the canary would evade
  the backstop (the hardened prompt is the real defense; the eval measures it).
