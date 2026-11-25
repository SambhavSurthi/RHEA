# Plan: RHEA-001 — Production RAG rebuild (root-cause programme)

- **Issue:** `docs/issues/RHEA-001-irrelevant-retrieval-and-weak-grounding.md`
- **Author (handle/tool/model):** `rhea / opencode / hy4-flash-free`
- **Date:** 2026-11-26
- **Status:** <!-- draft | approved | implementing | done | superseded --> **draft — awaiting owner approval**

## Goal / Non-goals

**Goal:** turn the current harness into a reliable, measurable document-intelligence platform where evidence survives from PDF → canonical chunk → all indexes → retrieval → context → answer → citation. Fix the root causes catalogued in `docs/architecture-audit.md`.

**Non-goals:** rewriting the whole project from scratch; replacing FastAPI/Streamlit/LangGraph without reason; adding every service in the brief blindly; claiming production readiness without executed tests; prompt-only fixes; adding model weights to Git.

## Background (Architecture refs)

- `docs/architecture-audit.md` — verified root causes P-01…P-22 and live probe evidence.
- `AGENTS.md` §3 invariants — grounded citations, hybrid retrieval, untrusted content, bounded memory, Git workflow, living documentation.
- `AGENTRULES.md` §4 — verification matrix; §8 — codebase-memory-first rule; §9 — incident rule.

Execution order follows the owner's stated priority (canonical → parsing → chunking → citations/metadata → retrieval → graph → fusion/rerank → generation → guardrails → model services → evaluation), not the order services happen to be listed in the brief.

## Phase contract

**Every phase must end with an executed test, not a claim.** For each phase:

1. Implement only that phase's deliverables.
2. Update every affected doc/rule/map in the same change set (`AGENTS.md` §11).
3. Re-index codebase memory and record calls in the session log.
4. Run the **Exit test** below. If it fails, fix within the phase — do not proceed.
5. Report modified files, decisions, failures honestly and remaining issues.

---

## Phase 1 — Canonical document/chunk architecture

**Intent:** establish one authoritative source for document content, versions, chunk identity and metadata so all indexes refer to the same IDs.

**Deliverables:** PostgreSQL service + schema (`documents`, `document_versions`, `chunks`, `chunk_elements`, `ingestion_jobs`, `index_sync_state`, `citation_records`); object-store abstraction with local filesystem dev adapter; canonical `document_id`/`version_id`/`chunk_id` typed models; deterministic ID derivation; migration tool.

**Dependencies:** none. **Exit test:** ingest the same PDF twice → one new version only on content change, identical deterministic chunk IDs, original PDF retrievable from object storage, chunk rows resolve in Postgres; `docker compose config` valid. **Evidence:** SQL assertions + ID equality report.

## Phase 2 — Docling parsing and OCR

**Intent:** preserve document structure instead of flattening text.

**Deliverables:** Docling parser behind `DocumentParser` interface; configurable OCR engine with availability detection; parsing warnings/confidence; scanned-page detection; structured element output with page numbers.

**Dependencies:** Phase 1. **Exit test:** fixture set (digital, scanned, table, figure, formula, empty/corrupt) produces typed elements with correct pages and captions; OCR status recorded; scanned fixture is not empty. **Evidence:** fixture-to-JSON snapshots.

## Phase 3 — Structured document representation

**Intent:** normalize parser output into the element model with stable element IDs and reading order.

**Deliverables:** `NormalizedElement` schema (`document_id`, `version`, `element_id`, `type`, `content`, `page_start/end`, `section`, `subsection`, `parent_element_id`, `reading_order`, `source_location`, `extraction_metadata`, `warnings`); heading/section hierarchy reconstruction.

**Dependencies:** Phase 2. **Exit test:** a paragraph after a heading inherits that section; table caption stays attached to its table; parent/child IDs resolve; reading order matches fixture order. **Evidence:** normalized JSON fixture assertions.

## Phase 4 — Structural chunking

**Intent:** replace 700-char uuid chunks with token-aware hierarchical chunks.

**Deliverables:** `Chunker` interface; parent/child chunks; configurable size/overlap; no table/formula splits; chunk validation (empty, duplicate, missing metadata, invalid page, broken parent, oversized, bad element refs).

