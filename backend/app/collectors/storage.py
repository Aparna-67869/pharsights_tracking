"""Artifact storage: local filesystem (dev) or Azure Blob (production)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class ArtifactStore(Protocol):
    def put(self, key: str, data: bytes) -> str: ...

    def get(self, key: str) -> bytes | None: ...

    def exists(self, key: str) -> bool: ...

    def url_for(self, key: str) -> str: ...


class LocalArtifactStore:
    """Content-addressed local store under ``storage_local_dir``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.write_bytes(data)
        return str(path.relative_to(self.root))

    def get(self, key: str) -> bytes | None:
        path = self.root / key
        return path.read_bytes() if path.exists() else None

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()

    def url_for(self, key: str) -> str:
        return f"/api/v1/documents/artifact/{key}"

    def path_for(self, key: str) -> Path:
        return self.root / key


class AzureBlobArtifactStore:
    """Azure Blob Storage backend using a connection string."""

    def __init__(self, connection_string: str, container: str) -> None:
        from azure.storage.blob import BlobServiceClient  # optional dependency

        self._service = BlobServiceClient.from_connection_string(connection_string)
        self._container = container
        try:
            self._service.create_container(container)
        except Exception:
            pass

    def put(self, key: str, data: bytes) -> str:
        blob = self._service.get_blob_client(self._container, key)
        blob.upload_blob(data, overwrite=True)
        return key

    def get(self, key: str) -> bytes | None:
        try:
            blob = self._service.get_blob_client(self._container, key)
            return blob.download_blob().readall()
        except Exception:
            return None

    def exists(self, key: str) -> bool:
        try:
            return self._service.get_blob_client(self._container, key).exists()
        except Exception:
            return False

    def url_for(self, key: str) -> str:
        return f"/api/v1/documents/artifact/{key}"


_store: ArtifactStore | None = None


def get_store() -> ArtifactStore:
    global _store
    if _store is None:
        if settings.storage_backend == "azure_blob" and settings.azure_storage_connection_string:
            try:
                _store = AzureBlobArtifactStore(
                    settings.azure_storage_connection_string, settings.azure_storage_container
                )
                log.info("artifact store: azure blob")
                return _store
            except Exception as exc:
                log.warning("azure blob unavailable (%s); using local store", exc)
        _store = LocalArtifactStore(settings.artifacts_dir)
        log.info("artifact store: local (%s)", settings.artifacts_dir)
    return _store


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def artifact_key(module: str, source_code: str, filename: str, data: bytes) -> str:
    """Content-addressed key: identical bytes collapse to one stored object."""
    stamp = datetime.now(UTC).strftime("%Y%m")
    digest = content_hash(data)[:16]
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    return f"{module}/{source_code}/{stamp}/{digest}_{safe}"
