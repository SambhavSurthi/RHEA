# RHEA — Research Hub for Exploration and Analysis

**An AI research paper assistant for reading, querying and analysing technical literature.**

RHEA ingests your PDFs, builds a hybrid retrieval index (vector embeddings + knowledge graph), and answers questions with grounded, streamed responses and precise page-level citations. It is designed as a production-oriented system: separated API and UI, explicit retrieval pipelines, conversation memory, evaluation, observability and containerised infrastructure.

---

## What RHEA does

| Capability | Description |
|---|---|
| **Paper ingestion** | Upload one or more PDFs. Text is extracted **per page**, cleaned, chunked, embedded and indexed. |
| **Hybrid retrieval** | Semantic vector search (Qdrant) is combined with entity/relationship traversal (Neo4j) using Reciprocal Rank Fusion. |
| **Multi-hop reasoning** | Bounded, undirected graph traversal (up to 3 hops) connects facts that never appear in the same paragraph. |
| **Cited answers** | Every factual claim is marked `[n]` and mapped to a citation chip showing the paper, page number, trust level and retrieved snippet. |
| **Streaming & reasoning trace** | Answers stream token-by-token over Server-Sent Events; the UI shows the agent's retrieval and fusion steps. |
| **Conversation memory** | Per-thread chat history is persisted by a LangGraph checkpointer; older turns are auto-summarised when the context budget is reached. |
| **Safety** | API-key RBAC, injection scanning on ingest, source trust scoring, prompt fencing, output validation, approval-gated destructive actions. |
| **Evaluation** | Retrieval hit rate, keyword coverage, groundedness proxy, multi-hop hit rate and latency percentiles. |
| **Observability** | Prometheus metrics and optional OpenTelemetry instrumentation. |
| **Deployment** | Non-root API and frontend images, Docker Compose topology, deterministic test suite. |

---

## Architecture

```mermaid
flowchart LR
    U[Researcher / Browser] --> UI[Streamlit UI :8501]
    UI -->|PDF upload| API[FastAPI :8000]
    UI -->|SSE chat| API

    API --> P[Pipelines]
    P --> PDF[PDF page extraction]
    P --> ING[Chunk + embed + extract entities]
    P --> RET[Hybrid retrieval + RRF + rerank]

    ING --> Q[(Qdrant<br/>vector chunks)]
    ING --> N[(Neo4j<br/>entities & relations)]
    RET --> Q
    RET --> N

    RET --> LG[LangGraph agent]
    LG --> LLM[LLM provider<br/>local / OpenAI / Anthropic]
    LLM --> A[Streamed answer + [n] citations]
    A --> UI
```

### Request flow

**Ingest:** PDF → `pypdf` page extraction → injection scan → chunking (~700 chars) → hashing embeddings → entity/relation extraction → Qdrant + Neo4j.

**Query:** question → entity extraction → vector search + bounded graph traversal → deduplicate and fuse with RRF → lexical/trust reranking → fenced, trust-labelled prompt → LLM → answer with numbered citations → SSE events (`step`, `sources`, `token`, `summary`, `done`).

### Backend layers

```
backend/rhea/
├── main.py            application factory, router assembly
├── api/               transport layer: health, ingest, query, chat, evaluation, admin
├── core/              settings, dependency injection, metrics/tracing
├── domain/            Pydantic request/response schemas
├── pipelines/         PDF, ingestion, retrieval, evaluation, eval runner
├── stores/            Qdrant / Neo4j adapters (+ in-memory fallbacks)
├── services/          LLM providers, embeddings, agents, security scanning
└── auth/              RBAC and approval tokens
```

The API layer contains no business logic; pipelines and services own the transformations. Stores sit behind narrow protocols so the system can degrade gracefully to in-memory backends for local development and CI.

---

## Technology stack

