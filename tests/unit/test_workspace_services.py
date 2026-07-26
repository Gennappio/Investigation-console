from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from lab_domain.errors import WorkspaceNotFoundError
from lab_domain.services.inspect_service import inspect_workspace
from lab_domain.services.validate_service import validate_workspace
from lab_domain.validation.findings import FindingCode
from lab_domain.workspace import experiment_manifest_paths, find_workspace_root

Workspace = Callable[..., Path]


def test_finds_the_root_from_a_subdirectory(workspace_factory: Workspace) -> None:
    root = workspace_factory("valid_lab.yaml")
    nested = root / "src" / "deep"
    nested.mkdir(parents=True)
    assert find_workspace_root(nested) == root.resolve()


def test_reports_a_missing_workspace(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceNotFoundError, match="lab init"):
        find_workspace_root(tmp_path)


def test_collects_experiment_manifests_in_order(workspace_factory: Workspace) -> None:
    root = workspace_factory(
        "valid_lab.yaml", "warnings_only.yaml", "valid_experiment.yaml"
    )
    (root / "experiments" / "notes.md").write_text("not a manifest")
    assert [p.name for p in experiment_manifest_paths(root)] == [
        "valid_experiment.yaml",
        "warnings_only.yaml",
    ]


def test_validates_a_clean_workspace(workspace_factory: Workspace) -> None:
    report = validate_workspace(workspace_factory("valid_lab.yaml"))
    assert report.valid
    assert report.findings == ()


def test_reports_findings_from_every_manifest(workspace_factory: Workspace) -> None:
    root = workspace_factory(
        "valid_lab.yaml", "missing_dataset_version.yaml", "malformed_id.yaml"
    )
    report = validate_workspace(root)
    assert not report.valid
    assert {(f.code, f.file) for f in report.errors} == {
        (
            FindingCode.MISSING_DATASET_VERSION,
            "experiments/missing_dataset_version.yaml",
        ),
        (FindingCode.MALFORMED_ID, "experiments/malformed_id.yaml"),
    }


def test_findings_are_ordered_by_file_then_path(workspace_factory: Workspace) -> None:
    root = workspace_factory(
        "valid_lab.yaml", "warnings_only.yaml", "unbounded_resources.yaml"
    )
    report = validate_workspace(root)
    keys = [(f.file, f.path) for f in report.findings]
    assert keys == sorted(keys)


def test_missing_manifest_is_a_finding_not_a_crash(tmp_path: Path) -> None:
    report = validate_workspace(tmp_path)
    assert [f.code for f in report.errors] == [FindingCode.MANIFEST_NOT_FOUND]


def test_inspect_summarizes_the_workspace(workspace_factory: Workspace) -> None:
    root = workspace_factory("valid_lab.yaml", "valid_experiment.yaml")
    info = inspect_workspace(root)
    assert info.name == "tcell-model"
    assert info.project_id == "PRJ-000001"
    assert info.owners == ("anna.rossi",)
    assert info.runtime.version == "3.12"
    assert info.commands["test"] == ("pytest", "-q")
    assert info.outputs_directory == "results"
    assert [(e.id, e.file) for e in info.experiments] == [
        ("EXP-000001", "experiments/valid_experiment.yaml")
    ]


def test_inspect_skips_experiments_that_do_not_parse(
    workspace_factory: Workspace,
) -> None:
    root = workspace_factory("valid_lab.yaml", "malformed_id.yaml")
    assert inspect_workspace(root).experiments == ()


def test_inspect_requires_a_readable_manifest(tmp_path: Path) -> None:
    (tmp_path / "lab.yaml").write_text("kind: Repository\n")
    with pytest.raises(WorkspaceNotFoundError, match="lab validate"):
        inspect_workspace(tmp_path)
