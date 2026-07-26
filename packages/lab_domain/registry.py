"""Registry port: identifier allocation and the project index.

The domain depends on this protocol, never on a concrete store, so the local
JSON implementation used in Milestone 1 can be replaced by the operational
database in Milestone 2 without touching services (AGENTS.md section 16.1).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from lab_domain.ids import (
    ArtifactId,
    ComponentId,
    DecisionId,
    ExperimentId,
    ProjectId,
    RunId,
)


class ProjectRecord(BaseModel):
    """Index entry for a project.

    ``path`` is a convenience hint for humans, never a canonical reference:
    stable identifiers are the only durable handle (AGENTS.md section 2.4).
    """

    model_config = ConfigDict(frozen=True)

    id: ProjectId
    name: str
    path: str
    created_at: datetime


class IdAllocator(Protocol):
    """Source of the next identifier of a kind, kept apart from any store."""

    def allocate_run_id(self) -> RunId: ...

    def allocate_artifact_id(self) -> ArtifactId: ...

    def allocate_component_id(self) -> ComponentId: ...

    def allocate_decision_id(self) -> DecisionId: ...


class ProjectRegistry(Protocol):
    def allocate_project_id(self) -> ProjectId: ...

    def allocate_experiment_id(self) -> ExperimentId: ...

    def register_project(self, record: ProjectRecord) -> None: ...

    def list_projects(self) -> tuple[ProjectRecord, ...]: ...

    def find_project(self, project_id: ProjectId) -> ProjectRecord | None: ...
