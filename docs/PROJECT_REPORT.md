# Project Report — RHEA - Research Hub for Exploration and Analysis

**Repository:** `D:\Capstone\rhea`
**Report date:** 26 November 2026
**Author of the project:** RHEA (MIT license)
**Report scope:** what the system is, how it works, and how to run/use it on this machine.

---

## 1. Executive summary

This is a **production-shaped hybrid Retrieval-Augmented Generation (RAG) API**. Instead of relying only on vector similarity, it combines:

- **Qdrant** vector search (semantic similarity), and
- **Neo4j** knowledge-graph traversal (explicit relationships and multi-hop reasoning),

fuses their results with **Reciprocal Rank Fusion (RRF)**, reranks lightly by lexical overlap and source trust, and generates a **grounded answer with cited sources** through a LangGraph state machine. It is packaged as a FastAPI service with RBAC, prompt-injection defenses, evaluation metrics, Prometheus/OTel observability, Docker Compose infrastructure, and scripted validation helpers.

It runs by default in **local deterministic mode** — no paid API key is required. The core design goal is to demonstrate practical LLM engineering (retrieval quality, traceability, safety, operability), not just a chat demo.

A **Streamlit workspace** is included: upload PDFs, watch page-level citations appear in streamed answers, inspect the agent's reasoning steps, and keep conversational memory with automatic context compaction.

---

## 2. What it does (capabilities)

| Capability | Implementation |
|---|---|
| Hybrid retrieval | Qdrant vector search + Neo4j graph search, merged with RRF (`score += 1/(k + rank)`, k=60) |
| Multi-hop graph reasoning | Bounded BFS up to `GRAPH_MAX_HOPS=3` (hard cap 4), undirected traversal; per-source `graph_hop_distance` makes reasoning inspectable |
| Knowledge graph | `(Document)-[:MENTIONS]->(Entity)`, `(Entity)-[:RELATED {kind}]->(Entity)` with kinds `DEPENDS_ON`, `MONITORED_BY`, `RUNS_ON`, `OWNED_BY` |
| Agent workflow | LangGraph: `retrieve` → `generate` → `END` (single-shot); `prepare` → `retrieve` → `generate` → `remember` (chat, with `MemorySaver` checkpointer) |
| PDF ingestion | `POST /v1/ingest/pdf` extracts each page with `pypdf`, then chunks/embeds/extracts entities and indexes pages into Qdrant + Neo4j with `document`/`page` metadata |
| Page-level citations | Numbered `[n]` markers in the answer (prompt-enforced for hosted LLMs), rendered as chips with document name, page, trust badge, hop distance and snippet |
| Streaming + reasoning | SSE endpoint `/v1/chat/stream` emits `step`, `sources`, `token`, `summary`, `done` events; the UI renders tokens progressively and shows a reasoning trace |
| Conversation memory + compaction | Per-thread history and summary stored by the LangGraph checkpointer; older turns auto-summarized when the word budget is exceeded (`MEMORY_MAX_TOKENS`, default 1800) |
| LLM providers | `local` (offline extractive, default), `openai` (Responses API), `anthropic` (Messages API) behind one interface |
| Embeddings | Deterministic offline `HashingEmbedder` (384 dims, blake2b token hashing); swappable |
| Safety | Injection-pattern scanning on ingest, trust labels (`trusted`/`unverified`/`quarantined`), trust-weighted ranking, quarantined content excluded from context, prompt fencing, output validation |
| Access control | API-key RBAC (`reader` < `writer` < `admin`) plus a separate, single-use, 5-minute approval token for destructive actions |
| Evaluation | Retrieval hit rate, keyword coverage, groundedness proxy, multi-hop hit rate, p50/p95 latency |
| Observability | Prometheus counters/histograms at `/metrics`; optional OpenTelemetry FastAPI instrumentation |
| Resilience | Graceful in-memory fallback for Qdrant/Neo4j when unavailable (`ALLOW_IN_MEMORY_FALLBACK=true`) |
| Deployment | Non-root backend and frontend Dockerfiles, Docker Compose with healthchecks/volumes, scripted `pytest` + `ruff` validation (no external services) |

---

## 3. Architecture and request flow