**Dependencies:** Phases 1–3. **Exit test:** chunk unit suite passes; no orphan sentences; tables intact; token bounds respected; `previous_chunk_id`/`next_chain` chain valid; stable IDs after re-run. **Evidence:** chunk validation report.

## Phase 5 — Correct source metadata and citations (foundation)

**Intent:** make citations resolvable before any generation work.

**Deliverables:** `EvidenceRef` type with backend-generated `evidence_id`, `chunk_id`, `document_id`, `version`, `page_start/end`, filename, section; citation metadata persisted in canonical store; single `source_label` helper used by backend and UI; remove the three duplicate label implementations.

**Dependencies:** Phases 1–4. **Exit test:** every retrieval candidate carries a resolvable evidence ID; label helper returns identical output in backend and UI; no `page=None` for PDF chunks. **Evidence:** resolver test for IDs → canonical record.

## Phase 6 — Qdrant retrieval (with model-backed embeddings)

**Intent:** make dense retrieval actually semantic and consistent with canonical chunks.

**Deliverables:** Dockerized embedding service (TEI/Infinity), configurable model/dimension/endpoint, batch embedding + retry + cache, collection versioning, payload indexes, upsert/delete/replace by stable chunk ID, stale-vector cleanup, health gate at startup.

**Dependencies:** Phases 1–5. **Exit test:** same query returns the labelled relevant chunk in top 5 for the semantic subset; re-ingest does not duplicate points; embedding dimension mismatch fails loudly. **Evidence:** Recall@K/nDCG baseline vs current.

## Phase 7 — OpenSearch BM25

**Intent:** recover exact terminology, acronyms, numbers, titles and formulas.

**Deliverables:** OpenSearch service, index mapping, bulk indexing, query/filter API, delete/replace, health check; same `chunk_id` as Qdrant; explicit degraded-mode flag (never silent).

**Dependencies:** Phases 1–5. **Exit test:** exact-keyword and numerical probes from `docs/architecture-audit.md` §3 retrieve the correct `reliability.md` chunk in top 3; service-down response reports `lexical_degraded=true`. **Evidence:** keyword benchmark results.

## Phase 8 — Neo4j graph retrieval

**Intent:** make graph evidence real, bounded and citable.

**Deliverables:** graph schema (Document/Section/Chunk/Entity/Author/Method/Dataset/Model/Institution), uniqueness constraints + indexes, evidence-bearing relationships with `source_chunk_id`/version/confidence/extraction_method/timestamp, relationship allowlist, bounded traversal, evidence chunk returned (never whole page).

**Dependencies:** Phases 1–5. **Exit test:** multi-hop probe returns Datadog as the answer-bearing evidence with `graph_hop_distance=3`; every edge resolves to a source chunk; no unsupported relationship type created. **Evidence:** graph assertions + probe transcript.

## Phase 9 — Hybrid retrieval (RRF) and reranking

**Intent:** combine three retrieval systems without comparing incompatible scores, then order by real relevance.

**Deliverables:** `HybridRetriever` rewritten to accept dense/BM25/graph candidates with provenance fields; RRF over ranks; configurable `vector_top_k`, `bm25_top_k`, `graph_top_k`, `rrf_k`, `candidate_count`; dedupe by `chunk_id`; document/version/permission filters; Dockerized cross-encoder reranker with recorded scores and explicit failure state.

**Dependencies:** Phases 6–8. **Exit test:** all three ranks present in candidate provenance; rerank ablation shows nDCG@10 improvement; reranker-down is reported, not silently skipped. **Evidence:** before/after ranking table.

## Phase 10 — Query understanding and context assembly

**Intent:** retrieve for the actual question and build a minimal, sufficient context.

**Deliverables:** query classification/rewrite/decomposition with original preserved; entity + keyword extraction; conditional graph use; `ContextAssembler` with dedupe, parent expansion, token budget, evidence metadata preservation.

**Dependencies:** Phase 9. **Exit test:** multi-part question issues N retrieval calls; follow-up does not pollute retrieval query with conversation text; assembled context respects token budget and contains the labelled evidence chunk. **Evidence:** query trace + context dump (redacted).

