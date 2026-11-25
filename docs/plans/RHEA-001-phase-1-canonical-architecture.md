# Plan: RHEA-001 Phase 1 — Canonical document/chunk architecture

- **Parent plan:** `docs/plans/RHEA-001-production-rag-rebuild.md`
- **Issue:** `docs/issues/RHEA-001-irrelevant-retrieval-and-weak-grounding.md`
- **Author (handle/tool/model):** `rhea / opencode / hy4-flash-free`
- **Date:** 2026-11-26
- **Status:** draft — awaiting owner approval (dependency addition + new infrastructure service)

---

## 1. Intent

Establish **one authoritative source of truth** for document content, document versions, chunk identity and citation metadata before any retrieval or generation changes. Today chunk IDs are `uuid4()` regenerated on every ingest, Qdrant payload and Neo4j `Document.text` are independent copies, and there is no relational record to reconcile them (audit P-04, P-05, P-09, P-18).

After Phase 1, every downstream system — Qdrant, OpenSearch, Neo4j, retrieval results, reranking, context assembly, citations and evaluation — will be able to refer to the **same stable `chunk_id`** and resolve it back to a canonical document version and page range.

**Explicit non-goals for this phase:** no Docling, no OCR, no chunking-algorithm change, no retrieval change, no prompt/LLM change, no UI redesign. Those are later phases. Existing behaviour and the 42 passing tests must remain green.

## 2. Target architecture

```text
                         +---------------------------+
                         |  CANONICAL (PostgreSQL)   |
                         | documents / versions      |
                         | chunks / elements         |
                         | jobs / index_sync / cites |
                         +-------------+-------------+
                                       | stable chunk_id / version_id
          +----------------------------+----------------------------+
          |            |               |               |            |
          v            v               v               v            v
     Object store   Qdrant        OpenSearch       Neo4j        API / UI
     (original PDF) (vectors)     (BM25, later)    (graph)      (citations)
```

The canonical store is the only writer of identity. Indexes are derived projections; their sync state is recorded in PostgreSQL.

## 3. What will be done (work breakdown)

### 3.1 Dependencies and configuration

- Add dependencies (pending approval): `sqlalchemy>=2.0`, `alembic>=1.13`, `psycopg[binary]>=3.1`, and `minio>=7.2` only if the MinIO adapter is enabled in this phase.
- Add settings to `backend/rhea/core/config.py`:
  - `postgres_dsn` (from `RHEA_POSTGRES_DSN`, no default secret)
  - `postgres_pool_size`, `postgres_statement_timeout`
  - `object_store_backend` (`filesystem` | `minio`)
  - `object_store_path` for local dev; MinIO endpoint/bucket vars when applicable
  - `canonical_schema` optional namespace
- Update `.env.example` with **names only, empty values**. Never read or print the real `.env`.

### 3.2 Deterministic identity module

New `backend/rhea/pipelines/identity.py`:

- `document_id = UUID5(namespace, canonical_source_key)` — derived from a normalized source identifier (filename/URI + title), stable across re-uploads of the same logical paper.
- `version_id = SHA256(normalized original bytes)` — changes only when content changes.
- `element_id = UUID5(namespace, f"{document_id}:{version_id}:{parser_element_key}")` — parser-stable where a parser supplies keys; temporary keys allowed until Phase 3, then normalized.
- `chunk_id = UUID5(namespace, f"{document_id}:{version_id}:{element_id}:{ordinal}")`.
- All IDs are strings in API/payloads; no `hash()` and no `uuid4()` in canonical paths.

**Why UUID5/SHA256:** deterministic across restarts and processes, no salted Python `hash()`, and version changes explicitly invalidate old chunk identities instead of silently reusing them.

### 3.3 Relational schema (migration `0001`)

| Table | Key fields | Notes |
|---|---|---|
| `documents` | `document_id UUID PK`, `source_uri TEXT`, `title TEXT`, `created_at`, `updated_at` | One row per logical paper |
| `document_versions` | `version_id TEXT PK`, `document_id FK`, `content_sha256`, `parsed_at`, `parser_name`, `parser_version`, `extraction_status`, `is_current BOOL` | Unique `(document_id, content_sha256)`; only one `is_current` per document |
| `chunks` | `chunk_id UUID PK`, `version_id FK`, `document_id FK`, `ordinal INT`, `chunk_type`, `content TEXT`, `token_count INT`, `page_start INT`, `page_end INT`, `section`, `subsection`, `parent_chunk_id`, `previous_chunk_id`, `next_chunk_id`, `metadata JSONB` | Unique `(version_id, ordinal)`; indexes on `document_id`, `version_id`, `page_start`, `parent_chunk_id` |
| `chunk_elements` | `chunk_id FK`, `element_id TEXT`, `reading_order INT`, `source_location`, `extraction_metadata JSONB`, `extraction_warnings JSONB` | Many-to-many; links canonical chunks to parser elements |
| `ingestion_jobs` | `job_id UUID PK`, `document_id`, `version_id`, `status`, `progress`, `error`, `created_at`, `updated_at` | Job tracking groundwork for Phase 12 worker |
| `index_sync_state` | `version_id FK`, `index_name` (`qdrant`/`opensearch`/`neo4j`), `status`, `last_synced_at`, `failure_reason` | Unique `(version_id, index_name)`; records partial failures |
| `citation_records` | `evidence_id UUID PK`, `chunk_id FK`, `version_id FK`, `document_id FK`, `page_start`, `page_end`, `filename`, `section`, `created_at` | Backend-generated citation metadata; no LLM-supplied fields |

Constraints: foreign keys with `ON DELETE RESTRICT` for canonical records; uniqueness on natural keys; no cascade that can silently delete evidence.

### 3.4 Storage abstractions