```
Streamlit UI (:8501)  --SSE-->  FastAPI (:8000)  -- X-API-Key RBAC
        |                             |
        | PDF upload                  +--> LangGraph RAGAgent: retrieve -> generate
        |                             +--> LangGraph ConversationalRAG (chat.py):
        |                                    prepare -> retrieve -> generate -> remember
        |                                    (MemorySaver checkpointer + auto-summary)
        v                                    |
backend/rhea/pipelines/pdf.py (per-page text) ------------------+
                                             |
                                             +--> HybridRetriever (backend/rhea/pipelines/retrieval.py)
                                                   +--> HashingEmbedder + QdrantVectorStore  (vector)
                                                   +--> Neo4jGraphStore (BFS, multi-hop)      (graph)
                                                   +--> RRF + lexical bonus + trust weighting
                                            |
                                            v
                                   LLMProvider (backend/rhea/services/llm.py): local | OpenAI | Anthropic
                                            |
                                            v
                        Grounded answer + [n] citations + reasoning steps
```

**Ingestion flow:** document → injection scan → trust classification → chunking (≈700 chars) → entity/relation extraction → `graph_store.index_document()` → embeddings → `vector_store.upsert()`.

**Query flow:** question → embed + extract entities → vector search (`TOP_K_VECTOR=8`) + graph search (`TOP_K_GRAPH=8`, up to 3 hops) → dedupe (overlaps become `retrieval="hybrid"`) → drop quarantined → score = RRF + `0.15 × lexical_bonus`, multiplied by trust weight (1.0 / 0.6 / 0.0) → top-k → prompt with fenced, trust-labeled context → answer.

---

## 4. Repository map