## Phase 11 — Grounded generation and citation validation

**Intent:** never fabricate an answer or a citation.

**Deliverables:** Dockerized local LLM service (Ollama/vLLM) behind configurable provider; structured output where supported; abstention contract; backend-issued evidence IDs in prompt; citation extraction → validity check → canonical resolution → page/filename check → **separate** entailment check; retry with corrected evidence; safe fallback; remove extractive default from production path.

**Dependencies:** Phase 10. **Exit test:** probes from audit §3 produce correct answer or explicit insufficiency; invalid citation ID rejected; wrong-version citation rejected; unsupported claim flagged; correct page rendered. **Evidence:** generation suite + citation validation matrix.

## Phase 12 — NeMo Guardrails, security, ingestion workers, evaluation and observability

**Intent:** defence-in-depth, recoverable ingestion, measurable operation.

**Deliverables:** NeMo Guardrails service (input/output/retrieved-content scanning, jailbreak detection, allowlisted tools); application-level ACLs and document filters; durable approval store + audit log + real approval channel; background ingestion worker with job IDs/status/retries/outbox recovery; Prometheus + OTel with query_id, stage timings, chunk IDs, scores, model version, token usage; benchmark suite (factual, keyword, numerical, table, figure, formula, multi-hop, comparative, unanswerable, multi-chunk) with Recall@K, Precision@K, MRR, nDCG, relevance, faithfulness, citation precision/recall and per-stage latency; full Docker Compose with justified services, pinned images, health checks, volumes, CPU/GPU profiles and hardware documentation.

**Dependencies:** Phases 1–11. **Exit test:** injection corpus yields zero bypass; guardrail-down reported; kill-after-Qdrant-write ingestion recovers; full Compose boots with all health checks; evaluation reproducible with recorded thresholds; no secret in logs/diffs. **Evidence:** red-team report, recovery test, compose health table, benchmark JSON.

## Phase 13 — End-to-end verification and acceptance

**Intent:** prove the 22 acceptance criteria from the brief, not just that services start.

**Exit test:** run the full acceptance checklist in `docs/audits/` (to be created in Phase 13) with executed evidence for every item. Any untested criterion remains **not claimed**.

## Alternatives considered

| Option | Pros | Cons | Why not |
|---|---|---|---|
| Prompt-only fix / swap LLM | Fast | Cannot fix retrieval, parsing, IDs or citations | Root causes are architectural (audit P-01…P-10) |
| Add OpenSearch first | Fixes exact terms | No canonical IDs to share; same chunk mismatch | Must establish IDs first (owner priority) |
| Keep `HashingEmbedder` for production | No infra | Not semantic; collision-prone; no model version | Fails relevance and reproducibility |
| Neo4j as content store | One DB | Cannot preserve chunk identity, tables, versions; duplicates Qdrant | Violates canonical architecture requirement |
| Add all 14 Compose services immediately | Matches target list | Unjustified complexity, high RAM, slower diagnosis | Brief says add only services with clear benefit |

## Safety / Policy impact

- Retrieval must respect document ACLs; no cross-document leakage.
- Graph relationships require evidence and confidence; no invented edges.
- Citation IDs are backend-generated; LLM never supplies page/filename/chunk ID.
- Untrusted PDF text cannot trigger tools or override instructions.
- Destructive purge acts on canonical store + all indexes, with durable approval.
- No hardcoded credentials; no model weights in Git; no unverified production claims.

## Migration / Rollout

1. Introduce canonical schema alongside current stores; dual-read for one release window.
2. Backfill deterministic chunk IDs and embed with a versioned collection.
3. Switch retrieval to hybrid only after Phase 9 exit test passes.
4. Switch generation/citations only after Phase 11 exit test passes.
5. Keep in-memory fallback for tests, but make degradation explicit in `/health`.

## Tests / Gates

Every phase has its own exit test above. Global gates: `pytest -q`, `ruff check`, `scripts/check.ps1`, codebase-memory re-index, session log, docs propagation (`AGENTS.md` §11). New known failures go to `docs/agent-logs/KNOWN_ISSUES.md`.

## Revision log

- 2026-11-26: initial draft from verified Phase 1 audit; execution order set to owner's priority.
