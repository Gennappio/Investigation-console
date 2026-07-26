"""Local execution backend (AGENTS.md section 8.1).

Runs in an isolated working directory, captures stdout and stderr to files,
records the exit code, enforces the wall-time limit, and never invokes a shell:
the command is an argument list, and placeholders are expanded from a
controlled environment rather than interpolated as text.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from lab_domain.containers import ContainerEngine
from lab_domain.errors import ExecutionFailedError, NotFoundError
from lab_domain.execution import (
    CollectionResult,
    JobState,
    JobStatus,
    RunRequest,
    SubmissionResult,
)
from lab_execution.process import expand_placeholders

STDOUT_FILENAME = "stdout.log"
STDERR_FILENAME = "stderr.log"
TERMINATION_GRACE_SECONDS = 5


@dataclass
class _Job:
    process: subprocess.Popen[bytes]
    request: RunRequest
    stdout_path: Path
    stderr_path: Path
    stdout_handle: IO[bytes]
    stderr_handle: IO[bytes]
    deadline: datetime | None
    state: JobState = JobState.RUNNING
    exit_code: int | None = None
    completed_at: datetime | None = None
    detail: str | None = None


class LocalExecutionBackend:
    """``ExecutionBackend`` running commands as child processes."""

    name = "local"

    def __init__(self, engine: ContainerEngine | None = None) -> None:
        self._engine = engine
        self._jobs: dict[str, _Job] = {}

    def submit(self, request: RunRequest) -> SubmissionResult:
        argv = expand_placeholders(request.argv, request.environment)
        if request.container is not None:
            if self._engine is None:
                raise ExecutionFailedError(
                    "This run requires a container but no container engine is "
                    "configured."
                )
            argv = self._engine.wrap(request.container, argv)

        request.working_directory.mkdir(parents=True, exist_ok=True)
        request.output_directory.mkdir(parents=True, exist_ok=True)
        request.log_directory.mkdir(parents=True, exist_ok=True)
        stdout_path = request.log_directory / STDOUT_FILENAME
        stderr_path = request.log_directory / STDERR_FILENAME

        stdout_handle = stdout_path.open("wb")
        stderr_handle = stderr_path.open("wb")
        try:
            process = subprocess.Popen(
                list(argv),
                cwd=request.working_directory,
                env={**os.environ, **request.environment},
                stdout=stdout_handle,
                stderr=stderr_handle,
            )
        except OSError as exc:
            stdout_handle.close()
            stderr_handle.close()
            raise ExecutionFailedError(
                f"Cannot start {argv[0]!r}: {exc.strerror}."
            ) from exc

        submitted_at = datetime.now(UTC)
        deadline = (
            submitted_at.timestamp() + request.timeout_seconds
            if request.timeout_seconds
            else None
        )
        job_id = str(request.run_id)
        self._jobs[job_id] = _Job(
            process=process,
            request=request,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            stdout_handle=stdout_handle,
            stderr_handle=stderr_handle,
            deadline=datetime.fromtimestamp(deadline, UTC) if deadline else None,
        )
        return SubmissionResult(external_job_id=job_id, submitted_at=submitted_at)

    def status(self, external_job_id: str) -> JobStatus:
        job = self._job(external_job_id)
        if job.state is JobState.RUNNING:
            code = job.process.poll()
            if code is None:
                if job.deadline is not None and datetime.now(UTC) > job.deadline:
                    self._terminate(job)
                    job.state = JobState.TIMED_OUT
                    job.detail = "Wall-time limit exceeded."
                    job.completed_at = datetime.now(UTC)
            else:
                job.exit_code = code
                job.completed_at = datetime.now(UTC)
                job.state = JobState.COMPLETED if code == 0 else JobState.FAILED
                job.detail = None if code == 0 else f"Exit code {code}."
                self._close(job)
        return JobStatus(
            state=job.state,
            exit_code=job.exit_code,
            completed_at=job.completed_at,
            detail=job.detail,
        )

    def cancel(self, external_job_id: str) -> None:
        job = self._job(external_job_id)
        if job.state is JobState.RUNNING:
            self._terminate(job)
            job.state = JobState.CANCELLED
            job.completed_at = datetime.now(UTC)
            job.detail = "Cancelled by the platform."

    def collect(self, external_job_id: str) -> CollectionResult:
        job = self._job(external_job_id)
        if job.state is JobState.RUNNING:
            job.process.wait()
            self.status(external_job_id)
        self._close(job)
        outputs = (
            sorted(p for p in job.request.output_directory.rglob("*") if p.is_file())
            if job.request.output_directory.is_dir()
            else []
        )
        return CollectionResult(
            stdout_path=job.stdout_path,
            stderr_path=job.stderr_path,
            output_paths=tuple(outputs),
            exit_code=job.exit_code,
        )

    def _job(self, external_job_id: str) -> _Job:
        job = self._jobs.get(external_job_id)
        if job is None:
            raise NotFoundError(f"No local job {external_job_id} in this session.")
        return job

    def _terminate(self, job: _Job) -> None:
        job.process.terminate()
        try:
            job.process.wait(timeout=TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            job.process.kill()
            job.process.wait()
        self._close(job)

    @staticmethod
    def _close(job: _Job) -> None:
        for handle in (job.stdout_handle, job.stderr_handle):
            if not handle.closed:
                handle.close()