| Path | Purpose |
|---|---|
| `backend/rhea/main.py` | FastAPI app, all HTTP routes, RBAC dependencies |
| `backend/rhea/core/bootstrap.py` | Dependency wiring; chooses Qdrant/Neo4j or in-memory backends and LLM provider |
| `backend/rhea/core/config.py` | `pydantic-settings` configuration loaded from `.env` |
| `backend/rhea/services/agent.py` | LangGraph state machine (single-shot) and timing |
| `backend/rhea/services/chat.py` | Conversational LangGraph: memory, streaming events, auto-compaction |
| `backend/rhea/pipelines/pdf.py` | PDF page extraction, page-scoped documents, citation labels |
| `backend/rhea/pipelines/retrieval.py` | Hybrid retrieval, RRF, reranking, dedup, trust weighting |
| `backend/rhea/services/embeddings.py` | Deterministic hashing embedder + cosine similarity |
| `backend/rhea/stores/vector.py` | Qdrant and in-memory vector stores |
| `backend/rhea/stores/graph.py` | Neo4j and in-memory graph stores, BFS traversal, hop distance |
| `backend/rhea/pipelines/ingestion.py` | Chunking, entity/relation extraction, sample loader, ingestion service |
| `backend/rhea/services/llm.py` | Provider abstraction and trust-fenced prompt construction |
| `backend/rhea/domain/models.py` | Pydantic request/response schemas |
| `backend/rhea/auth/rbac.py` | API-key roles and approval-token gate |
| `backend/rhea/services/security.py` | Injection patterns, trust scoring, output validation |
| `backend/rhea/pipelines/evaluation.py` / `backend/rhea/pipelines/runner.py` | Evaluation harness + CLI (`python -m app.eval_runner`) |
| `frontend/streamlit_app.py` | New UI: PDF upload, streaming chat, reasoning, citations, memory controls |
| `backend/rhea/core/observability.py` | Prometheus metrics and OTel setup |
| `backend/data/` | 4 demo markdown docs + `eval.json` (6 cases, 2 multi-hop) |
| `backend/tests/` | 10 deterministic test files (unit + API-level + PDF/chat memory, no external DB needed) |
| `docs/` | Architecture decisions (ADR-001…004) and production-hardening checklist |
| `infra/docker-compose.yml` / `backend/Dockerfile` | Neo4j, Qdrant, API container; non-root production image |
| `Makefile` | `install`, `dev`, `infra`, `up`, `test`, `lint`, `eval`, `clean` |
| **`start-all.ps1` / `stop-all.ps1`** | **New one-command startup/shutdown scripts (this report's deliverables)** |
| **`PROJECT_REPORT.md`** | **This document** |

---

## 5. One-command operation (new scripts)

### 5.1 Start everything

Open PowerShell in the project directory and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-all.ps1
```

It performs, in order:

1. Creates `.env` from `.env.example` if missing.
2. Creates `.venv` and installs `pip install -e '.[dev]'` if missing (first run only).
3. **Starts Docker Desktop** if installed but stopped, waits for the daemon; if Docker is genuinely unavailable, continues in **in-memory fallback mode** so the API still runs.
4. Runs `docker compose up -d neo4j qdrant` and waits until Neo4j reports `healthy` (Docker healthcheck + bolt port 7687) and Qdrant `/readyz` returns 200.
5. Starts `uvicorn rhea.main:app --host 127.0.0.1` in the background, writes logs to `.run\api.log` / `.run\api.err.log`, records PID in `.run\api.pid`, and waits for `/health`. If another service occupies the port, it automatically tries 8001, 8002, … and tells the UI where to connect.
6. Calls `POST /v1/ingest/sample` (idempotent) so the demo corpus is immediately queryable.
7. Starts the **Streamlit frontend** (`frontend/streamlit_app.py`) on port 8501 with `RAG_API_URL` pointing at the chosen API port; logs go to `.run\streamlit.log`. It also avoids foreign port conflicts by trying 8502, 8503, … if needed.
8. Prints a status panel with backend names, provider, and URLs.

Useful options:

```powershell
.\start-all.ps1 -SkipIngest                 # don't auto-load sample docs
.\start-all.ps1 -SkipDocker                 # force in-memory fallback
.\start-all.ps1 -ApiPort 9000               # use another port
.\start-all.ps1 -DockerWaitSeconds 240      # longer Docker Desktop startup wait
.\start-all.ps1 -StreamlitPort 8600          # use another UI port
```

It is **idempotent**: if this project's API / UI are already healthy on the chosen ports they are reused instead of launching duplicates. It never reuses a foreign service by accident — it validates `/health` for the API and the process command line for Streamlit.

### 5.2 Stop everything

```powershell
powershell -ExecutionPolicy Bypass -File .\stop-all.ps1
```

It stops the tracked uvicorn and Streamlit PIDs, sweeps for stray `uvicorn rhea.main:app` / `frontend/streamlit_app.py` processes from this project (leaving other projects alone), runs `docker compose down` (containers removed, **named data volumes preserved**), and reports completion.

Options:

```powershell
.\stop-all.ps1 -RemoveVolumes        # also delete neo4j_data / qdrant_data volumes
.\stop-all.ps1 -StopDockerDesktop    # also shut down Docker Desktop
```

Docker Desktop is **not** stopped by default because it may host unrelated workloads.

### 5.3 Verified result on this machine

Both scripts were executed end-to-end. After a stop → start cycle the status panel reported:

```
Vector backend : qdrant (healthy=True)
Graph backend  : neo4j (healthy=True)
LLM provider   : local
Streamlit UI   : http://127.0.0.1:8501
```

On this machine another project was already listening on port 8000; the script detected the foreign `/health` response, automatically selected port **8001**, and pointed Streamlit at it via `RAG_API_URL`. A 2-page test PDF was uploaded through `/v1/ingest/pdf` (2 pages → 2 chunks → 11 entities → 5 relations into Qdrant + Neo4j). A streamed chat returned `step`, `sources`, `token` and `done` events, with `[1] orion_runbook.pdf p.1` citations; a follow-up in the same thread correctly reported "2 recent turn(s)" from memory. Streamlit's own `AppTest` harness ran the UI script with zero exceptions. All **42 tests pass**.

A real query and the bundled evaluation also succeeded:

```json
{ "cases": 6, "retrieval_hit_rate": 100.0, "answer_keyword_coverage": 16.67,
  "groundedness_proxy": 93.59, "multi_hop_cases": 2, "multi_hop_hit_rate": 100.0,
  "p50_latency_ms": 22.43, "p95_latency_ms": 923.1 }
```

> Note: low `answer_keyword_coverage` is expected with `LLM_PROVIDER=local` — the fallback provider extracts a relevant sentence from the top sources instead of synthesizing an answer. Retrieval and multi-hop rates are the meaningful quality signals in local mode.

### 5.4 Streamlit workspace — step by step

Open **`http://127.0.0.1:8501`** (or the port printed by the start script).

1. **Upload a PDF** in the sidebar (one or many). Choose declared trust and click **Embed + index PDFs**. Each page is extracted, split into ~700-character chunks, embedded, and written to Qdrant and Neo4j; the result panel shows pages/chunks/entities/relations and which backends were used.
2. **Ask a question** in the chat box. Tokens stream in progressively. Expand **🧠 Agent reasoning** to see query preparation, vector/graph retrieval counts, RRF fusion, hop depth, and generation.
3. **Read the citations:** each answer ends claims with `[n]`. The numbered chips below the answer show document name, exact page, trust badge, retrieval type (`vector`/`graph`/`hybrid`), graph hop distance, and the underlying text snippet.
4. **Continue the conversation:** follow-up questions reuse the same thread. The sidebar shows turn count; once the context word budget is exceeded, older turns are compacted into an auto-summary (shown in an expander and announced by a toast).
5. **New chat** mints a fresh thread ID and clears both UI history and server-side memory.

> **Answer quality:** `LLM_PROVIDER=local` is an offline deterministic extractor — it is reliable for retrieval/citation demos but does not truly synthesize. For natural, fully reasoned answers, set `LLM_PROVIDER=openai` or `anthropic` plus the API key in `.env` and restart; the same prompt enforces `[n]` citations and trust-fenced context.

---

## 6. Manual operation (alternative to the scripts)

```powershell
# infrastructure only
docker compose up -d neo4j qdrant              # equivalently: make infra

# API in the foreground
.venv\Scripts\activate
uvicorn rhea.main:app --reload                  # equivalently: make dev

# everything in Docker (foreground); see caveat in section 11
docker compose up --build                      # equivalently: make up

# quality checks
pytest                                         # make test
ruff check app tests                           # make lint
python -m app.eval_runner                      # make eval
```

Useful UIs:

| URL | What |
|---|---|
| `http://127.0.0.1:8501` | Streamlit workspace (PDF upload + chat) |
| `http://localhost:8000/docs` | Swagger UI (interactive API; use the actual port if 8000 was taken) |
| `http://localhost:8000/health` | Public health: backends, provider |
| `http://localhost:7474` | Neo4j Browser — user `neo4j`, password `rhea-demo` |
| `http://localhost:6333/dashboard` | Qdrant dashboard |

---

## 7. API reference and usage examples

All endpoints except `/health` require the `X-API-Key` header. Roles: **reader** (query), **writer** (reader + ingest), **admin** (writer + evaluate/metrics/admin). An admin key satisfies lower roles. Demo keys in `.env`: `demo-reader-key`, `demo-writer-key`, `demo-admin-key`.

| Method | Endpoint | Min role | Purpose |
|---|---|---|---|
| GET | `/health` | none | Service + dependency health |
| POST | `/v1/ingest/sample` | writer | Load the 4 bundled markdown documents |
| POST | `/v1/ingest` | writer | Ingest caller-provided documents |
| POST | `/v1/query` | reader | Hybrid retrieval + generation (single-shot) |
| POST | `/v1/ingest/pdf` | writer | Multipart PDF upload → page-aware chunking, embedding and graph indexing |
| POST | `/v1/chat` | reader | Conversational query with thread memory and citations |
| POST | `/v1/chat/stream` | reader | SSE stream: `step`, `sources`, `token`, `summary`, `done` |
| POST | `/v1/chat/clear?thread_id=…` | reader | Forget one conversation thread |
| POST | `/v1/evaluate` | admin | Run bundled or supplied eval cases |
| GET | `/metrics` | admin | Prometheus metrics |
| POST | `/v1/admin/approvals?action=purge` | admin | Mint single-use approval token (5 min TTL) |
| POST | `/v1/admin/purge` | admin + approval | Clear in-memory stores via `X-Approval-Token` |

**PowerShell examples** (curl quoting on Windows can be awkward; these work as-is):

```powershell
# Ingest sample corpus
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/v1/ingest/sample' `
  -Headers @{ 'X-API-Key' = 'demo-writer-key' }

# Query
$body = @{ question = 'What depends on the inference gateway and how is it monitored?'; top_k = 5 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/v1/query' `
  -Headers @{ 'X-API-Key' = 'demo-reader-key'; 'Content-Type' = 'application/json' } -Body $body

# Evaluate (6 bundled cases, 2 of them multi-hop)
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/v1/evaluate' `
  -Headers @{ 'X-API-Key' = 'demo-admin-key'; 'Content-Type' = 'application/json' } -Body '{}'

# Custom document ingestion
$docs = @{ documents = @(@{ source='note.md'; text='The Checkout Service depends on Redis. The Checkout Service is monitored by Datadog.'; trust='unverified' }) } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/v1/ingest' `
  -Headers @{ 'X-API-Key' = 'demo-writer-key'; 'Content-Type' = 'application/json' } -Body $docs

# Upload a PDF (page-aware citations) - use curl.exe for multipart on Windows PowerShell 5.1
curl.exe -X POST 'http://127.0.0.1:8000/v1/ingest/pdf' `
  -H 'X-API-Key: demo-writer-key' -F 'file=@my_manual.pdf' -F 'trust=trusted'

# Conversational query (memory persisted per thread_id)
$chatBody = @{ message = 'What does the Orion Gateway depend on?'; thread_id = 'my-thread'; top_k = 5 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/v1/chat' `
  -Headers @{ 'X-API-Key' = 'demo-reader-key'; 'Content-Type' = 'application/json' } -Body $chatBody
```

A query response contains: `answer`, `sources[]` (`source`, `text`, `score`, `retrieval`: `vector|graph|hybrid`, `trust`, `graph_hop_distance`), `entities[]`, `latency_ms`, `provider`, `output_flagged`.

**Ingest request constraints:** `text` non-empty; `trust` is `trusted` or `unverified` (quarantine is decided by the scanner, never by the caller). **Query request constraints:** `question` ≥ 3 chars; `top_k` 1–20 (default 5).

### Switching to a hosted LLM

Set in `.env` and restart the API:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=<your key>
OPENAI_MODEL=gpt-5-mini
```
or
```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=<your key>
ANTHROPIC_MODEL=claude-sonnet-4-5
```
If the key is missing or the provider name is unknown, it silently falls back to `local`.

---

## 8. Configuration reference (`.env`)

| Group | Variables (defaults) |
|---|---|
| General | `APP_ENV=development`, `LOG_LEVEL=INFO` |
| LLM | `LLM_PROVIDER=local`, `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-5-mini`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL=claude-sonnet-4-5` |
| Qdrant | `QDRANT_URL=http://localhost:6333`, `QDRANT_API_KEY`, `QDRANT_COLLECTION=rhea_papers` |
| Neo4j | `NEO4J_URI=bolt://localhost:7687`, `NEO4J_USER=neo4j`, `NEO4J_PASSWORD=rhea-demo`, `NEO4J_DATABASE=neo4j` |
| Retrieval | `EMBEDDING_DIM=384`, `TOP_K_VECTOR=8`, `TOP_K_GRAPH=8`, `RRF_K=60`, `GRAPH_MAX_HOPS=3` |
| Chat memory | `MEMORY_MAX_TOKENS=1800` (rough word budget before compaction), `MEMORY_KEEP_RECENT=4` (recent turns kept verbatim) |
| Resilience | `ALLOW_IN_MEMORY_FALLBACK=true` |
| Tracing | `OTEL_ENABLED=false`, `OTEL_SERVICE_NAME=rhea` |
| RBAC | `API_KEYS_READER`, `API_KEYS_WRITER`, `API_KEYS_ADMIN` (comma-separated; demo values in `.env`/`.env.example`) |
| Safety | `BLOCK_QUARANTINED_INGEST=false`, `EXCLUDE_QUARANTINED_FROM_CONTEXT=true` |

Environment variables take precedence over `.env`. Note that `config.py` defaults the three API-key settings to empty strings, so an absent `.env` means **no key grants access** — the demo keys come from `.env` / `.env.example`.

---

## 9. Sample data and evaluation

`backend/data/` contains four synthetic enterprise-AI markdown documents (`platform.md`, `data_pipeline.md`, `reliability.md`, `security.md`) describing services, owners, dependencies, monitoring, SLOs, and security controls, plus `eval.json` with six benchmark cases. Two are deliberately constructed as **genuine multi-hop cases** with no shortcut (e.g. *"Which tool monitors the infrastructure that powers the Embedding Cache?"* → Embedding Cache → Redis Cluster → Cloud Provider → Datadog, 3 hops).

Metrics reported by `POST /v1/evaluate` or `python -m app.eval_runner`:

- `retrieval_hit_rate` — expected source retrieved
- `answer_keyword_coverage` — expected facts present in answer
- `groundedness_proxy` — token overlap between answer and retrieved context
- `multi_hop_hit_rate` — expected source retrieved **and** `graph_hop_distance >= 1`
- `p50_latency_ms`, `p95_latency_ms`

Entities and relations are extracted heuristically (capitalized terms; regex patterns for the four relation kinds), so quality is demo-grade — deliberately replaceable with proper NER/LLM extraction.

---

## 10. Security posture

- **Threat model insight:** the highest-risk input is retrieved content, not the user question. Injected instructions in a document are scanned at ingest, quarantined on high risk, down-weighted or excluded at retrieval, fenced in the prompt, and the generated answer is re-scanned.
- **Destructive actions:** `/v1/admin/purge` requires an admin key **and** a separate short-lived single-use token; splitting issuance from execution prevents an injected instruction from self-approving.
- **Secrets:** configuration is environment-driven. **Your local `.env` contains live-looking OpenAI and Qdrant credentials** — do not share it, and rotate them if they were ever exposed. `.env.example` is the safe template with empty keys.
- **Not included (documented as production work):** TLS/mTLS, real identity provider, tenant isolation, rate limiting, durable audit logs, trained injection classifier, least-privilege DB roles. See `docs/production-hardening.md`.

---

## 11. Known caveats and troubleshooting

| Issue | Detail / remedy |
|---|---|
| Port 8000 / 8501 already used | The start script validates that port 8000 is *this* API (via `/health` shape) and that 8501 is *this* Streamlit app (via process command line); otherwise it automatically picks the next free port and passes it to the UI. You can also force `-ApiPort` / `-StreamlitPort`. |
| Docker daemon down | The script auto-starts Docker Desktop (Windows) and waits. If unavailable, the API runs with in-memory stores; check `/health` for `backend: memory`. |
| Graph backend shows `memory` | Neo4j was not fully ready when the API imported `app.main`. The script now waits for the container healthcheck before starting uvicorn; if it still happens after a manual start, restart the API once Neo4j is healthy. |
| Full Docker stack uses in-memory stores | `infra/docker-compose.yml`'s API container inherits `QDRANT_URL=http://localhost:6333` / `NEO4J_URI=bolt://localhost:7687` from `.env`; inside a container `localhost` is the container itself. Use `http://qdrant:6333` and `bolt://neo4j:7687` for containerized DB access, or use `start-all.ps1` (host API + containerized DBs). |
| Data seems missing after restart | `stop-all.ps1` preserves volumes by default; `-RemoveVolumes` deletes them. Sample ingestion is idempotent and is re-run by `start-all.ps1`. |
| `make clean` on Windows | Uses POSIX `find`; delete `__pycache__` / `.pytest_cache` manually if needed. |
| Version labels | `pyproject.toml` and `rhea/__init__.py` say `0.1.0`; FastAPI app declares `0.2.0`. Cosmetic only. |
| Benign startup warnings | `pytest` shows "Api key is used with an insecure connection" (the `.env` Qdrant key is sent to the local HTTP Qdrant, which ignores it) and a qdrant-client/server minor-version mismatch warning (client 1.20 vs server 1.15.4). Both are non-fatal; all 39 tests pass. |
| Answers feel extractive / not synthesized | Expected with `LLM_PROVIDER=local`. Set `LLM_PROVIDER=openai` or `anthropic` with a valid key in `.env` and restart for natural, reasoned answers; citations and prompt fencing are identical. |
| Logs / PID | `.run\api.log`, `.run\api.err.log`, `.run\api.pid`, `.run\streamlit.log`, `.run\streamlit.err.log`, `.run\streamlit.pid` — check these if something fails to start. |

---

## 12. Quick reference card

```powershell
# START (Docker Desktop if needed, Neo4j, Qdrant, FastAPI, sample data, Streamlit)
powershell -ExecutionPolicy Bypass -File .\start-all.ps1

# STOP (API + Streamlit processes + Compose containers; data volumes kept)
powershell -ExecutionPolicy Bypass -File .\stop-all.ps1

# URLs:  Streamlit http://127.0.0.1:8501  (or the printed port)
#        API http://127.0.0.1:8000 (or auto-selected port)  |  Docs /docs  |  Health /health
#        Neo4j http://localhost:7474  |  Qdrant http://localhost:6333/dashboard
# Keys:  reader=demo-reader-key  writer=demo-writer-key  admin=demo-admin-key
# Chat:  POST /v1/chat/stream (SSE)  |  PDF: POST /v1/ingest/pdf  |  Clear: POST /v1/chat/clear
```
