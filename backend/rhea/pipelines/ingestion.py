import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from rhea.domain.canonical import (
    CanonicalChunk,
    CanonicalDocument,
    ChunkElementLink,
    CitationRecord,
    DocumentVersion,
    IngestionJob,
)
from rhea.domain.models import DocumentIn, IngestResponse
from rhea.pipelines.identity import (
    chunk_id as make_chunk_id,
)
from rhea.pipelines.identity import (
    document_id as make_document_id,
)
from rhea.pipelines.identity import (
    element_id as make_element_id,
)
from rhea.pipelines.identity import (
    evidence_id as make_evidence_id,
)
from rhea.pipelines.identity import (
    version_id as make_version_id,
)
from rhea.services.embeddings import Embedder
from rhea.services.object_store import InMemoryObjectStore, ObjectStore
from rhea.services.security import classify_trust, scan_text
from rhea.stores.graph import GraphStore, Relation
from rhea.stores.relational import CanonicalStore, InMemoryCanonicalStore
from rhea.stores.vector import VectorRecord, VectorStore

RELATION_PATTERNS = {
    "DEPENDS_ON": re.compile(
        r"([A-Z][A-Za-z0-9 _-]{2,40}) depends on ([A-Z][A-Za-z0-9 _-]{2,40})", re.I
    ),
    "MONITORED_BY": re.compile(
        r"([A-Z][A-Za-z0-9 _-]{2,40}) is monitored by ([A-Z][A-Za-z0-9 _-]{2,40})",
        re.I,
    ),
    "RUNS_ON": re.compile(
        r"([A-Z][A-Za-z0-9 _-]{2,40}) runs on ([A-Z][A-Za-z0-9 _-]{2,40})", re.I
    ),
    "OWNED_BY": re.compile(
        r"([A-Z][A-Za-z0-9 _-]{2,40}) is owned by ([A-Z][A-Za-z0-9 _-]{2,40})", re.I
    ),
}

ENTITY_PATTERN = re.compile(r"\b(?:[A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*){0,3})\b")


@dataclass(slots=True)
class Chunk:
    id: str
    source: str
    text: str
    metadata: dict[str, str]


def chunk_text(source: str, text: str, metadata: dict[str, str], size: int = 700) -> list[Chunk]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[Chunk] = []
    current = ""
    for paragraph in paragraphs:
        # A single very long paragraph (common in PDFs) must still be split so
        # every embedded chunk fits the chunk size.
        pieces = [
            paragraph[i : i + size] for i in range(0, len(paragraph), size)
        ] or [paragraph]
        for piece in pieces:
            if current and len(current) + len(piece) + 2 > size:
                chunks.append(Chunk(str(uuid.uuid4()), source, current, metadata))
                current = piece
            else:
                current = f"{current}\n\n{piece}".strip()
    if current:
        chunks.append(Chunk(str(uuid.uuid4()), source, current, metadata))
    return chunks


def normalize_entity(value: str) -> str:
    value = value.strip(" .,:;()")
    for prefix in ("The ", "the ", "A ", "An ", "a ", "an "):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    return value.strip()


def extract_entities(text: str) -> list[str]:
    stop = {
        "The", "This", "A", "An", "It", "For", "When", "Each", "Production",
        "What", "Which", "How", "Where", "Who", "Why",
    }
    entities = {normalize_entity(m.group(0)) for m in ENTITY_PATTERN.finditer(text)}
    return sorted(e for e in entities if len(e) > 2 and e not in stop)[:80]


def extract_relations(text: str) -> list[Relation]:
    relations: list[Relation] = []
    for kind, pattern in RELATION_PATTERNS.items():
        for match in pattern.finditer(text):
            relations.append(
                Relation(
                    source=normalize_entity(match.group(1)),
                    relation=kind,
                    target=normalize_entity(match.group(2)),
                )
            )
    return relations


