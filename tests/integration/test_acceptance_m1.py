"""Milestone 1 acceptance criterion (AGENTS.md section 19).

    lab init demo
    cd demo
    lab validate

must succeed on the generated project. The commands run in a subprocess
through the real module entry point, so the packaging and template lookup
paths are exercised, not only the in-process Typer application.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

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


def test_init_then_validate_succeeds(lab: Lab, tmp_path: Path) -> None:
    created = lab("init", "demo", cwd=tmp_path)
    assert created.returncode == 0, created.stderr
    assert "PRJ-000001" in created.stdout

    project = tmp_path / "demo"
    validated = lab("validate", cwd=project)
    assert validated.returncode == 0, validated.stderr

    report = json.loads(lab("validate", "--json", cwd=project).stdout)
    assert report == {"valid": True, "errors": [], "warnings": []}


def test_validate_works_from_a_subdirectory(lab: Lab, tmp_path: Path) -> None:
    lab("init", "demo", cwd=tmp_path)
    assert lab("validate", cwd=tmp_path / "demo" / "src").returncode == 0


def test_a_broken_manifest_fails_with_exit_code_three(lab: Lab, tmp_path: Path) -> None:
    lab("init", "demo", cwd=tmp_path)
    project = tmp_path / "demo"
    manifest = project / "experiments" / "EXP-000001.yaml"
    manifest.write_text(manifest.read_text().replace("cpus: 1", "cpus: 0"))

    result = lab("validate", "--json", cwd=project)
    assert result.returncode == 3
    assert json.loads(result.stdout)["valid"] is False


def test_generated_project_runs_its_own_smoke_test(lab: Lab, tmp_path: Path) -> None:
    lab("init", "demo", cwd=tmp_path)
    project = tmp_path / "demo"
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=project,
        env={**os.environ, "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
