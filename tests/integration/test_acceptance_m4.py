"""Milestone 4 acceptance criterion (AGENTS.md section 19).

    lab search components "sensitivity analysis"

must return registered, tested components with machine-readable metadata. The
whole path runs for real here: scaffold, test, publish, search, review.
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


@pytest.fixture
def project(lab: Lab, tmp_path: Path) -> Path:
    created = lab("init", "demo", cwd=tmp_path)
    assert created.returncode == 0, created.stderr
    return tmp_path / "demo"


def test_search_returns_tested_components_with_metadata(
    lab: Lab, project: Path
) -> None:
    for profile in ("smoke", "test"):
        tested = lab("test", "--profile", profile, cwd=project)
        assert tested.returncode == 0, tested.stderr

    published = lab("publish", "component", "--json", cwd=project)
    assert published.returncode == 0, published.stderr
    assert json.loads(published.stdout)["maturity"] == "tested"

    found = lab("search", "components", "sensitivity analysis", "--json", cwd=project)
    assert found.returncode == 0, found.stderr

    body = json.loads(found.stdout)
    assert body["count"] == 1
    component = body["results"][0]
    assert component["id"].startswith("CMP-")
    assert component["name"] == "demo-sensitivity-analysis"
    assert component["version"] == "0.1.0"
    assert component["maturity"] == "tested"
    assert component["maintainer"]
    assert component["command"]
    assert {e["suite"] for e in component["evidence"]} == {
        "software_tests",
        "integration_tests",
    }
    assert all(e["status"] == "passed" for e in component["evidence"])


def test_maturity_follows_the_evidence_that_exists(lab: Lab, project: Path) -> None:
    """The registry states what is proven, and what is still missing."""
    draft = json.loads(lab("publish", "component", "--json", cwd=project).stdout)
    assert draft["maturity"] == "draft"
    assert draft["missing_for_next_level"] == ["integration_tests"]

    lab("test", "--profile", "smoke", cwd=project)
    runnable = json.loads(lab("publish", "component", "--json", cwd=project).stdout)
    assert runnable["maturity"] == "runnable"
    assert runnable["missing_for_next_level"] == ["software_tests"]

    lab("test", "--profile", "test", cwd=project)
    tested = json.loads(lab("publish", "component", "--json", cwd=project).stdout)
    assert tested["maturity"] == "tested"
    assert tested["missing_for_next_level"] == ["reproducibility_tests"]


def test_a_failing_suite_does_not_advance_the_component(
    lab: Lab, project: Path
) -> None:
    manifest = project / "lab.yaml"
    manifest.write_text(
        manifest.read_text().replace(
            "    test:\n      - pytest\n      - -q\n",
            "    test:\n      - python\n      - -c\n      - raise SystemExit(1)\n",
        )
    )
    lab("test", "--profile", "smoke", cwd=project)
    failing = lab("test", "--profile", "test", cwd=project)
    assert failing.returncode == 6

    published = json.loads(lab("publish", "component", "--json", cwd=project).stdout)
    assert published["maturity"] == "runnable"
    statuses = {e["suite"]: e["status"] for e in published["evidence"]}
    assert statuses["software_tests"] == "failed"


def test_review_is_what_grants_validated(
    lab: Lab, project: Path, tmp_path: Path
) -> None:
    lab("test", "--profile", "smoke", cwd=project)
    lab("test", "--profile", "test", cwd=project)
    lab("publish", "component", cwd=project)

    refused = lab(
        "promote",
        "CMP-000001",
        "--to",
        "reproducible",
        "--note",
        "The tests all pass, good enough.",
        cwd=project,
    )
    assert refused.returncode == 3

    granted = lab(
        "promote",
        "CMP-000001",
        "--to",
        "validated",
        "--reviewer",
        "pi.rossi",
        "--note",
        "Recovered the published sensitivity ranking on the reference dataset.",
        "--json",
        cwd=project,
    )
    assert granted.returncode == 0, granted.stderr
    decision_id = json.loads(granted.stdout)["decision_id"]

    decision = json.loads(
        (tmp_path / "lab-home" / "decisions" / f"{decision_id}.json").read_text()
    )
    assert decision["reviewer"] == "pi.rossi"
    assert decision["from_status"] == "tested"
    assert decision["to_status"] == "validated"
    assert "reference dataset" in decision["note"]

    entries = [
        json.loads(line)
        for line in (tmp_path / "lab-home" / "audit.jsonl").read_text().splitlines()
    ]
    assert [e["action"] for e in entries][-1] == "component.promoted"


def test_a_component_citing_an_unknown_profile_fails_validation(
    lab: Lab, project: Path
) -> None:
    manifest = next((project / "components").glob("*.yaml"))
    manifest.write_text(
        manifest.read_text().replace(
            "software_tests: test", "software_tests: nonexistent"
        )
    )
    result = lab("validate", "--json", cwd=project)
    assert result.returncode == 3
    codes = {error["code"] for error in json.loads(result.stdout)["errors"]}
    assert "UNKNOWN_TEST_PROFILE" in codes