class IngestionService:
    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        graph_store: GraphStore,
        block_quarantined: bool = False,
        canonical_store: CanonicalStore | None = None,
        object_store: ObjectStore | None = None,
        parser_name: str = "pypdf",
        parser_version: str = "1",
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.block_quarantined = block_quarantined
        self.canonical = canonical_store or InMemoryCanonicalStore()
        self.objects = object_store or InMemoryObjectStore()
        self.parser_name = parser_name
        self.parser_version = parser_version

    def ingest(self, documents: list[DocumentIn]) -> IngestResponse:
        chunk_count = entity_count = relation_count = 0
        quarantined: list[str] = []
        for doc in documents:
            source_uri = doc.metadata.get("document") or doc.source
            title = doc.metadata.get("title", "")
            did = make_document_id(source_uri, title)
            original = doc.source_bytes or doc.text.encode("utf-8")
            vid = make_version_id(original)
            extension = "pdf" if doc.metadata.get("kind") == "pdf" else "txt"
            object_key = f"{did}/{vid}/original.{extension}"

            checksum = self.objects.put(object_key, original)
            self.canonical.register_document(
                CanonicalDocument(
                    document_id=did,
                    source_uri=source_uri,
                    title=title,
                )
            )
            self.canonical.create_version(
                DocumentVersion(
                    version_id=vid,
                    document_id=did,
                    content_sha256=checksum,
                    parser_name=self.parser_name,
                    parser_version=self.parser_version,
                    extraction_status="parsing",
                )
            )

            job_id = str(uuid.uuid4())
            self.canonical.create_job(
                IngestionJob(job_id=job_id, document_id=did, version_id=vid, status="pending")
            )
            self.canonical.update_job(job_id, "running", 10)

            scan = scan_text(doc.text)
            trust = classify_trust(doc.trust, scan)
            if trust == "quarantined":
                quarantined.append(doc.source)
                if self.block_quarantined:
                    self.canonical.update_job(job_id, "failed", 10, "quarantined")
                    continue

            entities = extract_entities(doc.text)
            relations = extract_relations(doc.text)
            entity_count += len(entities)
            relation_count += len(relations)

            metadata = {**doc.metadata, "trust": trust}
            raw_page = metadata.get("page")
            page = int(raw_page) if raw_page and raw_page.isdigit() else None

            canonical_chunks: list[CanonicalChunk] = []
            element_links: list[ChunkElementLink] = []
            # PDF pages share one document version. Page-scope the ordinal so
            # page 2 chunk 1 cannot collide with page 1 chunk 1.
            ordinal_base = page * 10000 if page is not None else 0
            for local_ordinal, chunk in enumerate(
                chunk_text(doc.source, doc.text, metadata), start=1
            ):
                ordinal = ordinal_base + local_ordinal
                cid = make_chunk_id(did, vid, ordinal, chunk.text)
                eid = make_element_id(did, vid, f"text-{ordinal}")
                canonical_chunks.append(
                    CanonicalChunk(
                        chunk_id=cid,
                        document_id=did,
                        version_id=vid,
                        ordinal=ordinal,
                        chunk_type=metadata.get("kind", "paragraph"),
                        content=chunk.text,
                        token_count=len(chunk.text.split()),
                        page_start=page,
                        page_end=page,
                        section=metadata.get("section"),
                        subsection=metadata.get("subsection"),
                        metadata=chunk.metadata,
                    )
                )
                element_links.append(
                    ChunkElementLink(
                        chunk_id=cid,
                        element_id=eid,
                        reading_order=ordinal,
                        source_location=chunk.source,
                        extraction_metadata=chunk.metadata,
                        extraction_warnings=[],
                    )
                )
            for index, record in enumerate(canonical_chunks):
                record.previous_chunk_id = (
                    canonical_chunks[index - 1].chunk_id if index > 0 else None
                )
                record.next_chunk_id = (
                    canonical_chunks[index + 1].chunk_id
                    if index + 1 < len(canonical_chunks)
                    else None
                )

            self.canonical.upsert_chunks(canonical_chunks)
            self.canonical.link_elements(element_links)
            for record in canonical_chunks:
                self.canonical.record_evidence(
                    CitationRecord(
                        evidence_id=make_evidence_id(record.chunk_id, vid),
                        chunk_id=record.chunk_id,
                        version_id=vid,
                        document_id=did,
                        page_start=record.page_start,
                        page_end=record.page_end,
                        filename=source_uri,
                        section=record.section,
                    )
                )
            self.canonical.update_job(job_id, "running", 45)

            try:
                self.graph_store.index_document(doc.source, doc.text, entities, relations)
                self.canonical.mark_index_synced(
                    vid, "neo4j", "synced", scope=doc.source
                )
            except Exception as exc:
                self.canonical.mark_index_synced(
                    vid, "neo4j", "failed", str(exc), scope=doc.source
                )
                self.canonical.update_job(job_id, "failed", 45, str(exc))
                raise

            records: list[VectorRecord] = []
            try:
                for record in canonical_chunks:
                    records.append(
                        VectorRecord(
                            id=record.chunk_id,
                            vector=self.embedder.embed(record.content),
                            text=record.content,
                            source=doc.source,
                            metadata=record.metadata,
                        )
                    )
                self.vector_store.upsert(records)
                self.canonical.mark_index_synced(
                    vid, "qdrant", "synced", scope=doc.source
                )
            except Exception as exc:
                self.canonical.mark_index_synced(
                    vid, "qdrant", "failed", str(exc), scope=doc.source
                )
                self.canonical.update_job(job_id, "failed", 75, str(exc))
                raise

            chunk_count += len(records)
            self.canonical.update_job(job_id, "completed", 100)

        return IngestResponse(
            documents=len(documents),
            chunks=chunk_count,
            entities=entity_count,
            relations=relation_count,
            backends={
                "vector": self.vector_store.backend_name,
                "graph": self.graph_store.backend_name,
            },
            quarantined=quarantined,
        )


def load_sample_documents() -> list[DocumentIn]:
    base = Path(__file__).resolve().parents[2] / "data"
    docs = []
    for path in sorted(base.glob("*.md")):
        docs.append(
            DocumentIn(
                source=path.name,
                text=path.read_text(),
                metadata={"kind": "sample"},
                trust="trusted",
            )
        )
    return docs
