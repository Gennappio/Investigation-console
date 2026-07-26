from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from lab_slurm.backend import SlurmExecutionBackend, SlurmOptions
from lab_slurm.jobs import JobIndex
from lab_slurm.script import SlurmJobOptions, job_name, render_script
from lab_slurm.states import exit_code, job_state

from lab_domain.containers import ContainerRunSpec, Mount
from lab_domain.errors import DependencyError, ExecutionFailedError, NotFoundError
from lab_domain.execution import ExecutionBackend, JobState, RunRequest
from lab_domain.runs import ResourceRequest

TEMPLATES = Path(__file__).resolve().parents[2] / "templates" / "slurm"


@dataclass
class FakeSlurm:
    """Answers scheduler commands from a table keyed on the command name."""

    results: dict[str, tuple[int, str, str]] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)

    def __call__(
        self, argv: Sequence[str], *, timeout: int | None = None
    ) -> FakeResult:
        self.calls.append(list(argv))
        code, out, err = self.results.get(argv[0], (0, "", ""))
        return FakeResult(returncode=code, stdout=out, stderr=err)


@dataclass
class FakeResult:
    returncode: int
    stdout: str
    stderr: str


def make_request(tmp_path: Path, *argv: str, container: object = None) -> RunRequest:
    return RunRequest(
        run_id="RUN-000001",
        argv=argv
        or ("python", "-m", "demo.run", "--config", "${LAB_EXPERIMENT_CONFIG}"),
        environment={
            "LAB_RUN_ID": "RUN-000001",
            "LAB_EXPERIMENT_CONFIG": str(tmp_path / "config.yaml"),
        },
        working_directory=tmp_path / "work",
        output_directory=tmp_path / "work" / "results",
        log_directory=tmp_path / "work" / "logs",
        resources=ResourceRequest(
            cpus=32, memory_mb=131072, gpus=2, time_limit="06:00:00"
        ),
        labels={"run_id": "RUN-000001", "commit": "a91bd29"},
        container=container,
    )


def backend_with(
    tmp_path: Path, **results: tuple[int, str, str]
) -> tuple[SlurmExecutionBackend, FakeSlurm]:
    fake = FakeSlurm(results=dict(results))
    return (
        SlurmExecutionBackend(
            template_dir=TEMPLATES,
            index=JobIndex(tmp_path / "home"),
            runner=fake,
            options=SlurmOptions(partition="bio", account="lab"),
        ),
        fake,
    )


def test_satisfies_the_backend_port(tmp_path: Path) -> None:
    backend, _ = backend_with(tmp_path)
    port: ExecutionBackend = backend
    assert port.name == "slurm"


@pytest.mark.parametrize(
    ("reported", "expected"),
    [
        ("PENDING", JobState.PENDING),
        ("CONFIGURING", JobState.PENDING),
        ("RUNNING", JobState.RUNNING),
        ("COMPLETING", JobState.RUNNING),
        ("COMPLETED", JobState.COMPLETED),
        ("FAILED", JobState.FAILED),
        ("OUT_OF_MEMORY", JobState.FAILED),
        ("NODE_FAIL", JobState.FAILED),
        ("TIMEOUT", JobState.TIMED_OUT),
        ("CANCELLED", JobState.CANCELLED),
        ("CANCELLED by 1000", JobState.CANCELLED),
        ("CANCELLED+", JobState.CANCELLED),
        ("", JobState.PENDING),
        ("SOMETHING_NEW", JobState.PENDING),
    ],
)
def test_maps_slurm_states(reported: str, expected: JobState) -> None:
    assert job_state(reported) is expected


@pytest.mark.parametrize(
    ("reported", "expected"),
    [("0:0", 0), ("7:0", 7), ("0:9", 137), ("", None), ("nonsense", None)],
)
def test_reads_the_exit_code(reported: str, expected: int | None) -> None:
    assert exit_code(reported) == expected


