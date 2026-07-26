"""The `--json` payloads are a stable interface for external agents.

These tests are the executable form of the CLI contract in AGENTS.md
section 13.3; changing a key here is changing a published interface.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from typer.testing import Result

Invoke = Callable[..., Result]
Payload = Callable[[Result], Any]


def test_init_reports_what_it_created(
    invoke: Invoke, payload: Payload, tmp_path: Path
) -> None:
    result = invoke("init", "demo", "--json")
    body = payload(result)
    assert set(body) == {"status", "project_id", "experiment_id", "path", "files"}
    assert body["status"] == "created"
    assert body["project_id"] == "PRJ-000001"
    assert body["experiment_id"] == "EXP-000001"
    assert body["path"] == str(tmp_path / "demo")
    assert "lab.yaml" in body["files"]


def test_validate_matches_the_documented_shape(
    invoke: Invoke, payload: Payload, tmp_path: Path
) -> None:
    invoke("init", "demo")
    body = payload(invoke("validate", "--json", cwd=tmp_path / "demo"))
    assert body == {"valid": True, "errors": [], "warnings": []}


def test_validate_reports_findings_with_code_path_message_file(
    invoke: Invoke, payload: Payload, tmp_path: Path, manifests: Path
) -> None:
    invoke("init", "demo")
    project = tmp_path / "demo"
    (project / "experiments" / "EXP-000001.yaml").write_text(
        (manifests / "missing_dataset_version.yaml").read_text()
    )
    body = payload(invoke("validate", "--json", cwd=project))
    assert body["valid"] is False
    assert body["errors"] == [
        {
            "code": "MISSING_DATASET_VERSION",
            "path": "execution.dataset_refs[0]",
            "message": "Dataset DATA-000001 requires an explicit version.",
            "file": "experiments/EXP-000001.yaml",
        }
    ]
    assert body["warnings"] == []


def test_validate_separates_warnings_from_errors(
    invoke: Invoke, payload: Payload, tmp_path: Path, manifests: Path
) -> None:
    invoke("init", "demo")
    project = tmp_path / "demo"
    (project / "experiments" / "EXP-000001.yaml").write_text(
        (manifests / "warnings_only.yaml").read_text()
    )
    body = payload(invoke("validate", "--json", cwd=project))
    assert body["valid"] is True
    assert body["errors"] == []
    assert {w["code"] for w in body["warnings"]} == {
        "MISSING_SEED_POLICY",
        "MISSING_REFERENCES",
        "MISSING_SCIENTIFIC_VALIDATION",
    }


def test_inspect_describes_the_workspace(
    invoke: Invoke, payload: Payload, tmp_path: Path
) -> None:
    invoke("init", "demo")
    body = payload(invoke("inspect", "--json", cwd=tmp_path / "demo"))
    assert set(body) == {
        "root",
        "name",
        "description",
        "project_id",
        "owners",
        "runtime",
        "commands",
        "outputs_directory",
        "experiments",
    }
    assert body["name"] == "demo"
    assert body["project_id"] == "PRJ-000001"
    assert body["runtime"] == {"type": "python", "version": "3.12"}
    assert body["outputs_directory"] == "results"
    assert body["commands"]["test"] == ["pytest", "-q"]
    assert body["experiments"] == [
        {
            "id": "EXP-000001",
            "title": "Demo experiment",
            "owner": body["experiments"][0]["owner"],
            "file": "experiments/EXP-000001.yaml",
        }
    ]


def test_errors_are_reported_as_json_when_requested(
    invoke: Invoke, payload: Payload
) -> None:
    body = payload(invoke("validate", "--json"))
    assert set(body) == {"status", "code", "message"}
    assert body == {
        "status": "error",
        "code": "MANIFEST_NOT_FOUND",
        "message": body["message"],
    }


def test_json_mode_writes_nothing_but_json(invoke: Invoke) -> None:
    result = invoke("init", "demo", "--json")
    assert result.stdout.lstrip().startswith("{")
    assert result.stdout.rstrip().endswith("}")
