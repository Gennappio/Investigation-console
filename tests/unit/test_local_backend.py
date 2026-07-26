from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from lab_execution.local_backend import LocalExecutionBackend, expand_placeholders

from lab_domain.errors import ExecutionFailedError, NotFoundError
from lab_domain.execution import ExecutionBackend, JobState, RunRequest
from lab_domain.runs import ResourceRequest


def make_request(tmp_path: Path, *argv: str, timeout: int | None = None) -> RunRequest:
    return RunRequest(
        run_id="RUN-000001",
        argv=argv,
        environment={"LAB_RUN_ID": "RUN-000001"},
        working_directory=tmp_path / "work",
        output_directory=tmp_path / "work" / "results",
        log_directory=tmp_path / "logs",
        resources=ResourceRequest(cpus=1, memory_mb=1024),
        timeout_seconds=timeout,
    )


def wait_for_terminal(
    backend: LocalExecutionBackend, job_id: str, timeout: float = 30.0
) -> JobState:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = backend.status(job_id).state
        if state is not JobState.RUNNING:
            return state
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} never reached a terminal state")


def test_expands_only_known_placeholders() -> None:
    argv = ("python", "--config", "${LAB_EXPERIMENT_CONFIG}", "${UNSET}")
    expanded = expand_placeholders(argv, {"LAB_EXPERIMENT_CONFIG": "/tmp/c.yaml"})
    assert expanded == ("python", "--config", "/tmp/c.yaml", "${UNSET}")


def test_placeholders_are_not_shell_expanded(tmp_path: Path) -> None:
    """A value with shell metacharacters is passed through as one argument."""
    backend = LocalExecutionBackend()
    request = make_request(
        tmp_path, sys.executable, "-c", "import sys; print(sys.argv[1])", "; rm -rf /"
    )
    job = backend.submit(request)
    assert wait_for_terminal(backend, job.external_job_id) is JobState.COMPLETED
    result = backend.collect(job.external_job_id)
    assert result.stdout_path.read_text().strip() == "; rm -rf /"


def test_satisfies_the_backend_port(tmp_path: Path) -> None:
    backend: ExecutionBackend = LocalExecutionBackend()
    assert backend.name == "local"


def test_captures_stdout_stderr_and_exit_code(tmp_path: Path) -> None:
    backend = LocalExecutionBackend()
    request = make_request(
        tmp_path,
        sys.executable,
        "-c",
        "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)",
    )
    job = backend.submit(request)
    assert wait_for_terminal(backend, job.external_job_id) is JobState.FAILED

    result = backend.collect(job.external_job_id)
    assert result.exit_code == 3
    assert result.stdout_path.read_text().strip() == "out"
    assert result.stderr_path.read_text().strip() == "err"


def test_collects_outputs_from_the_isolated_directory(tmp_path: Path) -> None:
    backend = LocalExecutionBackend()
    request = make_request(
        tmp_path,
        sys.executable,
        "-c",
        "from pathlib import Path; Path('results').mkdir(exist_ok=True); "
        "Path('results/summary.json').write_text('{}')",
    )
    job = backend.submit(request)
    assert wait_for_terminal(backend, job.external_job_id) is JobState.COMPLETED

    result = backend.collect(job.external_job_id)
    assert [p.name for p in result.output_paths] == ["summary.json"]
    assert result.output_paths[0].parent == request.output_directory


def test_enforces_the_wall_time_limit(tmp_path: Path) -> None:
    backend = LocalExecutionBackend()
    request = make_request(
        tmp_path, sys.executable, "-c", "import time; time.sleep(30)", timeout=1
    )
    job = backend.submit(request)
    assert wait_for_terminal(backend, job.external_job_id) is JobState.TIMED_OUT
    assert backend.status(job.external_job_id).detail == "Wall-time limit exceeded."


def test_cancellation_stops_the_process(tmp_path: Path) -> None:
    backend = LocalExecutionBackend()
    job = backend.submit(
        make_request(tmp_path, sys.executable, "-c", "import time; time.sleep(30)")
    )
    backend.cancel(job.external_job_id)
    status = backend.status(job.external_job_id)
    assert status.state is JobState.CANCELLED


def test_unknown_executable_is_a_structured_error(tmp_path: Path) -> None:
    backend = LocalExecutionBackend()
    with pytest.raises(ExecutionFailedError, match="Cannot start"):
        backend.submit(make_request(tmp_path, "definitely-not-a-command-42"))


def test_unknown_job_is_reported(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError, match="No local job"):
        LocalExecutionBackend().status("RUN-000999")


def test_a_container_run_needs_an_engine(tmp_path: Path) -> None:
    from lab_domain.containers import ContainerRunSpec

    backend = LocalExecutionBackend()
    request = make_request(tmp_path, "echo", "hi").model_copy(
        update={"container": ContainerRunSpec(image="lab/demo:1")}
    )
    with pytest.raises(ExecutionFailedError, match="no container engine"):
        backend.submit(request)
