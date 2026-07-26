"""Milestone 2 acceptance criterion (AGENTS.md section 19).

    lab build
    lab test --profile smoke
    lab run --backend local
    lab report RUN-...

must complete on the example project. ``lab build`` needs a container engine,
which CI may not have, so it is exercised here only far enough to prove the
command reaches the engine; the build itself is covered by unit tests with a
fake engine. The rest of the vertical slice runs for real.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPOSITORY_ROOT / "packages"
TEMPLATES = REPOSITORY_ROOT / "templates"

Lab = Callable[..., "subprocess.CompletedProcess[str]"]


@pytest.fixture
def lab(tmp_path: Path) -> Lab:
    environment = {
        **os.environ,
        "PYTHONPATH": str(PACKAGES),
        "LAB_HOME": str(tmp_path / "lab-home"),
        "LAB_TEMPLATES_DIR": str(TEMPLATES),
    }

    def run(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "lab_cli", *arguments],
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
        )

    return run


@pytest.fixture
def project(lab: Lab, tmp_path: Path) -> Path:
    created = lab("init", "demo", cwd=tmp_path)
    assert created.returncode == 0, created.stderr
    return tmp_path / "demo"


def test_the_vertical_slice_completes(lab: Lab, project: Path, tmp_path: Path) -> None:
    tested = lab("test", "--profile", "smoke", "--json", cwd=project)
    assert tested.returncode == 0, tested.stderr
    assert json.loads(tested.stdout)["status"] == "passed"

    executed = lab("run", "--backend", "local", "--no-container", "--json", cwd=project)
    assert executed.returncode == 0, executed.stderr
    run = json.loads(executed.stdout)
    assert run["status"] == "completed"
    run_id = run["run_id"]

    reported = lab("report", run_id, "--json", cwd=project)
    assert reported.returncode == 0, reported.stderr
    bundle = json.loads(reported.stdout)

    artifacts = {a["name"]: a for a in bundle["artifacts"]}
    assert set(artifacts) == {
        "report.html",
        "report.json",
        "provenance.json",
        "checksums.txt",
    }
    for artifact in artifacts.values():
        assert Path(artifact["uri"].removeprefix("file://")).is_file()


def test_the_report_states_every_documented_section(
    lab: Lab, project: Path, tmp_path: Path
) -> None:
    lab("test", "--profile", "smoke", cwd=project)
    lab("run", "--no-container", cwd=project)
    reported = lab("report", "RUN-000001", "--json", cwd=project)
    artifacts = {a["name"]: a for a in json.loads(reported.stdout)["artifacts"]}

    report = json.loads(_read(artifacts["report.json"]))
    assert report["experiment"]["question"]
    assert report["experiment"]["hypothesis"]
    assert report["code"]["commit"] is None  # a fresh scaffold is not a git repository
    assert report["container"]["digest"] is None
    assert report["parameters"] == {"repetitions": 2}
    assert report["seeds"] == [101]
    assert report["resource_usage"]["requested_cpus"] == 1
    assert report["resource_usage"]["wall_time_seconds"] > 0
    assert [t["suite"] for t in report["test_results"]] == ["integration_tests"]
    assert {o["name"] for o in report["outputs"]} == {"summary.json", "metrics.json"}
    assert report["metrics"]["seed"] == 101
    assert report["deviations"]
    assert report["reproduction_command"].startswith("lab run")

    html = _read(artifacts["report.html"])
    for heading in ("Scientific question", "Deviations from protocol", "Reproduction"):
        assert heading in html

    checksums = _read(artifacts["checksums.txt"]).splitlines()
    assert {line.split()[-1] for line in checksums} >= {"summary.json", "stdout.log"}

    provenance = json.loads(_read(artifacts["provenance.json"]))
    assert provenance["run"]["id"] == "RUN-000001"
    assert all(a["checksum"].startswith("sha256:") for a in provenance["artifacts"])


def test_the_run_snapshots_the_manifests_it_executed(lab: Lab, project: Path) -> None:
    lab("run", "--no-container", cwd=project)
    status = json.loads(lab("status", "RUN-000001", "--json", cwd=project).stdout)
    snapshot = next(
        a for a in status["artifacts"] if a["name"] == "manifest.snapshot.yaml"
    )
    documents = list(yaml.safe_load_all(_read(snapshot)))
    kinds = {document["kind"] for document in documents}
    assert kinds == {"Repository", "Experiment"}


def test_history_is_not_rewritten_by_a_second_run(lab: Lab, project: Path) -> None:
    lab("run", "--no-container", cwd=project)
    first = json.loads(lab("status", "RUN-000001", "--json", cwd=project).stdout)
    second = lab("run", "--no-container", "--json", cwd=project)
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["run_id"] == "RUN-000002"
    unchanged = json.loads(lab("status", "RUN-000001", "--json", cwd=project).stdout)
    assert unchanged == first


def test_the_audit_log_records_the_run(lab: Lab, project: Path, tmp_path: Path) -> None:
    lab("run", "--no-container", cwd=project)
    entries = [
        json.loads(line)
        for line in (tmp_path / "lab-home" / "audit.jsonl").read_text().splitlines()
    ]
    assert [e["action"] for e in entries] == [
        "run.created",
        "run.submitted",
        "run.completed",
    ]
    assert all(e["run_id"] == "RUN-000001" for e in entries)


def test_build_reaches_the_container_engine(lab: Lab, project: Path) -> None:
    """Without a usable daemon the failure is reported, never silently skipped."""
    built = lab("build", "--json", cwd=project)
    if built.returncode == 0:
        payload = json.loads(built.stdout)
        assert payload["status"] == "success"
        assert payload["digest"]
        return
    payload = json.loads(built.stdout)
    assert payload["code"] in {"DEPENDENCY_UNAVAILABLE", "BUILD_FAILED"}
    assert built.returncode in {4, 5}


def _read(artifact: dict[str, str]) -> str:
    return Path(artifact["uri"].removeprefix("file://")).read_text(encoding="utf-8")
