# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ Sempre rastreie o trabalho como issues (skill `track-work`)
Toda melhoria, correção, feature ou débito técnico DEVE virar issue no projeto
"chatbot-wb" (cmroypyl6001jpd01qyi04zlj) do WB Project Manager, com status em dia.
Invoque a skill `track-work` — ela é **local do operador e não versionada**
(`.claude/` está no `.gitignore`), então num clone novo pode não existir; o board +
a doc da API são a fonte da verdade: https://projects.wbdigitalsolutions.com/api/docs

## Project Overview

FastAPI chatbot for WB Digital Solutions. Uses a LangGraph state machine to orchestrate intent detection, RAG context retrieval (Qdrant), LLM response generation (DeepSeek API), and multi-tier caching (pattern match + Redis). Supports Portuguese, English, Spanish, and Italian.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (requires Redis and Qdrant running, or use Docker)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run with Docker (local development - includes Redis)
docker-compose -f compose.local.yaml up --build

# Run with local Qdrant (adds Qdrant container via override)
docker-compose -f compose.local.yaml -f docker-compose.override.yml up --build

# Production deployment via Ansible
cd ansible && ansible-playbook -i inventory.ini playbook.yml
```

There are no tests in this project.

## Architecture

### Request Flow

```
POST /chat → Pattern cache check → Redis cache check → LangGraph state machine → Cache result → Return
```

### LangGraph State Machine (`graph_config.py`)

The graph routes based on detected intent:
- **greeting** → `generate_greeting_response` (hardcoded, no API call) → END
- **off_topic** → `generate_off_topic_response` (LLM redirect) → END
- **chat_with_agent** → END (handled by frontend)
- **normal flow** → `retrieve_company_context` → `retrieve_user_context` → `augment_query` → `response_generation` → `response_revision` → `log_saving` → END

State is a plain `Dict[str, Any]` passed through nodes. The Qdrant client is a process-wide
singleton (`db.get_qdrant_client()`), not carried in state.

### Three-Tier Caching

1. **Pattern match** (`cached_responses.py`): Regex patterns → pre-built responses. Zero latency, zero API cost. Checked first in `main.py`.
2. **Redis** (`cache.py`): SHA256 of `{message}_{language}_{current_page}` as key. 7-day TTL. Checked second.
3. **DeepSeek context caching**: HTTP headers in `deepseek_optimizer.py` signal cache preferences to the API.

### Cost Optimization (`deepseek_optimizer.py`)

DeepSeek offers 50% discount 16:30-00:30 UTC (13:30-21:30 Brazil time). The optimizer:
- Tracks token usage and cost per API call
- Uses aggressive local caching outside discount hours
- Reports usage via `GET /usage-report`

### Key Constants

| Constant | Value | Location |
|----------|-------|----------|
| Embedding model | `all-MiniLM-L6-v2` | `nodes.py:14` |
| Vector dimensions | 384 | throughout |
| Qdrant collections | `company_info`, `chat_logs` | `main.py` |
| Redis cache TTL | 604800s (7 days) | `config.py:20` |
| Response max length | 500 chars (revision) | `nodes.py:348` |
| DeepSeek model | `deepseek-v4-flash` | `nodes.py` |
| API timeout | 30 seconds | `nodes.py` |

### API Endpoints

- `GET /health` — Health check
- `POST /chat` — Main chat (accepts `message`, `user_id`, `language`, `current_page`, `page_url`, `timestamp`)
- `POST /chat/stream` — SSE streaming (partially implemented, uses hardcoded responses)
- `GET /usage-report` — DeepSeek token/cost analytics

## Environment Variables

Required in `.env`:
- `DEEPSEEK_API_KEY` — DeepSeek LLM API key
- `QDRANT_HOST` — Qdrant server URL (cloud or local)
- `QDRANT_API_KEY` — Qdrant auth key (empty for local)
- `REDIS_HOST` — Redis host (default: `localhost`)
- `REDIS_PORT` — Redis port (default: `6379`)
- `REDIS_DB` — Redis DB number (default: `0`)

## Project structure

App code is grouped into topical packages; only `main.py` and `config.py` live at the root
(so `uvicorn main:app` and the deploy pipeline are unchanged).

- **main.py** — FastAPI app, endpoints (`/chat`, `/chat/stream`, `/usage-report`, `/analytics/funnel`), cache orchestration, response shaping.
- **config.py** — Env var loading and all runtime constants.
- **agents/** — `graph_config.py` (LangGraph `StateGraph` wiring + conditional routing), `tools.py` (create_lead / schedule_meeting / handoff_to_human), `mcp_server.py`.
- **nodes/** — graph node functions split by concern: `intent`, `retrieval`, `generation`, `revision`, `logging_node`, `greeting`, `handoff`, `offtopic`, `embeddings`.
- **providers/** — LLM layer: `llm.py` (routing + fallback), `deepseek_client.py` (transport), `deepseek_optimizer.py` (cost/spend tracking).
- **rag/** — `ingest.py` (chunk + embed the KB), `db.py` (Qdrant singleton), `retention.py` (LGPD purge, run via `python -m rag.retention`).
- **core/** — `cache.py` (Redis + semantic cache), `behavior.py` (lead scoring), `language.py` (language resolution).
- **safety/** — `guardrails.py` (injection pre-filter, output backstop, PII redaction), `security.py` (rate limit + spend cap).
- **observability/** — `langfuse_client.py`, `langfuse_prompts_v3.py` (prompt fallbacks), `analytics.py` (conversion funnel).
- **company_info.md** — Company profile used for RAG (loaded into Qdrant `company_info` collection).
