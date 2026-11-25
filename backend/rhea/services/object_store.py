"""Object storage abstraction for original PDFs and extracted assets.

The canonical database stores metadata; the original bytes live here so they
remain available after parsing and indexing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol


class ObjectStore(Protocol):
    backend_name: str

    def put(self, key: str, data: bytes) -> str: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...


class InMemoryObjectStore:
    backend_name = "memory"

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> str:
        self.objects[key] = data
        return hashlib.sha256(data).hexdigest()

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class FilesystemObjectStore:
    """Local-development adapter using a persistent directory."""

    backend_name = "filesystem"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if self.root not in target.parents and target != self.root:
            raise ValueError("Object key escapes the storage root")
        return target

    def put(self, key: str, data: bytes) -> str:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        target = self._path(key)
        if target.exists():
            target.unlink()


def build_object_store(backend: str, path: str) -> ObjectStore:
    """Select the configured object-store adapter."""
    if backend == "filesystem":
        return FilesystemObjectStore(path)
    if backend == "memory":
        return InMemoryObjectStore()
    raise ValueError(f"Unsupported object store backend: {backend}")