New `backend/rhea/stores/relational.py`:

- `CanonicalStore` protocol: `register_document`, `create_version`, `upsert_chunks`, `link_elements`, `get_chunk`, `list_chunks(version_id)`, `mark_index_synced`, `record_evidence`, `get_evidence`, `current_version`.
- `PostgresCanonicalStore` implementation (SQLAlchemy async).
- `InMemoryCanonicalStore` implementation for deterministic tests (no external DB).

New `backend/rhea/services/object_store.py`:

- `ObjectStore` protocol: `put(key, bytes) -> checksum`, `get(key) -> bytes`, `exists(key)`, `delete(key)`.
- `FilesystemObjectStore` for local dev: root from `object_store_path`, key = `{document_id}/{version_id}/original.pdf`.
- Optional `MinIOObjectStore`; selected by config, not hardcoded.

### 3.5 Ingestion integration (minimal, behaviour-preserving)

Refactor `IngestionService.ingest()` so that **before** Qdrant/Neo4j writes it:

1. computes `document_id`/`version_id` from the uploaded bytes and normalized source key;
2. stores the original bytes in the object store (idempotent by key);
3. registers document + version and upserts canonical chunk rows using **the existing `chunk_text` output** with deterministic IDs replacing `uuid4()` at this point only;
4. marks index sync state `pending` for Qdrant and Neo4j.

The current retriever/graph/vector code is otherwise untouched. Existing tests continue to exercise the same in-memory path through `InMemoryCanonicalStore`.

**No dual-write inconsistency:** if canonical persistence fails, nothing is written to Qdrant/Neo4j; if an index write later fails, `index_sync_state` records it explicitly instead of silently degrading.

### 3.6 Infrastructure and tooling

- `infra/docker-compose.yml`: add `postgres` service (pinned image, named volume, healthcheck `pg_isready`, credentials from environment only), wire `api` `depends_on` with health condition. Keep Neo4j/Qdrant unchanged.
- `scripts/migrate.ps1`: runs Alembic upgrade from repo root with `PYTHONPATH=backend`.
- `docs/runbooks/phase-1-canonical-store.md`: startup, migration, verification and rollback procedure (uses existing runbook template).

### 3.7 Tests

New `backend/tests/test_canonical_store.py`:

- deterministic ID equality across two ingests of identical bytes;
- new content → new version, old version chunks unchanged;
- chunk→document→version→page resolution;
- original PDF retrievable from object store with matching checksum;
- duplicate ingest is idempotent (no extra document/version/chunk rows);
- `InMemoryCanonicalStore` passes the same contract tests as the Postgres adapter interface;
- failed version registration leaves no partial chunk rows.

Existing 42 tests must still pass unchanged.

## 4. How it will be executed

1. Owner approves this plan (dependency additions + Postgres service).
2. Add dependencies/config/schema code in small commits; run `ruff` after each.
3. Apply migration locally and in Compose; verify schema with SQL assertions.
4. Wire `IngestionService` to canonical store; keep existing vector/graph calls intact.
5. Add and run tests; fix failures within Phase 1.
6. Update `AGENTS.md` §5 map, `docs/STRUCTURE.md`, `docs/NAVIGATION.md`, `README.md`, `.env.example` documentation in the same change set (`AGENTS.md` §11).
7. Re-index codebase memory; write session log; commit and push.

## 5. Outcomes and exit test

**Phase 1 is complete only when all of the following are executed and recorded:**

| # | Exit check | Command / evidence | Pass condition |
|---|---|---|---|
| 1 | Postgres service healthy | `docker compose -f infra/docker-compose.yml up -d postgres`; `docker compose ps` | `healthy` |
| 2 | Migration applies | `powershell -File .\scripts\migrate.ps1` | `alembic upgrade head` succeeds; tables listed via `\dt` |
| 3 | Deterministic IDs | `pytest -q backend/tests/test_canonical_store.py` | identical bytes → identical `document_id`, `version_id`, `chunk_id` |
| 4 | Versioning | same test suite | changed bytes → new `version_id`; old version chunks still resolvable |
| 5 | Object preservation | same test suite | original PDF bytes retrievable; SHA256 equals ingested checksum |
| 6 | Canonical resolution | SQL + API test | each chunk resolves to document, version, page_start/end, filename |
| 7 | Idempotency | double-ingest test | no duplicate rows; no new Qdrant points from second ingest |
| 8 | No regressions | `pytest -q` + `ruff check ...` | 42 existing tests still pass, lint clean |
| 9 | Docs/memory | `AGENTS.md` §11 propagation + `index_repository` | maps updated; memory re-indexed; session log written |

**Evidence artifacts to store with the phase:** migration output, `\dt` table list, ID equality report, object-store checksum comparison, test output, session log path.

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Postgres adds RAM/startup cost | Pinned lightweight image; healthcheck; no other new service until justified |
| Dependency approval not given | Plan stays draft; no code or Compose changes made |
| Dual-write transition inconsistency | Canonical write happens first; index sync states recorded; vector/graph code unchanged |
| Deterministic IDs change existing Qdrant points | Phase 1 uses a **new versioned collection**; old data untouched; dual-read not switched until Phase 6 |
| Migration errors on existing DB | Migration is additive only; rollback = `alembic downgrade base` + volume preserved |

## 7. Rollback

Revert the Phase 1 commits, remove the `postgres` service from Compose, and leave the Qdrant/Neo4j volumes untouched. No existing data is deleted during Phase 1; canonical rows are additive. If a versioned Qdrant collection is introduced, it is created alongside the old collection and not promoted until Phase 6.

## 8. Revision log

- 2026-11-26: initial detailed Phase 1 plan derived from verified audit P-04/P-05/P-09/P-18.
