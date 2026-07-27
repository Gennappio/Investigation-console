"""Artifacts, by identifier.

The API reports what an artifact is and what it hashes to. Fetching the bytes
is deliberately absent: an artifact store is not an HTTP file server, and the
run report already links to permanent storage.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from api.dependencies import artifact_store, run_store
from lab_domain.errors import NotFoundError
from lab_domain.ids import ArtifactId, RunId
from lab_domain.uris import lab_uri

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}")
def get_artifact(artifact_id: str) -> dict[str, Any]:
    identifier = ArtifactId(artifact_id)
    store = artifact_store()
    for run in run_store().list_runs():
        for artifact in store.list_artifacts(run.id):
            if artifact.id == identifier:
                return _artifact(artifact, run.id)
    raise NotFoundError(f"No artifact {artifact_id} recorded.")


def _artifact(artifact: Any, run_id: RunId) -> dict[str, Any]:
    return {
        "id": str(artifact.id),
        "uri": lab_uri(artifact.id),
        "run": lab_uri(run_id),
        "kind": artifact.kind.value,
        "name": artifact.name,
        "checksum": artifact.checksum,
        "size_bytes": artifact.size_bytes,
        "media_type": artifact.media_type,
        "created_at": artifact.created_at.isoformat(),
    }
