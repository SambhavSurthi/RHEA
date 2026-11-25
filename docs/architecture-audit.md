# Architecture Audit — RHEA Phase 1

- **Date:** 2026-11-26
- **Status:** Phase 1 complete — audit and plan only, **no code modified**
- **Method:** codebase-memory graph inspection (`index_status`, `get_architecture`, `search_graph`), direct reading of every listed source/config file, and live probes against the running API on port 8000. Nothing below is assumed from documentation alone.

## 1. Files actually inspected

Codebase memory: 544 nodes / 2090 edges, project `rhea`, branch `main` at `3c9852e`.

Backend: `backend/rhea/main.py`, `api/health.py`, `api/ingest.py`, `api/chat.py`, `core/config.py`, `core/bootstrap.py`, `core/observability.py`, `domain/models.py`, `auth/rbac.py`, `pipelines/pdf.py`, `pipelines/ingestion.py`, `pipelines/retrieval.py`, `pipelines/evaluation.py`, `pipelines/runner.py`, `services/embeddings.py`, `services/llm.py`, `services/security.py`, `services/agent.py`, `services/chat.py`, `stores/vector.py`, `stores/graph.py`.

Frontend/infra/config: `frontend/streamlit_app.py`, `infra/docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `pyproject.toml`, `.env.example`, `backend/data/eval.json`, `start-all.ps1`, `stop-all.ps1`, `Makefile`, `tests/` (file list + codebase-memory test graph), `docs/PROJECT_REPORT.md`, `docs/STRUCTURE.md`.

**Not read:** `.env` (prohibited by `AGENTRULES.md` §1.6). Only the safe `.env.example` template was read.

## 2. Existing architecture and data flow

```text
Streamlit (:8501)
  ├─ POST /v1/ingest/pdf (multipart) → FastAPI
  └─ POST /v1/chat/stream (SSE)      → FastAPI

FastAPI app factory → Services (bootstrap)
  IngestionService → scan_text/classify_trust → regex entity + relation extraction
                   → chunk_text(uuid4 ids) → HashingEmbedder → Qdrant upsert
                   → Neo4j Document MERGE + Entity MERGE + RELATED MERGE
  HybridRetriever → HashingEmbedder(question) → Qdrant top 8
                  → regex entities → Neo4j BFS (≤3 hops) top 8
                  → dedupe by hash(source+text) → RRF(k=60) + 0.15*token overlap
                  → × trust weight → sort → top_k
  RAGAgent / ConversationalRAG → build_prompt([1..n] sources) → LLM provider
                               → validate_output → answer + numbered citations
