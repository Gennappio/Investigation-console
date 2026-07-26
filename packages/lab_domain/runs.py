"""The run: one concrete execution, recorded immutably (AGENTS.md 2.3, 6.3).

A run record is a frozen model. Progress is expressed by deriving a new record
through :meth:`RunRecord.transitioned_to`, which enforces the state machine of
AGENTS.md section 16.3 and refuses to alter the fields that make a run
reproducible.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

from lab_domain.errors import ImmutableRunError, InvalidTransitionError
from lab_domain.ids import ArtifactId, DatasetId, ExperimentId, ProjectId, RunId


class RunStatus(StrEnum):
    CREATED = "created"
    VALIDATED = "validated"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.CREATED: frozenset({RunStatus.VALIDATED, RunStatus.FAILED}),
    RunStatus.VALIDATED: frozenset({RunStatus.QUEUED, RunStatus.FAILED}),
    RunStatus.QUEUED: frozenset(
        {RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.FAILED}
    ),
    RunStatus.RUNNING: frozenset(
        {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
    ),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}

TERMINAL_STATUSES = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
)

# Fields that describe what was executed. Once recorded they are never
# rewritten; a correction creates a new run (AGENTS.md section 2.3).
IMMUTABLE_FIELDS = frozenset(
    {
        "id",
        "experiment_id",
        "project_id",
        "backend",
        "code",
        "container",
        "datasets",
        "configuration_hash",
        "parameters",
        "seeds",
        "resources",
        "created_at",
        "submitted_by",
    }
)


class RunModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class CodeRef(RunModel):
    """Where the executed code came from."""

    repository: str | None = None
    commit: str | None = None
    dirty: bool = False


class ContainerRef(RunModel):
    """The image a run executed in, pinned by digest where available."""

    image: str | None = None
    digest: str | None = None


class DatasetPin(RunModel):
    id: DatasetId
    version: str


class ResourceRequest(RunModel):
    cpus: int = Field(ge=1)
    memory_mb: int = Field(ge=1)
    gpus: int = Field(ge=0, default=0)
    time_limit: str | None = None


class RunRecord(RunModel):
    id: RunId
    experiment_id: ExperimentId
    project_id: ProjectId
    status: RunStatus
    backend: str
    code: CodeRef
    container: ContainerRef
    datasets: tuple[DatasetPin, ...]
    configuration_hash: str
    parameters: dict[str, Any]
    seeds: tuple[int, ...]
    resources: ResourceRequest
    command: tuple[str, ...]
    submitted_by: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    exit_code: int | None = None
    external_job_id: str | None = None
    artifacts: tuple[ArtifactId, ...] = ()
    # Ways this execution departed from the protocol the manifest describes,
    # reported in the run report (AGENTS.md section 11, item 12).
    deviations: tuple[str, ...] = ()
    failure_reason: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def amended(self, **changes: Any) -> Self:
        """Record something learned about the run without changing its state.

        Used when a backend reports a job identifier for a run that stays
        queued: the state machine has no self-transition for that.
        """
        forbidden = IMMUTABLE_FIELDS & set(changes)
        if forbidden:
            raise ImmutableRunError(
                f"Run {self.id}: {', '.join(sorted(forbidden))} cannot change "
                "after the run is recorded."
            )
        if "status" in changes:
            raise ImmutableRunError(
                f"Run {self.id}: use transitioned_to() to change the status."
            )
        return self.model_copy(update=changes)

    def transitioned_to(self, status: RunStatus, **changes: Any) -> Self:
        """Derive the next record, rejecting impossible transitions."""
        allowed = ALLOWED_TRANSITIONS[self.status]
        if status not in allowed:
            permitted = ", ".join(sorted(s.value for s in allowed)) or "nothing"
            raise InvalidTransitionError(
                f"Run {self.id} cannot move from {self.status.value} to "
                f"{status.value}; allowed: {permitted}."
            )
        forbidden = IMMUTABLE_FIELDS & set(changes)
        if forbidden:
            raise ImmutableRunError(
                f"Run {self.id}: {', '.join(sorted(forbidden))} cannot change "
                "after the run is recorded."
            )
        return self.model_copy(update={"status": status, **changes})


def ensure_amendable(previous: RunRecord, updated: RunRecord) -> None:
    """Reject a save that would rewrite the recorded history of a run."""
    changed = sorted(
        field
        for field in IMMUTABLE_FIELDS
        if getattr(previous, field) != getattr(updated, field)
    )
    if changed:
        raise ImmutableRunError(
            f"Run {previous.id}: {', '.join(changed)} cannot change after the "
            "run is recorded. Create a new run instead."
        )
    if previous.is_terminal and updated.status != previous.status:
        raise ImmutableRunError(
            f"Run {previous.id} is {previous.status.value} and cannot be "
            f"reopened as {updated.status.value}."
        )


def configuration_hash(payload: dict[str, Any]) -> str:
    """Stable hash of everything that defines what a run executes."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
