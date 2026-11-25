"""Canonical document/chunk storage (PostgreSQL + in-memory test adapter).

This is the authoritative store for document identity and chunk metadata.
Derived indexes (Qdrant, OpenSearch, Neo4j) must use the IDs issued here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    select,
)
from sqlalchemy.engine import Engine

from rhea.domain.canonical import (
    CanonicalChunk,
    CanonicalDocument,
    ChunkElementLink,
    CitationRecord,
    DocumentVersion,
    IndexSyncState,
    IngestionJob,
)

metadata = MetaData()

documents = Table(
    "documents",
    metadata,
    Column("document_id", String(36), primary_key=True),
    Column("source_uri", Text, nullable=False),
    Column("title", Text, nullable=False, default=""),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

document_versions = Table(
    "document_versions",
    metadata,
    Column("version_id", String(64), primary_key=True),
    Column("document_id", String(36), ForeignKey("documents.document_id"), nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("parser_name", Text, nullable=False, default="unknown"),
    Column("parser_version", Text, nullable=False, default="unknown"),
    Column("extraction_status", Text, nullable=False, default="pending"),
    Column("is_current", Boolean, nullable=False, default=True),
    Column("parsed_at", DateTime, nullable=False),
    UniqueConstraint("document_id", "content_sha256", name="uq_document_content"),
)

chunks = Table(
    "chunks",
    metadata,
    Column("chunk_id", String(36), primary_key=True),
    Column("version_id", String(64), ForeignKey("document_versions.version_id"), nullable=False),
    Column("document_id", String(36), ForeignKey("documents.document_id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("chunk_type", Text, nullable=False, default="paragraph"),
    Column("content", Text, nullable=False),
    Column("token_count", Integer, nullable=False, default=0),
    Column("page_start", Integer),
    Column("page_end", Integer),
    Column("section", Text),
    Column("subsection", Text),
    Column("parent_chunk_id", String(36)),
    Column("previous_chunk_id", String(36)),
    Column("next_chunk_id", String(36)),
    Column("metadata", JSON, nullable=False, default=dict),
    UniqueConstraint("version_id", "ordinal", name="uq_version_ordinal"),
)

chunk_elements = Table(
    "chunk_elements",
    metadata,
    Column("chunk_id", String(36), ForeignKey("chunks.chunk_id"), primary_key=True),
    Column("element_id", String(36), primary_key=True),
    Column("reading_order", Integer, nullable=False, default=0),
    Column("source_location", Text, nullable=False, default=""),
    Column("extraction_metadata", JSON, nullable=False, default=dict),
    Column("extraction_warnings", JSON, nullable=False, default=list),
)

ingestion_jobs = Table(
    "ingestion_jobs",
    metadata,
    Column("job_id", String(36), primary_key=True),
    Column("document_id", String(36), ForeignKey("documents.document_id"), nullable=False),
    Column("version_id", String(64), ForeignKey("document_versions.version_id"), nullable=False),
    Column("status", Text, nullable=False, default="pending"),
    Column("progress", Integer, nullable=False, default=0),
    Column("error", Text),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

index_sync_state = Table(
    "index_sync_state",
    metadata,
    Column("version_id", String(64), ForeignKey("document_versions.version_id"), primary_key=True),
    Column("index_name", String(32), primary_key=True),
    Column("scope", Text, primary_key=True, default=""),
    Column("status", Text, nullable=False, default="pending"),
    Column("last_synced_at", DateTime),
    Column("failure_reason", Text),
)

citation_records = Table(
    "citation_records",
    metadata,
    Column("evidence_id", String(36), primary_key=True),
    Column("chunk_id", String(36), ForeignKey("chunks.chunk_id"), nullable=False),
    Column("version_id", String(64), ForeignKey("document_versions.version_id"), nullable=False),
    Column("document_id", String(36), ForeignKey("documents.document_id"), nullable=False),
    Column("page_start", Integer),
    Column("page_end", Integer),
    Column("filename", Text, nullable=False),
    Column("section", Text),
    Column("created_at", DateTime, nullable=False),
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class CanonicalStore(Protocol):
    backend_name: str

    def register_document(self, document: CanonicalDocument) -> None: ...
    def create_version(self, version: DocumentVersion) -> bool: ...
    def current_version(self, document_id: str) -> str | None: ...
    def upsert_chunks(self, records: list[CanonicalChunk]) -> None: ...
    def link_elements(self, links: list[ChunkElementLink]) -> None: ...
    def get_chunk(self, chunk_id: str) -> CanonicalChunk | None: ...
    def list_chunks(self, version_id: str) -> list[CanonicalChunk]: ...
    def mark_index_synced(
        self,
        version_id: str,
        index_name: str,
        status: str,
        failure_reason: str | None = None,
        scope: str = "",
    ) -> None: ...
    def record_evidence(self, evidence: CitationRecord) -> None: ...
    def get_evidence(self, evidence_id: str) -> CitationRecord | None: ...
    def create_job(self, job: IngestionJob) -> None: ...
    def update_job(
        self, job_id: str, status: str, progress: int, error: str | None = None
    ) -> None: ...
    def health(self) -> bool: ...


class InMemoryCanonicalStore:
    """Deterministic adapter for tests and offline development."""

    backend_name = "memory"

    def __init__(self) -> None:
        self.documents: dict[str, CanonicalDocument] = {}
        self.versions: dict[str, DocumentVersion] = {}
        self.chunks: dict[str, CanonicalChunk] = {}
        self.links: dict[str, list[ChunkElementLink]] = {}
        self.sync: dict[tuple[str, str, str], IndexSyncState] = {}
        self.evidence: dict[str, CitationRecord] = {}
        self.jobs: dict[str, IngestionJob] = {}

    def register_document(self, document: CanonicalDocument) -> None:
        existing = self.documents.get(document.document_id)
        now = _now()
        if existing:
            self.documents[document.document_id] = existing.model_copy(
                update={"updated_at": now}
            )
        else:
            self.documents[document.document_id] = document.model_copy(
                update={"created_at": now, "updated_at": now}
            )

    def create_version(self, version: DocumentVersion) -> bool:
        for existing in self.versions.values():
            if (
                existing.document_id == version.document_id
                and existing.content_sha256 == version.content_sha256
            ):
                return False
            if existing.document_id == version.document_id and existing.is_current:
                self.versions[existing.version_id] = existing.model_copy(
                    update={"is_current": False}
                )
        self.versions[version.version_id] = version.model_copy(
            update={"parsed_at": _now(), "is_current": True}
        )
        return True

    def current_version(self, document_id: str) -> str | None:
        for version in self.versions.values():
            if version.document_id == document_id and version.is_current:
                return version.version_id
        return None

    def upsert_chunks(self, records: list[CanonicalChunk]) -> None:
        for record in records:
            self.chunks[record.chunk_id] = record.model_copy(deep=True)

    def link_elements(self, links: list[ChunkElementLink]) -> None:
        for link in links:
            bucket = self.links.setdefault(link.chunk_id, [])
            if not any(existing.element_id == link.element_id for existing in bucket):
                bucket.append(link.model_copy(deep=True))

    def get_chunk(self, chunk_id: str) -> CanonicalChunk | None:
        chunk = self.chunks.get(chunk_id)
        return chunk.model_copy(deep=True) if chunk else None

    def list_chunks(self, version_id: str) -> list[CanonicalChunk]:
        return [
            c.model_copy(deep=True)
            for c in sorted(
                (c for c in self.chunks.values() if c.version_id == version_id),
                key=lambda c: c.ordinal,
            )
        ]

    def mark_index_synced(
        self,
        version_id: str,
        index_name: str,
        status: str,
        failure_reason: str | None = None,
        scope: str = "",
    ) -> None:
        self.sync[(version_id, index_name, scope)] = IndexSyncState(
            version_id=version_id,
            index_name=index_name,
            scope=scope,
            status=status,
            last_synced_at=_now() if status == "synced" else None,
            failure_reason=failure_reason,
        )

    def record_evidence(self, evidence: CitationRecord) -> None:
        self.evidence[evidence.evidence_id] = evidence.model_copy(
            update={"created_at": _now()}
        )

    def get_evidence(self, evidence_id: str) -> CitationRecord | None:
        evidence = self.evidence.get(evidence_id)
        return evidence.model_copy(deep=True) if evidence else None

    def create_job(self, job: IngestionJob) -> None:
        self.jobs[job.job_id] = job.model_copy(update={"created_at": _now(), "updated_at": _now()})

    def update_job(self, job_id: str, status: str, progress: int, error: str | None = None) -> None:
        job = self.jobs.get(job_id)
        if job:
            self.jobs[job_id] = job.model_copy(
                update={
                    "status": status,
                    "progress": progress,
                    "error": error,
                    "updated_at": _now(),
                }
            )

    def health(self) -> bool:
        return True


class PostgresCanonicalStore:
    """SQLAlchemy-backed canonical store.

    Uses a synchronous engine because FastAPI's route handlers and the current
    ingestion service are synchronous; they run in the worker threadpool.
    """

    backend_name = "postgres"

    def __init__(self, dsn: str, pool_size: int = 5, statement_timeout: int = 30) -> None:
        self.engine: Engine = create_engine(
            dsn,
            pool_size=pool_size,
            max_overflow=0,
            pool_pre_ping=True,
            future=True,
        )

        @event.listens_for(self.engine, "connect")
        def _set_timeout(dbapi_connection, _record) -> None:  # pragma: no cover - PG specific
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute(f"SET statement_timeout TO {int(statement_timeout) * 1000}")
                cursor.close()
            except Exception:
                pass

    def register_document(self, document: CanonicalDocument) -> None:
        now = _now()
        with self.engine.begin() as conn:
            found = conn.execute(
                select(documents.c.document_id).where(
                    documents.c.document_id == document.document_id
                )
            ).first()
            if found:
                conn.execute(
                    documents.update()
                    .where(documents.c.document_id == document.document_id)
                    .values(title=document.title, updated_at=now)
                )
            else:
                conn.execute(
                    documents.insert().values(
                        document_id=document.document_id,
                        source_uri=document.source_uri,
                        title=document.title,
                        created_at=now,
                        updated_at=now,
                    )
                )

    def create_version(self, version: DocumentVersion) -> bool:
        with self.engine.begin() as conn:
            found = conn.execute(
                select(document_versions.c.version_id).where(
                    document_versions.c.document_id == version.document_id,
                    document_versions.c.content_sha256 == version.content_sha256,
                )
            ).first()
            if found:
                return False
            conn.execute(
                document_versions.update()
                .where(
                    document_versions.c.document_id == version.document_id,
                    document_versions.c.is_current.is_(True),
                )
                .values(is_current=False)
            )
            conn.execute(
                document_versions.insert().values(
                    version_id=version.version_id,
                    document_id=version.document_id,
                    content_sha256=version.content_sha256,
                    parser_name=version.parser_name,
                    parser_version=version.parser_version,
                    extraction_status=version.extraction_status,
                    is_current=True,
                    parsed_at=_now(),
                )
            )
            return True

    def current_version(self, document_id: str) -> str | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(document_versions.c.version_id).where(
                    document_versions.c.document_id == document_id,
                    document_versions.c.is_current.is_(True),
                )
            ).first()
            return str(row[0]) if row else None

    def upsert_chunks(self, records: list[CanonicalChunk]) -> None:
        with self.engine.begin() as conn:
            for record in records:
                values = record.model_dump()
                values["metadata"] = values.get("metadata") or {}
                found = conn.execute(
                    select(chunks.c.chunk_id).where(chunks.c.chunk_id == record.chunk_id)
                ).first()
                if found:
                    conn.execute(
                        chunks.update().where(chunks.c.chunk_id == record.chunk_id).values(values)
                    )
                else:
                    conn.execute(chunks.insert().values(**values))

    def link_elements(self, links: list[ChunkElementLink]) -> None:
        with self.engine.begin() as conn:
            for link in links:
                values = link.model_dump()
                values["extraction_metadata"] = values.get("extraction_metadata") or {}
                values["extraction_warnings"] = values.get("extraction_warnings") or []
                found = conn.execute(
                    select(chunk_elements.c.chunk_id).where(
                        chunk_elements.c.chunk_id == link.chunk_id,
                        chunk_elements.c.element_id == link.element_id,
                    )
                ).first()
                if not found:
                    conn.execute(chunk_elements.insert().values(**values))

    @staticmethod
    def _to_chunk(row) -> CanonicalChunk:
        return CanonicalChunk(**dict(row._mapping))

    def get_chunk(self, chunk_id: str) -> CanonicalChunk | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(chunks).where(chunks.c.chunk_id == chunk_id)).first()
            return self._to_chunk(row) if row else None

    def list_chunks(self, version_id: str) -> list[CanonicalChunk]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(chunks).where(chunks.c.version_id == version_id).order_by(chunks.c.ordinal)
            ).all()
            return [self._to_chunk(row) for row in rows]

    def mark_index_synced(
        self,
        version_id: str,
        index_name: str,
        status: str,
        failure_reason: str | None = None,
        scope: str = "",
    ) -> None:
        with self.engine.begin() as conn:
            now = _now() if status == "synced" else None
            predicate = (
                (index_sync_state.c.version_id == version_id)
                & (index_sync_state.c.index_name == index_name)
                & (index_sync_state.c.scope == scope)
            )
            found = conn.execute(
                select(index_sync_state.c.version_id).where(predicate)
            ).first()
            values = {
                "status": status,
                "last_synced_at": now,
                "failure_reason": failure_reason,
            }
            if found:
                conn.execute(index_sync_state.update().where(predicate).values(**values))
            else:
                conn.execute(
                    index_sync_state.insert().values(
                        version_id=version_id,
                        index_name=index_name,
                        scope=scope,
                        **values,
                    )
                )

    def record_evidence(self, evidence: CitationRecord) -> None:
        with self.engine.begin() as conn:
            values = evidence.model_dump()
            values["created_at"] = _now()
            found = conn.execute(
                select(citation_records.c.evidence_id).where(
                    citation_records.c.evidence_id == evidence.evidence_id
                )
            ).first()
            if not found:
                conn.execute(citation_records.insert().values(**values))

    def get_evidence(self, evidence_id: str) -> CitationRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(citation_records).where(citation_records.c.evidence_id == evidence_id)
            ).first()
            return CitationRecord(**dict(row._mapping)) if row else None

    def create_job(self, job: IngestionJob) -> None:
        with self.engine.begin() as conn:
            now = _now()
            values = job.model_dump()
            values["created_at"] = now
            values["updated_at"] = now
            conn.execute(ingestion_jobs.insert().values(**values))

    def update_job(self, job_id: str, status: str, progress: int, error: str | None = None) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                ingestion_jobs.update()
                .where(ingestion_jobs.c.job_id == job_id)
                .values(status=status, progress=progress, error=error, updated_at=_now())
            )

    def health(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(select(1))
            return True
        except Exception:
            return False
