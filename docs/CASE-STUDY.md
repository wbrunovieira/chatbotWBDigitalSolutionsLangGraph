# Case study — from a leaky chatbot to a measured, tool-using agent

A production chatbot for [WB Digital Solutions](https://www.wbdigitalsolutions.com) that was
quietly losing leads. This is what I diagnosed, what I shipped, and the measured results —
every number below is real (produced by the eval suite / verified in production), not
illustrative.

## 1. The problem, found in the data

I pulled the production conversation logs (Qdrant `chat_logs`) instead of guessing. The
sample was small and revealing: **~14 real lead conversations in 5 months**, and the
classifier was **deflecting the few that arrived**:

- `"boa tarde"` (good afternoon) → classified **off_topic** → the bot replied, in English,
  that it "only helps in English." A greeting, from a Brazilian lead, sent away.
- `"vcs fazem automassao?"` ("do you do automation?", with a typo) → **off_topic** → deflected.
  A real automation inquiry — a core WB service — lost to a misspelling.

Root cause: brittle intent classification (a non-deterministic `set` + substring matching over
free LLM text) and a prompt whose greeting examples didn't include time-of-day greetings.

## 2. What I shipped

Six increments, each its own reviewed PR, each gated by CI:

1. **Fixed classification** — structured JSON output (enum, not substring), a corrected prompt
   (time-of-day greetings in pt/en/es/it, typo tolerance, "a service question is never
   off_topic"), and the prompt sources collapsed to one.
2. **A real tool-using agent** — the model *decides* to call `create_lead` (→ the WB-CRM),
   `schedule_meeting` (→ booking link), or `handoff_to_human`, in a bounded tool loop.
   Pydantic-validated args, timeout + retry, graceful fallback, and a per-IP lead cap.
   Pricing was removed from chat — a price question now *captures the lead* instead of quoting.
3. **MCP server** — the same tools exposed over the Model Context Protocol, callable by any
   MCP client (Claude Desktop, Cursor). One implementation, two consumers.
4. **Evals in CI** — the labelled datasets (including the real production failures) run against
   the live model on every relevant PR and **fail the build** on regression.
5. **Prompt-injection defense** — the user's text is treated as untrusted; the system prompt is
   hardened (never obey embedded instructions, never leak the prompt, stay on scope) with a
   canary + output backstop, and an adversarial eval gates it. Threat model documented.
6. **This showcase** — one-command demo + case study.

Underneath, a senior platform layer already existed and was hardened first: per-IP rate
limiting, a daily spend circuit-breaker, CORS/docs lockdown, the origin moved behind Cloudflare,
and CI/CD with a manual-approval production gate.

## 3. Results (measured)

| Dimension | Before | After |
|---|---|---|
| Intent accuracy (eval set, incl. the real failures) | untested; `boa tarde`/typos → off_topic | **100%** (34/34), verified live in prod |
| Leads captured by the bot | 0 (deflected to a frontend handoff) | `create_lead` fires and **persists to the CRM** — verified end-to-end (HTTP 201) |
| Tool selection (labelled action messages) | n/a (no tools) | **90.9%** (10/11) |
| Prompt-injection resistance | none | **11/11** attacks resisted, **0** prompt leaks |
| Over-refusal (does hardening break real use?) | n/a | **4/4** benign requests still answered |
| Regressions reaching production | silent (that's how `boa tarde` shipped) | **0** — the eval gate blocks them pre-merge |
| Automated tests | 0 (repo had none) | **119**, plus 3 live-model eval gates |

Every quality number is reproducible: `python evals/run_intents.py`, `run_tools.py`,
`run_adversarial.py` (see the eval gate in `.github/workflows/evals.yml`).

## 4. Engineering posture

- **Diagnosis from data, not vibes** — the work started by reading production logs.
- **Shipped in small, reviewed, CI-gated PRs** — each with a Definition of Done; each sent
  through an adversarial senior review and its findings fixed before merge (e.g. a duplicate-
  lead retry bug and a case-sensitive guardrail bypass were caught and fixed pre-merge).
- **Self-verifying** — quality is *measured and gated*, not asserted; a prompt regression turns
  CI red before it can reach a lead.
- **Honest about limits** — the threat model documents the paraphrase-leak gap and the
  unhardened paths rather than overclaiming.

## 5. Try it

`docker compose -f compose.demo.yaml up` (see the README Quickstart) brings up the API +
Qdrant + Redis + a stub CRM and a chat widget at `http://localhost:8000/demo`. Ask
*"quanto custa um site?"* or *"meu nome é João da Padaria Central, quero um site"* and watch it
capture the lead. Run the evals yourself to reproduce the numbers above.
