"""Deterministic identifiers for the canonical document architecture.

No Python ``hash()`` and no ``uuid4()`` are used here: identifiers must survive
process restarts, repeat ingests and re-ordering of workers.
"""

from __future__ import annotations

import hashlib
import uuid

NAMESPACE = uuid.UUID("3f5f5a64-8f1e-4f2a-9f3d-1c6f9a8b7d21")


def _normalize_source(source_uri: str, title: str = "") -> str:
    parts = [source_uri.strip(), title.strip().lower()]
    return "|".join(p for p in parts if p)


def document_id(source_uri: str, title: str = "") -> str:
    """Stable ID for a logical paper, independent of its content version."""
    return str(uuid.uuid5(NAMESPACE, _normalize_source(source_uri, title)))


def version_id(content: bytes) -> str:
    """Content-addressed version ID; changes only when bytes change."""
    return hashlib.sha256(content).hexdigest()


def element_id(document_id: str, version_id: str, parser_key: str) -> str:
    """Stable ID for a parser element within a document version."""
    return str(uuid.uuid5(NAMESPACE, f"{document_id}:{version_id}:{parser_key}"))


def chunk_id(document_id: str, version_id: str, ordinal: int, content: str) -> str:
    """Stable ID for a canonical chunk.

    The content hash makes the ID resistant to accidental ordinal collisions
    after a parser change, while remaining deterministic for identical input.
    """
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return str(uuid.uuid5(NAMESPACE, f"{document_id}:{version_id}:{ordinal}:{digest}"))


def evidence_id(chunk_id: str, version_id: str) -> str:
    """Backend-generated citation ID. The LLM never supplies this value."""
    return str(uuid.uuid5(NAMESPACE, f"evidence:{version_id}:{chunk_id}"))