- **Backend:** FastAPI, Pydantic, LangGraph, Uvicorn
- **Retrieval:** Qdrant, Neo4j (Cypher, bounded variable-length paths), hashing embeddings, RRF
- **LLM:** pluggable local extractive provider, OpenAI Responses API, Anthropic Messages API
- **Frontend:** Streamlit
- **Operations:** Docker, Docker Compose, Prometheus, OpenTelemetry, pytest, ruff

---

## Quick start

Requirements: Python 3.11+, Docker Desktop (or Docker Engine), PowerShell on Windows.

```powershell
# Start everything: databases, API, sample ingestion and the UI
powershell -ExecutionPolicy Bypass -File .\start-all.ps1

# Stop everything (data volumes are preserved)
powershell -ExecutionPolicy Bypass -File .\stop-all.ps1
```

The startup script creates `.env` from `.env.example` if needed, prepares `.venv`, starts Docker Desktop if it is stopped, waits for Neo4j and Qdrant to become healthy, launches the API and Streamlit, and auto-selects alternative ports if 8000/8501 are already taken.

| Service | Default URL |
|---|---|
| Streamlit UI | `http://127.0.0.1:8501` |
| API docs (Swagger) | `http://127.0.0.1:8000/docs` |
| Health check | `http://127.0.0.1:8000/health` |
| Neo4j Browser | `http://localhost:7474` (`neo4j` / `rhea-demo`) |
| Qdrant dashboard | `http://localhost:6333/dashboard` |

Demo API keys are configured in `.env`: `demo-reader-key`, `demo-writer-key`, `demo-admin-key`.

---

## Using RHEA

1. **Upload papers** in the sidebar (one or many PDFs) and click **Embed + index PDFs**. The result shows pages, chunks, entities and relations written to Qdrant and Neo4j.
2. **Ask a question** in the chat box. Answers stream progressively. Expand **Agent reasoning** to see retrieval statistics and fusion steps.
3. **Follow the citations** below each answer. `[1]` maps to a chip containing the source document, exact page, trust badge, retrieval type, graph hop distance and the underlying text.
4. **Continue the conversation.** Follow-ups reuse the same thread. The sidebar shows turn count and any auto-generated memory summary.
5. **New chat** starts a fresh thread and clears server-side memory.

For natural, fully synthesised answers, set `LLM_PROVIDER=openai` or `anthropic` and the matching API key in `.env`, then restart. The default `local` provider is deterministic and offline.

### REST API

| Method | Endpoint | Role | Purpose |
|---|---|---|---|
| GET | `/health` | public | Backend and provider health |
| POST | `/v1/ingest/sample` | writer | Load the bundled demo corpus |
| POST | `/v1/ingest` | writer | Ingest text documents |
| POST | `/v1/ingest/pdf` | writer | Upload and index PDFs |
| POST | `/v1/query` | reader | Single-shot hybrid query |
| POST | `/v1/chat` | reader | Conversational query with memory |
| POST | `/v1/chat/stream` | reader | SSE stream of steps, sources and tokens |
| POST | `/v1/chat/clear` | reader | Clear a conversation thread |
| POST | `/v1/evaluate` | admin | Run retrieval/quality evaluation |
| GET | `/metrics` | admin | Prometheus metrics |
| POST | `/v1/admin/approvals` | admin | Mint approval token for destructive actions |
| POST | `/v1/admin/purge` | admin + approval | Clear in-memory stores |

---

## Configuration

Key settings in `.env` (see `.env.example` for the full template):

| Group | Variables |
|---|---|
| LLM | `LLM_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |
| Vector store | `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION=rhea_papers` |
| Graph store | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` |
| Retrieval | `EMBEDDING_DIM`, `TOP_K_VECTOR`, `TOP_K_GRAPH`, `RRF_K`, `GRAPH_MAX_HOPS` |
| Memory | `MEMORY_MAX_TOKENS`, `MEMORY_KEEP_RECENT` |
| Safety | `BLOCK_QUARANTINED_INGEST`, `EXCLUDE_QUARANTINED_FROM_CONTEXT`, `API_KEYS_*` |
| Tracing | `OTEL_ENABLED`, `OTEL_SERVICE_NAME` |

