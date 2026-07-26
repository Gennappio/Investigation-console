"""Contracts of the execution commands: payload shapes and exit codes.

These run against the real local backend and file stores; only Docker is
absent, so container paths are covered by unit tests with a fake engine.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import Result

from lab_cli.exit_codes import ExitCode

Invoke = Callable[..., Result]
Payload = Callable[[Result], Any]


@pytest.fixture
def project(invoke: Invoke, tmp_path: Path) -> Path:
    """A generated project, ready to test and run."""
    assert invoke("init", "demo").exit_code == ExitCode.OK
    return tmp_path / "demo"


def test_test_reports_the_suite_it_proved(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    result = invoke("test", "--profile", "smoke", "--json", cwd=project)
    body = payload(result)
    assert result.exit_code == ExitCode.OK
    assert set(body) == {
        "suite",
        "profile",
        "status",
        "exit_code",
        "command",
        "artifacts",
    }
    assert body["suite"] == "integration_tests"
    assert body["profile"] == "smoke"
    assert body["status"] == "passed"
    assert body["exit_code"] == 0


def test_a_failing_profile_returns_six(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    manifest = project / "lab.yaml"
    manifest.write_text(
        manifest.read_text().replace(
            "    test:\n      - pytest\n      - -q\n",
            "    test:\n      - python\n      - -c\n      - raise SystemExit(1)\n",
        )
    )
    result = invoke("test", "--profile", "test", "--json", cwd=project)
    assert result.exit_code == ExitCode.TESTS_FAILED
    assert payload(result)["status"] == "failed"


def test_unknown_profile_is_a_manifest_error(invoke: Invoke, project: Path) -> None:
    result = invoke("test", "--profile", "nonexistent", cwd=project)
    assert result.exit_code == ExitCode.VALIDATION_FAILED


def test_run_records_the_execution(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    result = invoke(
        "run", "--backend", "local", "--no-container", "--json", cwd=project
    )
    body = payload(result)
    assert result.exit_code == ExitCode.OK
    assert set(body) == {
        "run_id",
        "status",
        "backend",
        "experiment_id",
        "external_job_id",
        "exit_code",
        "container_digest",
        "configuration_hash",
        "resources",
        "artifacts",
        "deviations",
    }
    assert body["run_id"] == "RUN-000001"
    assert body["status"] == "completed"
    assert body["backend"] == "local"
    assert body["exit_code"] == 0
    assert body["configuration_hash"].startswith("sha256:")
    assert body["container_digest"] is None
    assert any("host" in deviation for deviation in body["deviations"])
    assert len(body["artifacts"]) >= 3


def test_run_refuses_an_unknown_backend(invoke: Invoke, project: Path) -> None:
    result = invoke("run", "--backend", "kubernetes", cwd=project)
    assert result.exit_code == ExitCode.EXECUTION_FAILED
    assert "Available: local, slurm" in result.stderr


def test_slurm_without_the_scheduler_is_an_environment_error(
    invoke: Invoke, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Off-cluster there is no sbatch, and that is reported as such."""
    monkeypatch.setenv("PATH", str(project))
    result = invoke("run", "--backend", "slurm", "--no-container", cwd=project)
    assert result.exit_code == ExitCode.ENVIRONMENT_ERROR
    assert "sbatch" in result.stderr


def test_run_refuses_invalid_manifests(
    invoke: Invoke, project: Path, manifests: Path
) -> None:
    (project / "experiments" / "EXP-000001.yaml").write_text(
        (manifests / "missing_dataset_version.yaml").read_text()
    )
    result = invoke("run", "--no-container", cwd=project)
    assert result.exit_code == ExitCode.VALIDATION_FAILED
    assert "lab validate" in result.stderr


def test_a_failing_command_fails_the_run(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    manifest = project / "lab.yaml"
    manifest.write_text(
        manifest.read_text().replace(
            "    run:\n      - python\n      - -m\n      - demo.run\n"
            '      - --config\n      - "${LAB_EXPERIMENT_CONFIG}"\n',
            "    run:\n      - python\n      - -c\n      - raise SystemExit(9)\n",
        )
    )
    result = invoke("run", "--no-container", "--json", cwd=project)
    assert result.exit_code == ExitCode.EXECUTION_FAILED
    body = payload(result)
    assert body["status"] == "failed"
    assert body["exit_code"] == 9


def test_status_returns_the_run_record(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    invoke("run", "--no-container", cwd=project)
    body = payload(invoke("status", "RUN-000001", "--json", cwd=project))
    assert body["id"] == "RUN-000001"
    assert body["status"] == "completed"
    assert body["configuration_hash"].startswith("sha256:")
    assert {a["name"] for a in body["artifacts"]} >= {
        "stdout.log",
        "summary.json",
        "manifest.snapshot.yaml",
    }
    assert all(a["checksum"].startswith("sha256:") for a in body["artifacts"])


def test_status_of_an_unknown_run_returns_eleven(invoke: Invoke, project: Path) -> None:
    assert invoke("status", "RUN-000999", cwd=project).exit_code == ExitCode.NOT_FOUND


def test_a_malformed_identifier_is_invalid_input(invoke: Invoke, project: Path) -> None:
    assert invoke("status", "run-1", cwd=project).exit_code == ExitCode.INVALID_INPUT


def test_report_writes_the_documented_bundle(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    invoke("test", "--profile", "smoke", cwd=project)
    invoke("run", "--no-container", cwd=project)
    body = payload(invoke("report", "RUN-000001", "--json", cwd=project))

    assert body["run_id"] == "RUN-000001"
    assert {a["name"] for a in body["artifacts"]} == {
        "report.html",
        "report.json",
        "provenance.json",
        "checksums.txt",
    }
    assert all(a["uri"].startswith("file://") for a in body["artifacts"])


def test_report_of_an_unknown_run_returns_eleven(invoke: Invoke, project: Path) -> None:
    assert invoke("report", "RUN-000999", cwd=project).exit_code == ExitCode.NOT_FOUND


def test_build_without_a_container_engine_is_an_environment_error(
    invoke: Invoke, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no docker on PATH the failure is reported as a dependency error."""
    monkeypatch.setenv("PATH", str(project))
    result = invoke("build", cwd=project)
    assert result.exit_code == ExitCode.ENVIRONMENT_ERROR