def test_job_names_are_sanitised() -> None:
    assert job_name("RUN-000001") == "lab-RUN-000001"
    # Runs of unsafe characters collapse to one hyphen; hyphens are safe.
    assert job_name("RUN 1; rm -rf /") == "lab-RUN-1-rm--rf-"
    assert job_name("x" * 200).startswith("lab-x")
    assert len(job_name("x" * 200)) == 64


def test_script_carries_the_directives_and_provenance(tmp_path: Path) -> None:
    script = render_script(
        TEMPLATES,
        make_request(tmp_path),
        SlurmJobOptions(partition="bio", account="lab", qos="normal"),
    )
    assert script.startswith("#!/bin/bash\n")
    assert "#SBATCH --job-name=lab-RUN-000001" in script
    assert "#SBATCH --cpus-per-task=32" in script
    assert "#SBATCH --mem=131072M" in script
    assert "#SBATCH --time=06:00:00" in script
    assert "#SBATCH --gres=gpu:2" in script
    assert "#SBATCH --partition=bio" in script
    assert "#SBATCH --account=lab" in script
    assert "#SBATCH --qos=normal" in script
    assert "set -euo pipefail" in script
    assert "commit" in script and "a91bd29" in script


def test_script_expands_placeholders_rather_than_leaving_them_to_the_shell(
    tmp_path: Path,
) -> None:
    script = render_script(TEMPLATES, make_request(tmp_path), SlurmJobOptions())
    assert "${LAB_EXPERIMENT_CONFIG}" not in script.split("export ")[-1]
    assert str(tmp_path / "config.yaml") in script


def test_script_quotes_hostile_arguments(tmp_path: Path) -> None:
    script = render_script(
        TEMPLATES,
        make_request(tmp_path, "python", "-c", "print(1)", "; rm -rf /"),
        SlurmJobOptions(),
    )
    assert "'; rm -rf /'" in script
    assert "\n; rm -rf /" not in script


def test_script_runs_the_container_when_one_is_pinned(tmp_path: Path) -> None:
    from lab_containers.apptainer_engine import ApptainerEngine

    request = make_request(
        tmp_path,
        container=ContainerRunSpec(
            image="lab/demo:1.0.0",
            digest="sha256:abcdef",
            workdir="/scratch",
            mounts=(Mount(source=tmp_path, target="/workspace"),),
        ),
    )
    script = render_script(
        TEMPLATES, request, SlurmJobOptions(), engine=ApptainerEngine()
    )
    assert "apptainer exec" in script
    assert "docker://lab/demo@sha256:abcdef" in script


def test_submission_uses_parsable_output_and_records_the_job(tmp_path: Path) -> None:
    backend, fake = backend_with(tmp_path, sbatch=(0, "4242;cluster\n", ""))
    submission = backend.submit(make_request(tmp_path))

    assert submission.external_job_id == "4242"
    assert fake.calls[0][:2] == ["sbatch", "--parsable"]
    assert (tmp_path / "work" / "job.sbatch").is_file()
    assert JobIndex(tmp_path / "home").get("4242").run_id == "RUN-000001"


def test_a_rejected_submission_is_reported(tmp_path: Path) -> None:
    backend, _ = backend_with(
        tmp_path, sbatch=(1, "", "sbatch: error: invalid partition")
    )
    with pytest.raises(ExecutionFailedError, match="invalid partition"):
        backend.submit(make_request(tmp_path))


def test_a_submission_without_a_job_id_is_reported(tmp_path: Path) -> None:
    backend, _ = backend_with(tmp_path, sbatch=(0, "\n", ""))
    with pytest.raises(ExecutionFailedError, match="no job id"):
        backend.submit(make_request(tmp_path))


def test_status_prefers_the_queue(tmp_path: Path) -> None:
    backend, fake = backend_with(tmp_path, squeue=(0, "RUNNING\n", ""))
    assert backend.status("4242").state is JobState.RUNNING
    assert fake.calls[0] == [
        "squeue",
        "--job",
        "4242",
        "--noheader",
        "--format=%T",
    ]


