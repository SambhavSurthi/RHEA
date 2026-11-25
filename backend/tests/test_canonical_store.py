"""Phase 1 contract tests for canonical identity, storage and object preservation."""

import pytest
from rhea.domain.canonical import (
    CanonicalChunk,
    CanonicalDocument,
    DocumentVersion,
    IngestionJob,
)
from rhea.domain.models import DocumentIn
from rhea.pipelines.identity import (
    chunk_id as make_chunk_id,
)
from rhea.pipelines.identity import (
    document_id as make_document_id,
)
from rhea.pipelines.identity import (
    evidence_id as make_evidence_id,
)
from rhea.pipelines.identity import (
    version_id as make_version_id,
)
from rhea.pipelines.ingestion import IngestionService
from rhea.services.embeddings import HashingEmbedder
from rhea.services.object_store import FilesystemObjectStore, InMemoryObjectStore
from rhea.stores.graph import InMemoryGraphStore
from rhea.stores.relational import InMemoryCanonicalStore
from rhea.stores.vector import InMemoryVectorStore


def test_identifiers_are_deterministic():
    did = make_document_id("paper.pdf", "")
    assert did == make_document_id("paper.pdf", "")
    assert did != make_document_id("other.pdf", "")
    assert make_version_id(b"abc") == make_version_id(b"abc")
    assert make_version_id(b"abc") != make_version_id(b"abd")
    cid = make_chunk_id(did, make_version_id(b"abc"), 1, "text")
    assert cid == make_chunk_id(did, make_version_id(b"abc"), 1, "text")
    assert cid != make_chunk_id(did, make_version_id(b"abc"), 2, "text")


def test_inmemory_store_contract_and_versioning():
    store = InMemoryCanonicalStore()
    did = make_document_id("paper.pdf")
    vid = make_version_id(b"v1")

    store.register_document(CanonicalDocument(document_id=did, source_uri="paper.pdf"))
    assert store.create_version(
        DocumentVersion(version_id=vid, document_id=did, content_sha256="v1")
    )
    assert not store.create_version(
        DocumentVersion(version_id=vid, document_id=did, content_sha256="v1")
    )
    assert store.current_version(did) == vid

    cid = make_chunk_id(did, vid, 1, "evidence text")
    store.upsert_chunks(
        [
            CanonicalChunk(
                chunk_id=cid,
                document_id=did,
                version_id=vid,
                ordinal=1,
                content="evidence text",
                page_start=1,
                page_end=1,
            )
        ]
    )
    assert store.get_chunk(cid) is not None
    assert store.get_chunk(cid).page_start == 1
    assert [c.chunk_id for c in store.list_chunks(vid)] == [cid]

    store.mark_index_synced(vid, "qdrant", "synced", scope="paper.pdf#p1")
    store.mark_index_synced(vid, "neo4j", "failed", "boom", scope="paper.pdf#p1")
    assert store.sync[(vid, "qdrant", "paper.pdf#p1")].status == "synced"
    assert store.sync[(vid, "neo4j", "paper.pdf#p1")].failure_reason == "boom"

    store.create_job(IngestionJob(job_id="job-1", document_id=did, version_id=vid))
    store.update_job("job-1", "completed", 100)
    assert store.jobs["job-1"].status == "completed"

    new_vid = make_version_id(b"v2")
    assert store.create_version(
        DocumentVersion(version_id=new_vid, document_id=did, content_sha256="v2")
    )
    assert store.current_version(did) == new_vid
    assert store.get_chunk(cid).version_id == vid  # old version unchanged


def test_filesystem_object_store_preserves_bytes_and_rejects_escape(tmp_path):
    store = FilesystemObjectStore(tmp_path / "objects")
    key = "doc/version/original.pdf"
    digest = store.put(key, b"%PDF-fake")
    assert store.exists(key)
    assert store.get(key) == b"%PDF-fake"
    assert len(digest) == 64
    with pytest.raises(ValueError):
        store.put("../escape.pdf", b"x")


def test_ingestion_is_idempotent_and_citable():
    canonical = InMemoryCanonicalStore()
    objects = InMemoryObjectStore()
    service = IngestionService(
        HashingEmbedder(32),
        InMemoryVectorStore(),
        InMemoryGraphStore(),
        canonical_store=canonical,
        object_store=objects,
    )
    doc = DocumentIn(
        source="paper.pdf#p1",
        text="The Alpha Service depends on Beta. Alpha is monitored by Prometheus.",
        metadata={"kind": "pdf", "document": "paper.pdf", "page": "1"},
        trust="trusted",
        source_bytes=b"%PDF-original",
    )

    service.ingest([doc])
    did = make_document_id("paper.pdf")
    vid = make_version_id(b"%PDF-original")
    first_ids = [c.chunk_id for c in canonical.list_chunks(vid)]
    assert first_ids
    assert all(c.page_start == 1 for c in canonical.list_chunks(vid))

    service.ingest([doc])
    assert [c.chunk_id for c in canonical.list_chunks(vid)] == first_ids
    assert len([v for v in canonical.versions.values() if v.document_id == did]) == 1

    key = f"{did}/{vid}/original.pdf"
    assert objects.get(key) == b"%PDF-original"

    evidence = canonical.get_evidence(make_evidence_id(first_ids[0], vid))
    assert evidence is not None
    assert evidence.document_id == did
    assert evidence.filename == "paper.pdf"
    assert evidence.page_start == 1

    changed = doc.model_copy(
        update={
            "text": "A completely different paper about attention mechanisms.",
            "source_bytes": b"%PDF-changed",
        }
    )
    service.ingest([changed])
    new_vid = make_version_id(b"%PDF-changed")
    assert new_vid != vid
    assert canonical.get_chunk(first_ids[0]).version_id == vid