---

## Development

```powershell
python -m pip install -e '.[dev]'                         # install with dev extras
uvicorn rhea.main:app --reload                           # API only
pytest                                                   # 42 deterministic tests
ruff check backend/rhea backend/tests frontend/streamlit_app.py
python -m rhea.pipelines.runner                          # evaluation report
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

Docker Compose builds both services from the root context:

```powershell
docker compose -f infra/docker-compose.yml up --build
docker compose -f infra/docker-compose.yml down
```

---

## Repository structure

```
rhea/
├── backend/           API, pipelines, stores, services, tests, demo data, Dockerfile
├── frontend/          Streamlit application, Dockerfile
├── infra/             Docker Compose topology
├── docs/              architecture decisions, hardening notes, project report, structure map
├── scripts/           validation and evaluation helpers
├── start-all.ps1      one-command start
├── stop-all.ps1       one-command stop
└── pyproject.toml     dependencies and tool configuration
```

Detailed module ownership is documented in [`docs/STRUCTURE.md`](docs/STRUCTURE.md).

---

## Agent harness and project tracking

This repository is designed to be worked on by AI agents with a strict, auditable protocol:

- [`AGENTS.md`](AGENTS.md) — how to work in the codebase (architecture, commands, conventions).
- [`AGENTRULES.md`](AGENTRULES.md) — mandatory behavior, verification, session logging and the codebase-memory-first rule.
- [`Agent.md`](Agent.md) — short alias pointing to `AGENTS.md`.
- [`docs/NAVIGATION.md`](docs/NAVIGATION.md) — read order and what-lives-where.
- `docs/agent-logs/` — one mandatory log per agent session.
- `docs/audits/` — safety and incident records.
- `docs/issues/` — `RHEA-XXX` issue tracker including `solved/`.
- `docs/plans/` — design proposals before non-trivial changes.
- `docs/runbooks/` — repeatable operations.
- `docs/user-guide/` — researcher-facing instructions.

Every agent must index its steps into codebase memory (`codebase-memory`, project name `rhea`) and perform code retrieval through that graph first; plain file search is a declared fallback only. Read `AGENTRULES.md` before making changes.

**Living documentation:** the structure, stack and behaviour of RHEA are not fixed. Any change to folders, tools, libraries, endpoints or behaviour must update every affected doc, rule file and map in the same change set, then re-index codebase memory. Stale docs are treated as defects. The canonical remote is `https://github.com/SambhavSurthi/RHEA.git` on branch `main`.

---

## Current engineering status

The Phase 1 repository audit is complete: [`docs/architecture-audit.md`](docs/architecture-audit.md) documents the verified root causes of irrelevant retrieval, wrong answers and unverifiable citations, including live API probe evidence. The phased rebuild plan is [`docs/plans/RHEA-001-production-rag-rebuild.md`](docs/plans/RHEA-001-production-rag-rebuild.md), with a detailed [`Phase 1 canonical-architecture plan`](docs/plans/RHEA-001-phase-1-canonical-architecture.md), tracked by [`docs/issues/RHEA-001-irrelevant-retrieval-and-weak-grounding.md`](docs/issues/RHEA-001-irrelevant-retrieval-and-weak-grounding.md). **No implementation code has been changed by Phase 1**; the plan awaits owner approval.

## Security notes

Credentials and API keys are environment-driven; `.env` is excluded from container build contexts. Replace demo keys before any non-local deployment. The current safety layer includes RBAC, injection pattern scanning, trust-weighted ranking, prompt fencing and output validation; a production deployment should add TLS, a real identity provider, tenant isolation, rate limiting and a trained injection classifier (see `docs/production-hardening.md`).

## License

MIT — see [LICENSE](LICENSE).