def test_status_falls_back_to_accounting(tmp_path: Path) -> None:
    backend, fake = backend_with(
        tmp_path,
        squeue=(0, "", ""),
        sacct=(0, "COMPLETED|0:0|2026-07-26T12:00:00\n", ""),
    )
    status = backend.status("4242")
    assert status.state is JobState.COMPLETED
    assert status.exit_code == 0
    assert status.completed_at is not None
    assert "--parsable2" in fake.calls[1]
    assert "--noheader" in fake.calls[1]


def test_a_failed_job_reports_its_exit_code(tmp_path: Path) -> None:
    backend, _ = backend_with(
        tmp_path, squeue=(0, "", ""), sacct=(0, "FAILED|7:0|2026-07-26T12:00:00\n", "")
    )
    status = backend.status("4242")
    assert status.state is JobState.FAILED
    assert status.exit_code == 7
    assert status.detail is not None and "FAILED" in status.detail


def test_a_timed_out_job_says_so(tmp_path: Path) -> None:
    backend, _ = backend_with(
        tmp_path, squeue=(0, "", ""), sacct=(0, "TIMEOUT|0:1|Unknown\n", "")
    )
    status = backend.status("4242")
    assert status.state is JobState.TIMED_OUT
    assert status.detail == "The job exceeded its wall-time limit."
    assert status.completed_at is None


def test_an_unknown_job_is_pending_not_finished(tmp_path: Path) -> None:
    """Accounting lags behind submission; a gap must not close a live run."""
    backend, _ = backend_with(tmp_path, squeue=(0, "", ""), sacct=(0, "", ""))
    status = backend.status("4242")
    assert status.state is JobState.PENDING
    assert status.detail is not None


def test_cancellation_calls_scancel(tmp_path: Path) -> None:
    backend, fake = backend_with(tmp_path)
    backend.cancel("4242")
    assert fake.calls[0] == ["scancel", "4242"]


def test_a_refused_cancellation_is_reported(tmp_path: Path) -> None:
    backend, _ = backend_with(tmp_path, scancel=(1, "", "scancel: error: no such job"))
    with pytest.raises(ExecutionFailedError, match="no such job"):
        backend.cancel("4242")


def test_collection_reads_the_paths_back_from_the_index(tmp_path: Path) -> None:
    backend, _ = backend_with(
        tmp_path,
        sbatch=(0, "4242\n", ""),
        squeue=(0, "", ""),
        sacct=(0, "COMPLETED|0:0|2026-07-26T12:00:00\n", ""),
    )
    request = make_request(tmp_path)
    backend.submit(request)
    (request.output_directory / "summary.json").write_text("{}")

    # A fresh backend, as a later `lab status` would build.
    later, _ = backend_with(
        tmp_path,
        squeue=(0, "", ""),
        sacct=(0, "COMPLETED|0:0|2026-07-26T12:00:00\n", ""),
    )
    collection = later.collect("4242")
    assert [p.name for p in collection.output_paths] == ["summary.json"]
    assert collection.stdout_path == request.log_directory / "stdout.log"
    assert collection.exit_code == 0


def test_collecting_an_unknown_job_is_reported(tmp_path: Path) -> None:
    backend, _ = backend_with(tmp_path)
    with pytest.raises(NotFoundError, match="No SLURM job"):
        backend.collect("9999")


def test_a_missing_scheduler_is_a_dependency_error(tmp_path: Path) -> None:
    def missing(argv: Sequence[str], *, timeout: int | None = None) -> FakeResult:
        raise DependencyError(f"{argv[0]} is not installed or not on PATH.")

    backend = SlurmExecutionBackend(
        template_dir=TEMPLATES, index=JobIndex(tmp_path / "home"), runner=missing
    )
    with pytest.raises(DependencyError, match="scheduler's client tools"):
        backend.status("4242")
