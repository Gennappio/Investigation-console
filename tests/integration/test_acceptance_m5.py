"""Milestone 5 acceptance criteria (AGENTS.md section 19).

Completion of a run must create or update the expected Markdown notes, and
human text must survive regeneration. Both are checked here against a real
vault directory, through the real CLI.
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
def vault(tmp_path: Path) -> Path:
    return tmp_path / "vault"


@pytest.fixture
def lab(tmp_path: Path, vault: Path) -> Lab:
    environment = {
        **os.environ,
        "PYTHONPATH": str(PACKAGES),
        "LAB_HOME": str(tmp_path / "lab-home"),
        "LAB_TEMPLATES_DIR": str(TEMPLATES),
        "LAB_OBSIDIAN_VAULT": str(vault),
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


def frontmatter(note: Path) -> dict:
    text = note.read_text(encoding="utf-8")
    _, _, rest = text.partition("---\n")
    document, _, _ = rest.partition("\n---")
    return yaml.safe_load(document)


def test_finishing_a_run_creates_the_expected_notes(
    lab: Lab, project: Path, vault: Path
) -> None:
    result = lab("run", "--no-container", cwd=project)
    assert result.returncode == 0, result.stderr

    run_note = vault / "Runs" / "RUN-000001.md"
    experiment_note = vault / "Experiments" / "EXP-000001.md"
    project_note = vault / "Projects" / "PRJ-000001.md"
    assert run_note.is_file()
    assert experiment_note.is_file()
    assert project_note.is_file()

    keys = frontmatter(run_note)
    assert keys["type"] == "run"
    assert keys["run_id"] == "RUN-000001"
    assert keys["experiment"] == "[[EXP-000001]]"
    assert keys["status"] == "completed"
    assert keys["backend"] == "local"
    assert keys["report_uri"] == "lab-report://RUN-000001"
    assert keys["artifacts_uri"] == "lab-run://RUN-000001/artifacts"
    assert keys["managed_by"] == "lab-platform"

    body = run_note.read_text()
    assert "<!-- BEGIN LAB MANAGED -->" in body
    assert "<!-- BEGIN HUMAN NOTES -->" in body
    assert "Executed directly on the host" in body, "deviations belong in the note"

    assert "[[RUN-000001]]" in experiment_note.read_text()
    assert "[[EXP-000001]]" in project_note.read_text()


def test_the_notes_carry_no_artifact_contents(
    lab: Lab, project: Path, vault: Path
) -> None:
    """The vault links to artifacts; it does not become a copy of them."""
    lab("run", "--no-container", cwd=project)
    body = (vault / "Runs" / "RUN-000001.md").read_text()

    assert "metrics.json" in body, "the note names the outputs"
    assert "lab-run://RUN-000001/artifacts" in body
    assert '"score"' not in body, "but not their contents"
    assert "file://" not in body, "and no filesystem paths"


def test_human_text_survives_regeneration(lab: Lab, project: Path, vault: Path) -> None:
    lab("run", "--no-container", cwd=project)
    note = vault / "Runs" / "RUN-000001.md"

    interpretation = "The score is flat across seeds; check the RNG wiring."
    note.write_text(
        note.read_text().replace(
            "## Interpretation\n", f"## Interpretation\n\n{interpretation}\n"
        )
    )

    for _ in range(2):
        synced = lab("sync", "obsidian", cwd=project)
        assert synced.returncode == 0, synced.stderr
        assert interpretation in note.read_text()

    # A second run rewrites the managed part and still leaves the human part.
    lab("run", "--no-container", cwd=project)
    assert interpretation in note.read_text()
    assert "RUN-000002" in (vault / "Experiments" / "EXP-000001.md").read_text()


def test_a_note_the_platform_cannot_parse_is_never_overwritten(
    lab: Lab, project: Path, vault: Path
) -> None:
    lab("run", "--no-container", cwd=project)
    note = vault / "Runs" / "RUN-000001.md"
    handwritten = "# My own notes\n\nWritten by hand, not in the platform format.\n"
    note.write_text(handwritten)

    synced = lab("sync", "obsidian", "--json", cwd=project)
    assert synced.returncode == 0, synced.stderr

    assert note.read_text() == handwritten
    body = json.loads(synced.stdout)
    assert body["conflicts"] == 1
    conflict = next(n for n in body["notes"] if n["outcome"] == "conflict")
    assert conflict["path"] == str(note)
    sidecar = Path(conflict["sidecar"])
    assert sidecar.is_file()
    assert "## Execution summary" in sidecar.read_text()


def test_projection_is_off_until_a_vault_is_configured(
    lab: Lab, project: Path, tmp_path: Path, vault: Path
) -> None:
    environment = {
        **os.environ,
        "PYTHONPATH": str(PACKAGES),
        "LAB_HOME": str(tmp_path / "lab-home"),
        "LAB_TEMPLATES_DIR": str(TEMPLATES),
    }
    environment.pop("LAB_OBSIDIAN_VAULT", None)

    def without_vault(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "lab_cli", *arguments],
            cwd=project,
            env=environment,
            capture_output=True,
            text=True,
        )

    executed = without_vault("run", "--no-container", "--json")
    assert executed.returncode == 0, executed.stderr
    assert json.loads(executed.stdout)["notes"] == []
    assert not vault.exists()

    refused = without_vault("sync", "obsidian")
    assert refused.returncode == 4
    assert "LAB_OBSIDIAN_VAULT" in refused.stderr


def test_a_cluster_run_is_projected_when_status_collects_it(
    lab: Lab, project: Path, vault: Path, tmp_path: Path
) -> None:
    """A queued run has no note until it finishes and is collected."""
    sys.path.insert(0, str(REPOSITORY_ROOT / "tests" / "fixtures"))
    import fake_slurm

    bin_dir = fake_slurm.install(tmp_path / "slurm-bin")
    state = tmp_path / "cluster.json"
    cluster = {
        **os.environ,
        **fake_slurm.environment(bin_dir, state, autostart=False),
        "PYTHONPATH": str(PACKAGES),
        "LAB_HOME": str(tmp_path / "lab-home"),
        "LAB_TEMPLATES_DIR": str(TEMPLATES),
        "LAB_OBSIDIAN_VAULT": str(vault),
    }

    def on_cluster(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "lab_cli", *arguments],
            cwd=project,
            env=cluster,
            capture_output=True,
            text=True,
        )

    submitted = json.loads(
        on_cluster("run", "--backend", "slurm", "--no-container", "--json").stdout
    )
    assert submitted["status"] == "queued"
    assert submitted["notes"] == []

    fake_slurm.start_job(bin_dir, state, submitted["external_job_id"])
    collected = json.loads(on_cluster("status", submitted["run_id"], "--json").stdout)

    assert collected["status"] == "completed"
    assert collected["notes"]
    note = vault / "Runs" / f"{submitted['run_id']}.md"
    assert note.is_file()
    assert frontmatter(note)["backend"] == "slurm"
    assert frontmatter(note)["external_job_id"] == submitted["external_job_id"]
