"""PDF â†’ page-aware documents for the hybrid index.

Each page becomes its own DocumentIn so citations can point to an exact page.
The regular ingestion service handles chunking, embedding, entity extraction,
injection scanning and indexing into Qdrant + Neo4j.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from pypdf import PdfReader

from rhea.domain.models import DocumentIn


@dataclass(frozen=True, slots=True)
class PdfPage:
    page: int  # 1-based
    text: str


def extract_pages(data: bytes) -> list[PdfPage]:
    """Extract non-empty pages from a PDF byte payload."""
    reader = PdfReader(io.BytesIO(data))
    pages: list[PdfPage] = []
    for number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(PdfPage(page=number, text=text))
    return pages


def documents_from_pdf(
    filename: str,
    data: bytes,
    trust: str = "trusted",
) -> list[DocumentIn]:
    """Convert an uploaded PDF into page-scoped documents ready for ingest.

    ``source`` uses ``file.pdf#pN`` so each page is stored separately while
    ``metadata['document']`` / ``metadata['page']`` keep the human-facing
    citation fields intact.
    """
    documents: list[DocumentIn] = []
    for page in extract_pages(data):
        documents.append(
            DocumentIn(
                source=f"{filename}#p{page.page}",
                text=page.text,
                metadata={
                    "kind": "pdf",
                    "document": filename,
                    "page": str(page.page),
                },
                trust=trust,  # type: ignore[arg-type]
                source_bytes=data,
            )
        )
    return documents


def citation_label(source: str, metadata: dict[str, str]) -> str:
    """Human-readable source label, e.g. ``manual.pdf p.3``."""
    document = metadata.get("document") or source.split("#p", 1)[0]
    page = metadata.get("page")
    return f"{document} p.{page}" if page else source
