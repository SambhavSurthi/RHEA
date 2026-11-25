# Project structure and ownership

This document describes the production-oriented layout introduced during cleanup. Git metadata, commit history and CI files were intentionally removed; this folder is the complete project.

## Top level

| Path | Responsibility |
|---|---|
| `backend/` | API application, pipelines, stores, services, tests, demo data, backend image |
| `frontend/` | Streamlit UI and its image |
| `infra/` | Docker Compose topology for Neo4j, Qdrant, API and frontend |
| `docs/` | Architecture decisions, hardening checklist, project report, this map |
| `scripts/` | Developer helpers (evaluation, validation) |
| `start-all.ps1` / `stop-all.ps1` | Operational entry points for the whole stack |
| `pyproject.toml` | Single dependency and tool configuration for the whole project |
| `.env` / `.env.example` | Runtime configuration / safe template |

## Backend layers

```
backend/rhea/
├── main.py            create_app() factory; builds Services, mounts routers
├── api/               thin HTTP layer (no business logic)
│   ├── deps.py        get_services() from rhea.state
│   ├── health.py      GET /health
│   ├── ingest.py      POST /v1/ingest, /v1/ingest/sample, /v1/ingest/pdf
│   ├── query.py       POST /v1/query
│   ├── chat.py        POST /v1/chat, /v1/chat/stream (SSE), /v1/chat/clear
│   ├── evaluation.py  POST /v1/evaluate
│   └── admin.py       approvals + approval-gated purge
├── core/              config.py, bootstrap.py (DI), observability.py
├── domain/            models.py (API schemas), canonical.py (canonical records)
├── pipelines/         identity.py (deterministic IDs), ingestion.py, retrieval.py,
│                      pdf.py, evaluation.py, runner.py
├── stores/            relational.py (PostgreSQL/memory canonical store),
│                      vector.py (Qdrant/memory), graph.py (Neo4j/memory)
├── services/          object_store.py (filesystem/memory), embeddings.py, llm.py,
│                      agent.py, chat.py, security.py
└── auth/              rbac.py — roles, API keys, approval tokens

migrations/            Alembic environment + 0001_initial canonical schema
scripts/migrate.ps1    migration entry point
```

### Why these boundaries

- **api/** stays transport-only: validation, auth dependencies, response models. Business logic lives in pipelines/services, so endpoints can be tested independently and reused by other transports.
- **core/** owns process-wide concerns (settings, dependency graph, metrics/tracing). `bootstrap.build_services()` is the only place that chooses real vs. in-memory backends.
- **pipelines/** contains the data transformations: chunking + entity extraction, hybrid retrieval + RRF, PDF page extraction, and evaluation scoring.
- **stores/** isolates the canonical PostgreSQL store, Qdrant and Neo4j behind narrow protocols; in-memory implementations keep CI deterministic. Canonical IDs issued here are the only identity source for derived indexes.
- **services/** hosts LLM providers (local/OpenAI/Anthropic), the single-shot LangGraph agent, the conversational LangGraph agent (memory/streaming/compaction) and injection scanning.
- **domain/** prevents schema duplication between API and pipelines.

## Data flow

```
PDF upload → pipelines/pdf.py (per-page text + original bytes)
           → pipelines/identity.py (stable document/version/chunk IDs)
           → stores/relational.py (canonical document/version/chunk rows)
           → services/object_store.py (original PDF preserved)
           → pipelines/ingestion.py (scan, chunk, embed, extract entities/relations)
           → stores/vector.py (Qdrant) + stores/graph.py (Neo4j)
           → index_sync_state records Qdrant/Neo4j sync per page

Question   → api/chat.py → services/chat.py (LangGraph)
           → pipelines/retrieval.py (vector + BFS graph → RRF → trust rerank)
           → services/llm.py (fenced prompt, [n] citations, token stream)
           → SSE events (step, sources, token, summary, done) → frontend
```

## Tests

`backend/tests/` holds deterministic unit and API tests. They run without Qdrant, Neo4j or paid APIs because `Settings.allow_in_memory_fallback` and the local provider are used. `pyproject.toml` sets `pythonpath = ["backend"]` and `testpaths = ["backend/tests"]`, so `pytest` works from the repository root without extra environment variables.

## Container topology

`infra/docker-compose.yml` builds `backend/Dockerfile` for the API and `frontend/Dockerfile` for Streamlit, and runs PostgreSQL for the canonical store. The API container receives service hostnames (`http://qdrant:6333`, `bolt://neo4j:7687`, `postgresql+psycopg://...@postgres:5432/rhea`) through Compose `environment` entries, overriding host-oriented values in `.env`; the frontend receives `RAG_API_URL=http://api:8000`. The Postgres host port auto-selects a free port in `start-all.ps1` when 5432 is occupied.
