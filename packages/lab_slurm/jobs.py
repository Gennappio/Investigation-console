"""Where a submitted job's paths are kept.

A cluster job outlives the process that submitted it, so a later `lab status`
must be able to find the job's scratch directory without re-reading the
manifest. One small JSON document per job, under ``$LAB_HOME``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from lab_domain.errors import NotFoundError, StateStoreError
from lab_domain.ids import RunId
from lab_registry.files import write_atomically

JOBS_DIRECTORY = "slurm"


class SubmittedJob(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str
    run_id: RunId
    working_directory: Path
    output_directory: Path
    log_directory: Path
    script_path: Path


class JobIndex:
    """Job records for the SLURM backend, one file per job."""

    def __init__(self, home: Path) -> None:
        self._directory = home / JOBS_DIRECTORY

    def save(self, job: SubmittedJob) -> None:
        write_atomically(
            self._directory / f"{job.job_id}.json",
            job.model_dump_json(indent=2) + "\n",
        )

    def get(self, job_id: str) -> SubmittedJob:
        path = self._directory / f"{job_id}.json"
        if not path.is_file():
            raise NotFoundError(
                f"No SLURM job {job_id} recorded in {self._directory}. The run "
                "may have been submitted from another LAB_HOME."
            )
        try:
            return SubmittedJob.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise StateStoreError(f"Job record {path} is unreadable: {exc}.") from exc
