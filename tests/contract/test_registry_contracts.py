"""Contracts of the registry commands: publish, search, promote."""

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
    assert invoke("init", "demo").exit_code == ExitCode.OK
    return tmp_path / "demo"


@pytest.fixture
def tested_project(invoke: Invoke, project: Path) -> Path:
    """A project whose component has integration evidence recorded."""
    assert invoke("test", "--profile", "smoke", cwd=project).exit_code == ExitCode.OK
    return project


def test_publish_reports_the_maturity_and_its_evidence(
    invoke: Invoke, payload: Payload, tested_project: Path
) -> None:
    result = invoke("publish", "component", "--json", cwd=tested_project)
    assert result.exit_code == ExitCode.OK

    body = payload(result)
    assert set(body) == {
        "status",
        "component_id",
        "name",
        "version",
        "maturity",
        "project",
        "evidence",
        "missing_for_next_level",
    }
    assert body["status"] == "published"
    assert body["component_id"] == "CMP-000001"
    assert body["version"] == "0.1.0"
    assert body["maturity"] == "runnable"
    assert body["evidence"] == [
        {"suite": "integration_tests", "profile": "smoke", "status": "passed"}
    ]
    assert body["missing_for_next_level"] == ["software_tests"]


def test_publishing_without_evidence_says_draft(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    body = payload(invoke("publish", "component", "--json", cwd=project))
    assert body["maturity"] == "draft"
    assert body["evidence"] == []


def test_republishing_the_same_version_refreshes_evidence(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    first = payload(invoke("publish", "component", "--json", cwd=project))
    invoke("test", "--profile", "smoke", cwd=project)
    second = payload(invoke("publish", "component", "--json", cwd=project))

    assert first["maturity"] == "draft"
    assert second["status"] == "already_published"
    assert second["component_id"] == first["component_id"]
    assert second["maturity"] == "runnable"


def test_changing_a_published_version_is_refused(invoke: Invoke, project: Path) -> None:
    """Others may depend on a published version, so it cannot change silently."""
    assert invoke("publish", "component", cwd=project).exit_code == ExitCode.OK
    manifest = next((project / "components").glob("*.yaml"))
    manifest.write_text(manifest.read_text().replace("- sensitivity", "- rewritten"))

    result = invoke("publish", "component", cwd=project)
    assert result.exit_code == ExitCode.CONFLICT
    assert "Publish a new version" in result.stderr


def test_a_new_version_keeps_the_component_identifier(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    first = payload(invoke("publish", "component", "--json", cwd=project))
    manifest = next((project / "components").glob("*.yaml"))
    manifest.write_text(
        manifest.read_text().replace("version: 0.1.0", "version: 0.2.0")
    )

    second = payload(invoke("publish", "component", "--json", cwd=project))
    assert second["component_id"] == first["component_id"]
    assert second["version"] == "0.2.0"


def test_publishing_refuses_invalid_manifests(
    invoke: Invoke, project: Path, manifests: Path
) -> None:
    (project / "experiments" / "EXP-000001.yaml").write_text(
        (manifests / "missing_dataset_version.yaml").read_text()
    )
    result = invoke("publish", "component", cwd=project)
    assert result.exit_code == ExitCode.VALIDATION_FAILED


def test_publishing_an_unknown_kind_is_invalid_input(
    invoke: Invoke, project: Path
) -> None:
    assert invoke("publish", "dataset", cwd=project).exit_code == ExitCode.INVALID_INPUT


def test_search_returns_machine_readable_metadata(
    invoke: Invoke, payload: Payload, tested_project: Path
) -> None:
    invoke("publish", "component", cwd=tested_project)
    body = payload(
        invoke(
            "search", "components", "sensitivity analysis", "--json", cwd=tested_project
        )
    )

    assert set(body) == {"query", "count", "results"}
    assert body["count"] == 1
    result = body["results"][0]
    assert set(result) == {
        "id",
        "name",
        "version",
        "maturity",
        "maintainer",
        "description",
        "keywords",
        "project",
        "command",
        "references",
        "evidence",
        "reviewed_by",
        "score",
    }
    assert result["id"] == "CMP-000001"
    assert result["maturity"] == "runnable"
    assert result["score"] > 0


def test_search_without_a_query_lists_the_registry(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    invoke("publish", "component", cwd=project)
    assert payload(invoke("search", "components", "--json", cwd=project))["count"] == 1


def test_search_filters_by_maturity(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    invoke("publish", "component", cwd=project)
    matching = payload(
        invoke("search", "components", "--status", "draft", "--json", cwd=project)
    )
    other = payload(
        invoke("search", "components", "--status", "validated", "--json", cwd=project)
    )
    assert matching["count"] == 1
    assert other["count"] == 0


def test_search_reports_nothing_found_without_failing(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    result = invoke("search", "components", "nonexistent term", "--json", cwd=project)
    assert result.exit_code == ExitCode.OK
    assert payload(result)["count"] == 0


def test_an_unknown_maturity_filter_is_invalid_input(
    invoke: Invoke, project: Path
) -> None:
    result = invoke("search", "components", "--status", "perfect", cwd=project)
    assert result.exit_code == ExitCode.INVALID_INPUT


def test_promotion_records_a_decision(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    invoke("publish", "component", cwd=project)
    body = payload(
        invoke(
            "promote",
            "CMP-000001",
            "--to",
            "validated",
            "--reviewer",
            "pi.rossi",
            "--note",
            "Reproduced the published figure on the reference dataset.",
            "--json",
            cwd=project,
        )
    )
    assert body["maturity"] == "validated"
    assert body["from_status"] == "draft"
    assert body["decision_id"] == "DEC-000001"
    assert body["reviewer"] == "pi.rossi"

    found = payload(invoke("search", "components", "--json", cwd=project))
    assert found["results"][0]["maturity"] == "validated"
    assert found["results"][0]["reviewed_by"] == "pi.rossi"


def test_an_evidenced_level_cannot_be_granted_by_review(
    invoke: Invoke, project: Path
) -> None:
    invoke("publish", "component", cwd=project)
    result = invoke(
        "promote",
        "CMP-000001",
        "--to",
        "tested",
        "--note",
        "It looks fine to me honestly.",
        cwd=project,
    )
    assert result.exit_code == ExitCode.VALIDATION_FAILED
    assert "decided by recorded evidence" in result.stderr


def test_a_promotion_needs_a_real_note(invoke: Invoke, project: Path) -> None:
    invoke("publish", "component", cwd=project)
    result = invoke(
        "promote", "CMP-000001", "--to", "validated", "--note", "ok", cwd=project
    )
    assert result.exit_code == ExitCode.VALIDATION_FAILED


def test_promoting_an_unknown_component_returns_eleven(
    invoke: Invoke, project: Path
) -> None:
    result = invoke(
        "promote",
        "CMP-000404",
        "--to",
        "validated",
        "--note",
        "Reviewed thoroughly enough.",
        cwd=project,
    )
    assert result.exit_code == ExitCode.NOT_FOUND


def test_a_review_survives_republishing(
    invoke: Invoke, payload: Payload, project: Path
) -> None:
    """Re-publishing unchanged content must not quietly undo a PI's judgement."""
    invoke("publish", "component", cwd=project)
    invoke(
        "promote",
        "CMP-000001",
        "--to",
        "validated",
        "--note",
        "Reproduced the published figure on the reference dataset.",
        cwd=project,
    )
    invoke("test", "--profile", "smoke", cwd=project)
    body = payload(invoke("publish", "component", "--json", cwd=project))
    assert body["maturity"] == "validated"
