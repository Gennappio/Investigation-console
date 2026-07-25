from __future__ import annotations

from pathlib import Path

import pytest

from lab_domain.manifests.loader import load_manifest, render_path
from lab_domain.manifests.models import ExperimentManifest, RepositoryManifest
from lab_domain.validation.findings import FindingCode, Severity


def test_loads_valid_repository(manifests: Path) -> None:
    manifest, findings = load_manifest(
        RepositoryManifest, manifests / "valid_lab.yaml", "lab.yaml"
    )
    assert findings == []
    assert manifest is not None
    assert manifest.spec.project == "PRJ-000001"
    assert manifest.spec.commands["test"] == ("pytest", "-q")
    assert manifest.spec.outputs is not None
    assert manifest.spec.outputs.directory == "results"


def test_loads_valid_experiment(manifests: Path) -> None:
    manifest, findings = load_manifest(
        ExperimentManifest, manifests / "valid_experiment.yaml", "e.yaml"
    )
    assert findings == []
    assert manifest is not None
    assert manifest.execution.dataset_refs[0].version == "v4"
    assert manifest.execution.resources is not None
    assert manifest.execution.resources.memory_mb == 137439


@pytest.mark.parametrize(
    ("fixture", "code", "path"),
    [
        ("unknown_api_version.yaml", FindingCode.UNKNOWN_SCHEMA_VERSION, "apiVersion"),
        ("unknown_field.yaml", FindingCode.UNKNOWN_FIELD, "execution.hypotesis"),
        (
            "missing_required_field.yaml",
            FindingCode.MISSING_REQUIRED_FIELD,
            "metadata.title",
        ),
        ("malformed_id.yaml", FindingCode.MALFORMED_ID, "metadata.id"),
        (
            "partial_resources.yaml",
            FindingCode.UNBOUNDED_RESOURCES,
            "execution.resources.time_limit",
        ),
    ],
)
def test_structural_errors_map_to_codes(
    manifests: Path, fixture: str, code: FindingCode, path: str
) -> None:
    manifest, findings = load_manifest(ExperimentManifest, manifests / fixture, fixture)
    assert manifest is None
    assert [(f.code, f.path) for f in findings] == [(code, path)]
    assert findings[0].severity is Severity.ERROR
    assert findings[0].file == fixture


def test_invalid_yaml_is_reported(tmp_path: Path) -> None:
    bad = tmp_path / "lab.yaml"
    bad.write_text("metadata:\n  name: x\n :::\n")
    manifest, findings = load_manifest(RepositoryManifest, bad, "lab.yaml")
    assert manifest is None
    assert findings[0].code is FindingCode.YAML_PARSE_ERROR


def test_non_mapping_document_is_reported(tmp_path: Path) -> None:
    bad = tmp_path / "lab.yaml"
    bad.write_text("- just\n- a list\n")
    manifest, findings = load_manifest(RepositoryManifest, bad, "lab.yaml")
    assert manifest is None
    assert findings[0].code is FindingCode.TYPE_ERROR


def test_unreadable_file_is_reported(tmp_path: Path) -> None:
    manifest, findings = load_manifest(
        RepositoryManifest, tmp_path / "absent.yaml", "lab.yaml"
    )
    assert manifest is None
    assert findings[0].code is FindingCode.MANIFEST_NOT_FOUND


def test_manifests_are_frozen(manifests: Path) -> None:
    manifest, _ = load_manifest(
        RepositoryManifest, manifests / "valid_lab.yaml", "lab.yaml"
    )
    assert manifest is not None
    with pytest.raises(Exception, match="frozen"):
        manifest.metadata.name = "other"  # type: ignore[misc]


def test_render_path_uses_indices() -> None:
    assert render_path(("execution", "dataset_refs", 0, "version")) == (
        "execution.dataset_refs[0].version"
    )
    assert render_path(()) == ""
