"""Projects known to the platform."""

from __future__ import annotations

from fastapi import APIRouter

from api.dependencies import registry, run_store
from lab_domain.errors import NotFoundError
from lab_domain.ids import ProjectId
from lab_domain.uris import lab_uri

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects() -> dict[str, object]:
    projects = registry().list_projects()
    return {
        "count": len(projects),
        "results": [_summary(p.id, p.name) for p in projects],
    }


@router.get("/{project_id}")
def get_project(project_id: str) -> dict[str, object]:
    identifier = ProjectId(project_id)
    record = registry().find_project(identifier)
    if record is None:
        raise NotFoundError(f"No project {project_id}.")
    runs = [r for r in run_store().list_runs() if r.project_id == identifier]
    return {
        **_summary(record.id, record.name),
        "created_at": record.created_at.isoformat(),
        "runs": len(runs),
        "experiments": sorted({str(r.experiment_id) for r in runs}),
    }


def _summary(project_id: ProjectId, name: str) -> dict[str, object]:
    return {"id": str(project_id), "name": name, "uri": lab_uri(project_id)}