```

There is **no canonical relational store**, **no BM25 service**, **no reranker service**, **no model service**, **no ingestion worker**, **no object store**, **no per-stage tracing** and **no citation validation**.

## 3. Live evidence (actual API responses)

Probe 1 — multi-hop question *"Which tool monitors the infrastructure that powers the Embedding Cache?"*

- Expected answer: **Datadog** monitors the Cloud Provider reached via Embedding Cache → Redis Cluster → Cloud Provider (3 hops).
- Actual answer: *"The Embedding Cache depends on the Redis Cluster [1]. The GPU Cluster runs on Kubernetes [2]. The Retrieval Service depends on Neo4j [3]."*
- The graph result with `graph_hop_distance=3` was ranked 4th, marked `retrieval=graph`, `trust=unverified`, `metadata={}`, and its `text` was the **entire page**, not the evidence sentence.

Probe 2 — exact factual question *"What is the exact p95 latency target mentioned in the reliability notes?"*

- Actual answer: *"The Cloud Provider is monitored by Datadog [1]. The GPU Cluster runs on Kubernetes [2]. The API Gateway depends on Identity Provider [3]."*
- `reliability.md` was not retrieved at all. No abstention despite no supporting evidence.

Probe 3 — unanswerable question *"Who is the author of the Attention Is All You Need paper and what dataset was used?"*

- Actual answer: *"The GPU Cluster runs on Kubernetes [1]..."* — confident, irrelevant, with three fabricated `[n]` markers.
- Entities mis-extracted as `['Attention Is All You', 'Need']`.

Evaluation endpoint returned `retrieval_hit_rate: 100`, `multi_hop_hit_rate: 100`, but `answer_keyword_coverage: 25` — the metrics reward finding a source filename, not answering correctly. This is a measurement defect, not a quality signal.

## 4. Root-cause catalogue

| ID | Problem | Root cause (verified) | Relevant files | Impact | Proposed solution | Verification method |
|---|---|---|---|---|---|---|
| P-01 | Irrelevant vector retrieval | `HashingEmbedder` is a blake2b token-bucket hash, not a semantic model; collisions and no word sense. Production retrieval therefore ranks by accidental token overlap. | `services/embeddings.py`, `core/bootstrap.py` | Root cause of wrong chunks in every query. | Dedicated embedding service with a real model; configurable dimension/model identity; collection versioning. | Retrieval benchmark Recall@K/nDCG on labelled questions before/after; dimension and model-version assertions. |
| P-02 | No lexical retrieval | Only vector + graph are queried. No BM25 anywhere in code or Compose. Exact terms, acronyms, numbers and titles cannot be matched reliably. | `pipelines/retrieval.py`, `infra/docker-compose.yml` | Probe 2 misses `reliability.md` entirely. | Add OpenSearch BM25 service with same stable `chunk_id`; degrade explicitly when down. | Exact-keyword and numerical question suite; assert BM25 rank recorded in provenance. |
| P-03 | Multi-hop graph evidence not load-bearing | Graph hits are whole `Document.text` pages; dedup key is `hash(source+text)`, not a chunk ID; graph hit ranked 4th and labelled unverified with empty metadata. | `stores/graph.py`, `pipelines/retrieval.py` | Probe 1 answers the first hop only; correct path is present but unusable. | Graph nodes for Section/Chunk, relationships with evidence chunk IDs and confidence; bounded traversal; evidence-bearing results. | Multi-hop eval requiring both correct chunk and `graph_hop_distance >= 1`; assert cited chunk contains the fact. |
| P-04 | No canonical document/chunk store | Qdrant payload and Neo4j `Document.text` are independent copies; PostgreSQL/MinIO/Redis absent. No document_id/version/chunk_id contract. | `core/bootstrap.py`, `pipelines/ingestion.py`, `stores/*` | No single source of truth; impossible to reconcile or cite reliably. | PostgreSQL canonical tables + object storage for original PDFs; stable IDs shared by all indexes. | Schema assertions: same chunk_id resolves in Postgres, Qdrant, OpenSearch, Neo4j. |
| P-05 | Unstable chunk IDs | `chunk_text()` uses `uuid.uuid4()` per ingest. Re-ingest creates new IDs; old Qdrant points are never deleted. | `pipelines/ingestion.py:39-57`, `stores/vector.py:69-82` | Duplicate/stale vectors, broken citations after re-upload, no idempotency. | Deterministic IDs from `(document_id, version, element_id, ordinal)`; replacement/deletion logic. | Ingest same file twice → point count unchanged, IDs identical, old version filtered. |
| P-06 | PDF parsing destroys structure | `pypdf.extract_text()` only; no Docling, no OCR, no layout/table/figure/heading model; scanned page yields empty text and is silently skipped. | `pipelines/pdf.py:24-32`, `api/ingest.py:43-70` | Sections, tables, formulas, captions, reading order and page confidence lost. | Docling structured parsing + configurable OCR; normalized element model with warnings/confidence. | Fixture PDFs (digital, scanned, table, figure, formula) assert element types, captions and page numbers. |
| P-07 | Character-count chunking | `chunk_text()` splits on blank lines and hard 700-char slices; no tokens, sections, parent/child, overlap or validation. | `pipelines/ingestion.py:39-57` | Splits tables/formulas, isolates sentences, loses section context. | Hierarchical structural chunker with token-aware sizing, parent/child, validation. | Chunk unit tests: no orphan sentences, tables intact, section metadata present, token bounds. |
| P-08 | Fabricated/incorrect citations | LLM is told to cite `[1]..[n]` by **position in the final list**; no evidence IDs, no validation, no entailment check. Probes 2–3 show citations to unrelated chunks. | `services/llm.py:48-103`, `services/chat.py:127-152`, `frontend/streamlit_app.py:77-95` | Citations are decoration, not evidence. | Backend-issued evidence IDs; extract & validate citation IDs; resolve chunk→document→page; separate validity from entailment; safe fallback. | Citation tests: invalid ID rejected, wrong-version rejected, unsupported claim flagged, correct page rendered. |
| P-09 | Page metadata unreliable | PDF page encoded as `source="file.pdf#pN"` string and `metadata['page']` string; `.md` sources have no page; graph hits lose metadata entirely. | `pipelines/pdf.py:35-60`, `pipelines/retrieval.py:93-105` | Page references can be wrong or absent. | Canonical `page_start/page_end` integers on chunk and element records; propagated to every result. | Assert page int on every chunk and citation; PDF fixture with known page locations. |
| P-10 | Weak graph schema/extraction | Only 4 regex relations; entities are capitalized sequences with an 8-word stoplist; no CITES/AUTHORED_BY/USES/EVALUATED_ON, no evidence, confidence, version or constraints for chunk nodes. | `pipelines/ingestion.py:12-89`, `stores/graph.py:196-237` | Incomplete/incorrect relationships; cannot support research questions about authors/methods/datasets. | Configurable structured extractor with schema validation, evidence chunk, confidence; explicit relationship allowlist. | Extraction tests: malformed rejected, every edge has evidence chunk + version, no edge without source text. |
| P-11 | No query understanding | Raw question is embedded; chat `_prepare` appends recent turns/summary to the retrieval string, which contaminates retrieval. | `services/chat.py:90-105`, `pipelines/retrieval.py:64-67` | Follow-up queries retrieve on conversation text, not the question; multi-part questions get one query. | Classify/rewrite/decompose with original preserved; entity + keyword extraction; conditional graph use. | Query tests: rewritten queries logged, multi-part produces N retrieval calls, original intent preserved. |
| P-12 | No reranking | No cross-encoder or rerank service; `"reranking"` is a 0.15 token-overlap bonus. | `pipelines/retrieval.py:35-40,112` | Fused candidates are not relevance-ordered; top_k truncation discards the right chunk. | Dockerized reranker service with measured before/after ranking. | Rerank ablation: nDCG@10 improves; service-down path explicitly flagged. |
| P-13 | No context assembly module | Retriever returns top_k `SourceResult`s directly to the prompt; no dedupe beyond `stable_key`, no parent expansion, no token budget. | `services/agent.py:34-43`, `services/chat.py:107-125`, `services/llm.py:54-68` | Irrelevant passages consume context; supporting parent section never added. | Dedicated assembler: select, dedupe, expand parent, budget tokens, preserve citation metadata. | Context tests: token budget respected, parent expansion present, irrelevant chunk removed. |
| P-14 | Unreliable generation | Default `LLM_PROVIDER=local` is extractive; no hosted/local model service; no abstention contract; prompt is the only guardrail. | `core/config.py:10`, `services/llm.py:116-178`, `core/bootstrap.py:57-63` | Confident but wrong answers (all probes); keyword coverage 25%. | Dockerized LLM provider (Ollama/vLLM) with structured output, controlled fallback and explicit insufficiency response. | Generation suite: answer relevance/faithfulness; unanswerable question abstains; no fabricated facts. |
| P-15 | Security layer is heuristic-only | 11 regexes + output regex; no NeMo Guardrails, no tool allowlisting, no rate limits, no tenant filters, no audit log. | `services/security.py`, `auth/rbac.py` | Prompt injection bypassable; no defence-in-depth. | NeMo Guardrails service + application validation; untrusted-content tagging; allowlisted tools; audit events. | Injection corpus: zero bypass; guardrail-down reported, not silently skipped. |
| P-16 | No document-level access control | `/v1/query` and `/v1/chat` accept no document filter or permission context; all indexed documents are searchable by any reader. `thread_id` is caller-controlled for `/v1/chat/clear`. | `api/query.py`, `api/chat.py`, `domain/models.py` | Reader can search documents they should not see; can clear another thread by guessing ID. | Document ACLs in canonical store; filters enforced in every retriever; server-issued thread tokens. | Auth tests: reader cannot retrieve forbidden document; cross-thread clear denied. |
| P-17 | Approval gate is ineffective | `/v1/admin/purge` clears only in-memory stores; it does not purge Qdrant or Neo4j. Tokens are issued by any admin key, in-memory. | `api/admin.py`, `auth/rbac.py:75-128` | Destructive endpoint is misleading; no real human approval or durable audit. | Durable approval store + real channel; purge operates on canonical store and all indexes with recovery. | Purge test: all stores cleared; token single-use; audit entry written. |
| P-18 | Ingestion is synchronous and non-recoverable | Upload does parse→chunk→embed→Qdrant→Neo4j inline; no job ID, status, retries, outbox or partial-failure recovery. | `api/ingest.py:43-70`, `pipelines/ingestion.py:105-149` | Failed halfway leaves Qdrant/Neo4j inconsistent; large PDFs block request. | Background worker + job table + transactional outbox; per-index status; recovery job. | Failure injection: kill after Qdrant write → recovery completes; no orphan vectors. |
| P-19 | Evaluation measures the wrong thing | 6 synthetic cases; hit-rate by **filename** only; groundedness = token overlap; no Recall@K/MRR/nDCG, citation metrics, unanswerable/table/figure/formula cases. | `pipelines/evaluation.py`, `backend/data/eval.json` | 100% hit rate coexists with wrong answers (live evidence). | Layered benchmark + real retrieval/generation/citation metrics; per-stage latency; reproducible runs. | Baseline benchmark recorded; thresholds gate changes; metrics fail on a deliberately wrong answer. |
| P-20 | Observability insufficient | 4 Prometheus metrics with only endpoint/status labels; OTel disabled and console exporter only; no structured logs, query_id, chunk IDs, scores, model version, token usage. | `core/observability.py`, `main.py` | Failures are difficult to debug; no reproducible traces. | Structured JSON logs + OTel exporter + stage metrics with IDs; redact content by default. | Trace test: one query produces query_id, stage timings, chunk IDs, scores, citation status. |
| P-21 | Infrastructure incomplete / version drift | Compose has only Neo4j, Qdrant, API, frontend; no model services or canonical DB. Live warning: qdrant-client 1.20.0 vs server 1.15.4; no lockfile/SBOM. | `infra/docker-compose.yml`, `pyproject.toml`, runtime warning | Not deployable as the target architecture; version incompatibility risk. | Add justified services only, pinned images, health checks, volumes, resource docs, CPU/GPU profiles. | `docker compose config` + full-stack boot + health checks + pinned-version assertions. |
| P-22 | Encoding defects in source/docs | Mojibake (`â€”`) in `services/llm.py:85`, `auth/rbac.py:6`, `pipelines/pdf.py:1` from earlier file rewrites. | those files | Low functional impact but indicates uncontrolled text rewrites; pollutes prompts/logs. | Normalize UTF-8 in a dedicated cleanup change; add a CI encoding check. | Grep for mojibake sequences returns zero. |

## 5. Duplicate implementations / missing abstractions

- **Duplicate agent graphs:** `RAGAgent` (`services/agent.py`) and `ConversationalRAG` (`services/chat.py`) each implement retrieve→generate. Both route to the same retriever and prompt; evaluation only exercises `RAGAgent`, while the UI uses `ConversationalRAG`. This splits behaviour and test coverage.
- **Duplicate citation labels:** `citation_label()` in `pipelines/pdf.py`, `source_label()` in `services/llm.py`, and `source_label()` in `frontend/streamlit_app.py` independently reconstruct a display label from metadata. They can disagree.
- **Missing interfaces:** no `DocumentParser`, `Normalizer`, `Chunker`, `LexicalRetriever`, `Reranker`, `ContextAssembler`, `CitationValidator`, `Guardrail`, `ObjectStore`, `JobQueue` abstractions. The `Embedder`/`VectorStore`/`GraphStore` protocols are the only real seams.
- **Duplicate content storage:** chunk text lives in Qdrant payload and page text in Neo4j; neither is authoritative.

## 6. What works and must be preserved

1. FastAPI application factory with clean router separation and `app.state.services` dependency.
2. RBAC role model (`reader < writer < admin`) and the concept of a separate approval token.
3. LangGraph memory + auto-compaction + SSE step/source/token streaming — good scaffolding for the future agent.
4. Docker Compose with Neo4j healthcheck and container-safe service hostnames.
5. Deterministic in-memory fallbacks that make 42 tests runnable without external services.
6. The existing page-scoping intent in PDF ingestion (correct direction, wrong implementation).

These are interfaces/structures, not the broken retrieval logic; replacing them without a technical reason would violate the brief.

## 7. Audit conclusion

The primary failure chain is:

`HashingEmbedder` (no semantics) + flattened `pypdf` text + 700-char uuid chunks + no BM25 + whole-page graph hits + positional citations + extractive local LLM + filename-only evaluation
→ irrelevant chunks → wrong answers → citations that point at unrelated text.

Fixing prompts or adding libraries alone will not help. The canonical document/chunk layer and stable IDs must come first, followed by parsing/chunking, then retrieval sources, then generation/citations, then guardrails/model services/evaluation.

**Phase 1 exit condition:** this audit and the implementation plan are complete, reviewed and linked from `docs/NAVIGATION.md`. No code has been changed. Next phase is gated on owner approval of the plan.

See `docs/plans/RHEA-001-production-rag-rebuild.md` for the phased build and per-phase exit tests.
