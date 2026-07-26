"""Execution port (AGENTS.md section 8).

The domain describes what to execute; backends decide where. Local execution
lands in Milestone 2, SLURM in Milestone 3, without changing this contract.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from lab_domain.containers import ContainerRunSpec
from lab_domain.ids import RunId


class ExecutionModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class RunRequest(ExecutionModel):
    run_id: RunId
    argv: tuple[str, ...]
    environment: dict[str, str]
    # Isolated scratch directory; permanent storage is a separate concern
    # (AGENTS.md section 8.3).
    working_directory: Path
    output_directory: Path
    log_directory: Path
    timeout_seconds: int | None = None
    container: ContainerRunSpec | None = None


class SubmissionResult(ExecutionModel):
    external_job_id: str
    submitted_at: datetime


class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class JobStatus(ExecutionModel):
    state: JobState
    exit_code: int | None = None
    completed_at: datetime | None = None
    detail: str | None = None


class CollectionResult(ExecutionModel):
    stdout_path: Path
    stderr_path: Path
    output_paths: tuple[Path, ...]
    exit_code: int | None


class ExecutionBackend(Protocol):
    name: str

    def submit(self, request: RunRequest) -> SubmissionResult: ...

    def status(self, external_job_id: str) -> JobStatus: ...

    def cancel(self, external_job_id: str) -> None: ...

    def collect(self, external_job_id: str) -> CollectionResult: ...
