"""Local filesystem artifact backend (AGENTS.md section 4, development).

Artifacts are copied out of scratch into permanent storage and checksummed on
the way in, so a run is only complete once its outputs are safely stored
(AGENTS.md section 8.3).
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from lab_domain.artifacts import ArtifactKind, ArtifactRecord
from lab_domain.errors import CollectionFailedError, StateStoreError
from lab_domain.ids import ArtifactId, RunId
from lab_domain.registry import IdAllocator
from lab_registry.files import write_atomically

INDEX_FILENAME = "artifacts.json"
UNSCOPED_DIRECTORY = "_unscoped"
CHUNK_SIZE = 1024 * 1024
DEFAULT_MEDIA_TYPE = "application/octet-stream"

_MEDIA_TYPES = {
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".html": "text/html",
    ".log": "text/plain",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".parquet": "application/vnd.apache.parquet",
}


def checksum_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def media_type_of(path: Path) -> str:
    known = _MEDIA_TYPES.get(path.suffix.lower())
    if known is not None:
        return known
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or DEFAULT_MEDIA_TYPE


class FilesystemArtifactStore:
    """``ArtifactStore`` writing under a permanent root directory."""

    def __init__(self, root: Path, allocator: IdAllocator) -> None:
        self._root = root
        self._allocator = allocator

    @property
    def root(self) -> Path:
        return self._root

    def allocate_artifact_id(self) -> ArtifactId:
        return self._allocator.allocate_artifact_id()

    def store(
        self,
        source: Path,
        *,
        kind: ArtifactKind,
        run_id: RunId | None = None,
        name: str | None = None,
    ) -> ArtifactRecord:
        if not source.is_file():
            raise CollectionFailedError(f"Cannot store {source}: not a readable file.")

        artifact_name = name or source.name
        target = self._directory_for(run_id) / artifact_name
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        except OSError as exc:
            raise CollectionFailedError(
                f"Cannot store {source} as {target}: {exc.strerror}."
            ) from exc

        record = ArtifactRecord(
            id=self.allocate_artifact_id(),
            run_id=run_id,
            kind=kind,
            name=artifact_name,
            uri=target.absolute().as_uri(),
            checksum=checksum_of(target),
            size_bytes=target.stat().st_size,
            media_type=media_type_of(target),
            created_at=datetime.now(UTC),
        )
        self._append_to_index(run_id, record)
        return record

    def list_artifacts(self, run_id: RunId) -> tuple[ArtifactRecord, ...]:
        return tuple(self._read_index(run_id))

    def resolve(self, record: ArtifactRecord) -> Path:
        return self._directory_for(record.run_id) / record.name

    def _directory_for(self, run_id: RunId | None) -> Path:
        return self._root / (str(run_id) if run_id is not None else UNSCOPED_DIRECTORY)

    def _index_path(self, run_id: RunId | None) -> Path:
        return self._directory_for(run_id) / INDEX_FILENAME

    def _read_index(self, run_id: RunId | None) -> list[ArtifactRecord]:
        path = self._index_path(run_id)
        if not path.exists():
            return []
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
            return [ArtifactRecord.model_validate(entry) for entry in entries]
        except (OSError, ValueError, ValidationError) as exc:
            raise StateStoreError(
                f"Artifact index {path} is unreadable: {exc}."
            ) from exc

    def _append_to_index(self, run_id: RunId | None, record: ArtifactRecord) -> None:
        # Run outputs are stored once, but a report can be regenerated from the
        # same record: the newest generation of a name replaces the previous.
        kept = [r for r in self._read_index(run_id) if r.name != record.name]
        records = [*kept, record]
        payload = json.dumps([r.model_dump(mode="json") for r in records], indent=2)
        write_atomically(self._index_path(run_id), payload + "\n")
