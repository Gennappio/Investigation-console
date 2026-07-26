"""Milestone 3 acceptance criteria (AGENTS.md section 19), against a fake cluster.

The milestone asks for a real job on the laboratory cluster; no cluster is
reachable from this development machine, so these tests drive the real CLI
against fake `sbatch`, `squeue`, `sacct` and `scancel` executables that behave
like the scheduler does. What they prove is that the platform submits, polls,
cancels and collects correctly through the documented interfaces. What they
cannot prove is that a particular cluster accepts the generated script.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))

import fake_slurm  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPOSITORY_ROOT / "packages"
TEMPLATES = REPOSITORY_ROOT / "templates"

Lab = Callable[..., "subprocess.CompletedProcess[str]"]


@pytest.fixture
def cluster(tmp_path: Path) -> tuple[Path, Path]:
    """A fake cluster: its executables and its state file."""
    bin_dir = fake_slurm.install(tmp_path / "slurm-bin")
    return bin_dir, tmp_path / "cluster.json"


@pytest.fixture
def lab(tmp_path: Path, cluster: tuple[Path, Path]) -> Lab:
    bin_dir, state_path = cluster

    def run(
        *arguments: str, cwd: Path, autostart: bool = True
    ) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            **fake_slurm.environment(bin_dir, state_path, autostart=autostart),
            "PYTHONPATH": str(PACKAGES),
            "LAB_HOME": str(tmp_path / "lab-home"),
            "LAB_TEMPLATES_DIR": str(TEMPLATES),
        }
        return subprocess.run(
            [sys.executable, "-m", "lab_cli", *arguments],
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
        )

    return run


def _run_and_wait(lab: Lab, project: Path) -> dict:
    """Submit and block until the job ends, as `--wait` does."""
    result = lab(
        "run", "--backend", "slurm", "--no-container", "--wait", "--json", cwd=project
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture
def project(lab: Lab, tmp_path: Path) -> Path:
    created = lab("init", "demo", cwd=tmp_path)
    assert created.returncode == 0, created.stderr
    return tmp_path / "demo"


def test_a_job_is_submitted_and_its_state_reflected(lab: Lab, project: Path) -> None:
    submitted = lab(
        "run", "--backend", "slurm", "--no-container", "--json", cwd=project
    )
    assert submitted.returncode == 0, submitted.stderr
    body = json.loads(submitted.stdout)

    assert body["backend"] == "slurm"
    assert body["external_job_id"], "the scheduler's job id must be recorded"
    assert body["status"] in {"queued", "running", "completed"}


def test_status_collects_the_finished_job(lab: Lab, project: Path) -> None:
    submitted = json.loads(
        lab("run", "--backend", "slurm", "--no-container", "--json", cwd=project).stdout
    )
    run_id = submitted["run_id"]

    status = json.loads(lab("status", run_id, "--json", cwd=project).stdout)
    assert status["status"] == "completed"
    assert status["exit_code"] == 0
    assert {a["name"] for a in status["artifacts"]} >= {
        "stdout.log",
        "summary.json",
        "metrics.json",
        "manifest.snapshot.yaml",
    }
    assert all(a["checksum"].startswith("sha256:") for a in status["artifacts"])


def test_a_queued_job_is_reported_as_queued_until_it_starts(
    lab: Lab, project: Path, cluster: tuple[Path, Path]
) -> None:
    bin_dir, state_path = cluster
    submitted = json.loads(
        lab(
            "run",
            "--backend",
            "slurm",
            "--no-container",
            "--json",
            cwd=project,
            autostart=False,
        ).stdout
    )
    run_id, job_id = submitted["run_id"], submitted["external_job_id"]
    assert submitted["status"] == "queued"

    waiting = json.loads(lab("status", run_id, "--json", cwd=project).stdout)
    assert waiting["status"] == "queued"
    assert waiting["artifacts"] == []

    fake_slurm.start_job(bin_dir, state_path, job_id)

    finished = json.loads(lab("status", run_id, "--json", cwd=project).stdout)
    assert finished["status"] == "completed"
    assert finished["started_at"] is not None


def test_wait_blocks_until_the_job_finishes(lab: Lab, project: Path) -> None:
    result = lab(
        "run", "--backend", "slurm", "--no-container", "--wait", "--json", cwd=project
    )
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body["status"] == "completed"
    assert body["artifacts"]


def test_a_failing_job_is_recorded_as_failed(lab: Lab, project: Path) -> None:
    manifest = project / "lab.yaml"
    manifest.write_text(
        manifest.read_text().replace(
            "    run:\n      - python\n      - -m\n      - demo.run\n"
            '      - --config\n      - "${LAB_EXPERIMENT_CONFIG}"\n',
            "    run:\n      - python\n      - -c\n      - raise SystemExit(7)\n",
        )
    )
    submitted = json.loads(
        lab("run", "--backend", "slurm", "--no-container", "--json", cwd=project).stdout
    )
    status = json.loads(
        lab("status", submitted["run_id"], "--json", cwd=project).stdout
    )
    assert status["status"] == "failed"
    assert status["exit_code"] == 7
    assert status["failure_reason"]


def test_cancel_stops_a_queued_job(
    lab: Lab, project: Path, cluster: tuple[Path, Path]
) -> None:
    _, state_path = cluster
    submitted = json.loads(
        lab(
            "run",
            "--backend",
            "slurm",
            "--no-container",
            "--json",
            cwd=project,
            autostart=False,
        ).stdout
    )
    cancelled = lab("cancel", submitted["run_id"], "--json", cwd=project)
    assert cancelled.returncode == 0, cancelled.stderr

    assert fake_slurm.job_state(state_path, submitted["external_job_id"]) == "CANCELLED"
    assert json.loads(cancelled.stdout)["status"] == "cancelled"

    status = json.loads(
        lab("status", submitted["run_id"], "--json", cwd=project).stdout
    )
    assert status["status"] == "cancelled"


def test_cancelling_a_finished_run_is_refused(lab: Lab, project: Path) -> None:
    submitted = json.loads(
        lab(
            "run",
            "--backend",
            "slurm",
            "--no-container",
            "--wait",
            "--json",
            cwd=project,
        ).stdout
    )
    refused = lab("cancel", submitted["run_id"], cwd=project)
    assert refused.returncode == 11
    assert "cannot be cancelled" in refused.stderr


def test_the_report_carries_the_slurm_metadata(lab: Lab, project: Path) -> None:
    submitted = json.loads(
        lab(
            "run",
            "--backend",
            "slurm",
            "--no-container",
            "--wait",
            "--json",
            cwd=project,
        ).stdout
    )
    reported = lab("report", submitted["run_id"], "--json", cwd=project)
    assert reported.returncode == 0, reported.stderr

    artifacts = {a["name"]: a for a in json.loads(reported.stdout)["artifacts"]}
    report = json.loads(
        Path(artifacts["report.json"]["uri"].removeprefix("file://")).read_text()
    )
    assert report["run"]["backend"] == "slurm"
    assert report["run"]["external_job_id"] == submitted["external_job_id"]

    html = Path(artifacts["report.html"]["uri"].removeprefix("file://")).read_text()
    assert "slurm" in html
    assert submitted["external_job_id"] in html


def test_the_generated_script_is_kept_with_the_run(
    lab: Lab, project: Path, tmp_path: Path
) -> None:
    """The script is provenance: it survives in the artifact store, not scratch."""
    submitted = _run_and_wait(lab, project)
    status = json.loads(
        lab("status", submitted["run_id"], "--json", cwd=project).stdout
    )
    stored = next(a for a in status["artifacts"] if a["name"] == "job.sbatch")
    assert stored["kind"] == "job_script"
    script = Path(stored["uri"].removeprefix("file://")).read_text()

    assert script.startswith("#!/bin/bash")
    assert "set -euo pipefail" in script
    assert f"#SBATCH --job-name=lab-{submitted['run_id']}" in script
    assert "#SBATCH --cpus-per-task=1" in script
    assert "#SBATCH --time=00:10:00" in script
    header = [line for line in script.splitlines() if line.startswith("#   run_id")]
    assert header and submitted["run_id"] in header[0]
    assert "export LAB_EXPERIMENT_CONFIG=" in script


def test_scratch_is_removed_after_a_successful_run(
    lab: Lab, project: Path, tmp_path: Path
) -> None:
    """Scratch is temporary; the artifact store holds what matters (8.3)."""
    home = tmp_path / "lab-home"
    (home).mkdir(parents=True, exist_ok=True)
    (home / "policy.json").write_text(json.dumps({"scratch": "delete"}))

    submitted = json.loads(
        lab(
            "run",
            "--backend",
            "slurm",
            "--no-container",
            "--wait",
            "--json",
            cwd=project,
        ).stdout
    )
    assert not (home / "work" / submitted["run_id"]).exists()
    stored = home / "artifacts" / submitted["run_id"]
    assert (stored / "summary.json").is_file()


def test_a_request_above_policy_is_refused(
    lab: Lab, project: Path, tmp_path: Path
) -> None:
    home = tmp_path / "lab-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "policy.json").write_text(
        json.dumps({"max_cpus": 0 + 1, "max_memory_mb": 8})
    )

    refused = lab("run", "--backend", "slurm", "--no-container", cwd=project)
    assert refused.returncode == 3
    assert "above the limit" in refused.stderr
