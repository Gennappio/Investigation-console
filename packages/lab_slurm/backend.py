"""SLURM execution backend (AGENTS.md section 8.2).

Every scheduler command is invoked with its machine-readable option — `sbatch
--parsable`, `squeue --noheader --format`, `sacct --parsable2 --noheader` — so
nothing depends on parsing output meant for people.

Jobs outlive the process that submits them, so `collect` reads the paths back
from the job index rather than keeping them in memory.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from lab_execution.process import CommandResult, CommandRunner, subprocess_runner
from pydantic import BaseModel, ConfigDict

from lab_domain.containers import ContainerEngine
from lab_domain.errors import DependencyError, ExecutionFailedError
from lab_domain.execution import (
    CollectionResult,
    JobState,
    JobStatus,
    RunRequest,
    SubmissionResult,
)
from lab_slurm.jobs import JobIndex, SubmittedJob
from lab_slurm.script import SlurmJobOptions, render_script, write_script
from lab_slurm.states import exit_code, job_state

SBATCH = "sbatch"
SQUEUE = "squeue"
SACCT = "sacct"
SCANCEL = "scancel"
COMMAND_TIMEOUT_SECONDS = 60


class SlurmOptions(BaseModel):
    """How this platform installation talks to its cluster."""

    model_config = ConfigDict(frozen=True)

    partition: str | None = None
    account: str | None = None
    qos: str | None = None
    cluster: str | None = None

    def job_options(self) -> SlurmJobOptions:
        return SlurmJobOptions(
            partition=self.partition, account=self.account, qos=self.qos
        )


class SlurmExecutionBackend:
    """``ExecutionBackend`` submitting to SLURM through its command-line tools."""

    name = "slurm"

    def __init__(
        self,
        *,
        template_dir: Path,
        index: JobIndex,
        runner: CommandRunner = subprocess_runner,
        options: SlurmOptions | None = None,
        engine: ContainerEngine | None = None,
    ) -> None:
        self._template_dir = template_dir
        self._index = index
        self._run = runner
        self._options = options or SlurmOptions()
        self._engine = engine

    def submit(self, request: RunRequest) -> SubmissionResult:
        script = render_script(
            self._template_dir, request, self._options.job_options(), self._engine
        )
        script_path = write_script(request.working_directory, script)
        request.log_directory.mkdir(parents=True, exist_ok=True)
        request.output_directory.mkdir(parents=True, exist_ok=True)

        result = self._command([SBATCH, "--parsable", str(script_path)])
        if result.returncode != 0:
            raise ExecutionFailedError(
                f"sbatch rejected {request.run_id}: {_tail(result.stderr)}"
            )
        # --parsable prints "<job id>" or "<job id>;<cluster>".
        job_id = result.stdout.strip().split(";")[0].strip()
        if not job_id:
            raise ExecutionFailedError(
                f"sbatch accepted {request.run_id} but reported no job id."
            )

        self._index.save(
            SubmittedJob(
                job_id=job_id,
                run_id=request.run_id,
                working_directory=request.working_directory,
                output_directory=request.output_directory,
                log_directory=request.log_directory,
                script_path=script_path,
            )
        )
        return SubmissionResult(external_job_id=job_id, submitted_at=datetime.now(UTC))

    def status(self, external_job_id: str) -> JobStatus:
        """Ask the queue first, then accounting once the job has left it."""
        queued = self._command(
            [SQUEUE, "--job", external_job_id, "--noheader", "--format=%T"]
        )
        state_word = queued.stdout.strip().splitlines()
        if queued.returncode == 0 and state_word:
            return JobStatus(state=job_state(state_word[0]))

        accounted = self._command(
            [
                SACCT,
                "--jobs",
                external_job_id,
                "--allocations",
                "--parsable2",
                "--noheader",
                "--format=State,ExitCode,End",
            ]
        )
        line = next(
            (line for line in accounted.stdout.strip().splitlines() if line.strip()),
            "",
        )
        if accounted.returncode != 0 or not line:
            # Accounting can lag behind submission; an unknown job is reported
            # as pending rather than guessed to be finished.
            return JobStatus(
                state=JobState.PENDING, detail="Not yet visible in the accounting data."
            )

        fields = line.split("|")
        state = job_state(fields[0])
        code = exit_code(fields[1]) if len(fields) > 1 else None
        completed_at = _parse_slurm_time(fields[2]) if len(fields) > 2 else None
        detail = None
        if state is JobState.TIMED_OUT:
            detail = "The job exceeded its wall-time limit."
        elif state is JobState.CANCELLED:
            detail = f"Cancelled on the cluster ({fields[0].strip()})."
        elif state is JobState.FAILED:
            detail = f"SLURM reported {fields[0].strip()}."
        return JobStatus(
            state=state, exit_code=code, completed_at=completed_at, detail=detail
        )

    def cancel(self, external_job_id: str) -> None:
        result = self._command([SCANCEL, external_job_id])
        if result.returncode != 0:
            raise ExecutionFailedError(
                f"scancel could not cancel job {external_job_id}: "
                f"{_tail(result.stderr)}"
            )

    def collect(self, external_job_id: str) -> CollectionResult:
        job = self._index.get(external_job_id)
        outputs = (
            sorted(p for p in job.output_directory.rglob("*") if p.is_file())
            if job.output_directory.is_dir()
            else []
        )
        return CollectionResult(
            stdout_path=job.log_directory / "stdout.log",
            stderr_path=job.log_directory / "stderr.log",
            output_paths=tuple(outputs),
            exit_code=self.status(external_job_id).exit_code,
            provenance_paths=((job.script_path,) if job.script_path.is_file() else ()),
        )

    def _command(self, argv: Sequence[str]) -> CommandResult:
        try:
            return self._run(argv, timeout=COMMAND_TIMEOUT_SECONDS)
        except DependencyError as exc:
            raise DependencyError(
                f"{argv[0]} is not available. The SLURM backend must run on a "
                f"machine with the scheduler's client tools: {exc}"
            ) from exc


def _parse_slurm_time(value: str) -> datetime | None:
    """SLURM timestamps are local ISO 8601 without a zone."""
    text = value.strip()
    if not text or text.lower() in {"unknown", "none"}:
        return None
    try:
        return datetime.fromisoformat(text).astimezone(UTC)
    except ValueError:
        return None


def _tail(text: str, lines: int = 3) -> str:
    return " / ".join(text.strip().splitlines()[-lines:]) or "no output"
