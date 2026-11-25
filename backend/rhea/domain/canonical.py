"""Canonical document/chunk contracts shared by storage and pipelines.

These models are the authoritative representation of a document version and
its chunks. Every index (Qdrant, OpenSearch, Neo4j) must refer to these IDs.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CanonicalDocument(BaseModel):
    document_id: str
    source_uri: str
    title: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentVersion(BaseModel):
    version_id: str
    document_id: str
    content_sha256: str
    parser_name: str = "unknown"
    parser_version: str = "unknown"
    extraction_status: str = "pending"
    is_current: bool = True
    parsed_at: datetime | None = None


class CanonicalChunk(BaseModel):
    chunk_id: str
    document_id: str
    version_id: str
    ordinal: int
    chunk_type: str = "paragraph"
    content: str
    token_count: int = 0
    page_start: int | None = None
    page_end: int | None = None
    section: str | None = None
    subsection: str | None = None
    parent_chunk_id: str | None = None
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class ChunkElementLink(BaseModel):
    chunk_id: str
    element_id: str
    reading_order: int = 0
    source_location: str = ""
    extraction_metadata: dict[str, str] = Field(default_factory=dict)
    extraction_warnings: list[str] = Field(default_factory=list)


class IngestionJob(BaseModel):
    job_id: str
    document_id: str
    version_id: str
    status: str = "pending"
    progress: int = 0
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IndexSyncState(BaseModel):
    version_id: str
    index_name: str
    scope: str = ""  # per-page/per-document scope inside a version
    status: str = "pending"
    last_synced_at: datetime | None = None
    failure_reason: str | None = None


class CitationRecord(BaseModel):
    evidence_id: str
    chunk_id: str
    version_id: str
    document_id: str
    page_start: int | None = None
    page_end: int | None = None
    filename: str
    section: str | None = None
    created_at: datetime | None = None
