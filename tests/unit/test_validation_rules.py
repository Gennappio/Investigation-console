from __future__ import annotations

from pathlib import Path

import pytest

from lab_domain.manifests.loader import load_manifest
from lab_domain.manifests.models import ExperimentManifest, RepositoryManifest
from lab_domain.validation.findings import FindingCode, Severity
from lab_domain.validation.rules import ManifestDoc, WorkspaceDocs, run_rules


def _docs(manifests: Path, repository: str, *experiments: str) -> WorkspaceDocs:
    repo, repo_findings = load_manifest(
        RepositoryManifest, manifests / repository, "lab.yaml"
    )
    assert repo_findings == [], repo_findings
    parsed = []
    raw = {"lab.yaml": (manifests / repository).read_text()}
    for name in experiments:
        manifest, findings = load_manifest(
            ExperimentManifest, manifests / name, f"experiments/{name}"
        )
        assert findings == [], findings
        assert manifest is not None
        parsed.append(ManifestDoc(file=f"experiments/{name}", manifest=manifest))
        raw[f"experiments/{name}"] = (manifests / name).read_text()
    return WorkspaceDocs(repository=repo, experiments=tuple(parsed), raw_texts=raw)


def test_valid_workspace_has_no_findings(manifests: Path) -> None:
    assert run_rules(_docs(manifests, "valid_lab.yaml", "valid_experiment.yaml")) == []


@pytest.mark.parametrize(
    ("fixture", "code", "path"),
    [
        (
            "missing_dataset_version.yaml",
            FindingCode.MISSING_DATASET_VERSION,
            "execution.dataset_refs[0]",
        ),
        (
            "unbounded_resources.yaml",
            FindingCode.UNBOUNDED_RESOURCES,
            "execution.resources",
        ),
        ("project_mismatch.yaml", FindingCode.PROJECT_MISMATCH, "metadata.project"),
    ],
)
def test_experiment_errors(
    manifests: Path, fixture: str, code: FindingCode, path: str
) -> None:
    findings = run_rules(_docs(manifests, "valid_lab.yaml", fixture))
    errors = [f for f in findings if f.severity is Severity.ERROR]
    assert [(f.code, f.path, f.file) for f in errors] == [
        (code, path, f"experiments/{fixture}")
    ]


def test_missing_dataset_version_message_matches_the_cli_contract(
    manifests: Path,
) -> None:
    findings = run_rules(
        _docs(manifests, "valid_lab.yaml", "missing_dataset_version.yaml")
    )
    finding = next(f for f in findings if f.code is FindingCode.MISSING_DATASET_VERSION)
    assert finding.message == "Dataset DATA-000001 requires an explicit version."


def test_repository_without_outputs_is_an_error(
    manifests: Path, tmp_path: Path
) -> None:
    text = (manifests / "valid_lab.yaml").read_text()
    trimmed = text.replace("  outputs:\n    directory: results\n", "")
    stripped = tmp_path / "lab.yaml"
    stripped.write_text(trimmed)
    repo, findings = load_manifest(RepositoryManifest, stripped, "lab.yaml")
    assert findings == []
    assert repo is not None
    codes = [f.code for f in run_rules(WorkspaceDocs(repository=repo))]
    assert codes == [FindingCode.MISSING_OUTPUT_LOCATION]


def test_repository_without_owners_warns(manifests: Path, tmp_path: Path) -> None:
    text = (manifests / "valid_lab.yaml").read_text()
    trimmed = text.replace("  owners:\n    - anna.rossi\n", "")
    stripped = tmp_path / "lab.yaml"
    stripped.write_text(trimmed)
    repo, findings = load_manifest(RepositoryManifest, stripped, "lab.yaml")
    assert findings == []
    assert repo is not None
    results = run_rules(WorkspaceDocs(repository=repo))
    assert [(f.severity, f.code) for f in results] == [
        (Severity.WARNING, FindingCode.MISSING_MAINTAINER)
    ]


def test_sparse_experiment_produces_warnings_only(manifests: Path) -> None:
    findings = run_rules(_docs(manifests, "valid_lab.yaml", "warnings_only.yaml"))
    assert all(f.severity is Severity.WARNING for f in findings)
    assert {f.code for f in findings} == {
        FindingCode.MISSING_SEED_POLICY,
        FindingCode.MISSING_REFERENCES,
        FindingCode.MISSING_SCIENTIFIC_VALIDATION,
    }


def test_secret_in_manifest_is_an_error(manifests: Path) -> None:
    text = (manifests / "secret_in_manifest.yaml").read_text()
    findings = run_rules(WorkspaceDocs(raw_texts={"lab.yaml": text}))
    assert [f.code for f in findings] == [FindingCode.SECRET_DETECTED]
    assert findings[0].file == "lab.yaml"


@pytest.mark.parametrize(
    "line",
    [
        "  token: ghp_0123456789abcdefghijklmnopqrstuvwxyz",
        "  aws_key: AKIAIOSFODNN7EXAMPLE",
        "  registry_password: hunter2",
        '  api_key: "abc123"',
    ],
)
def test_secret_patterns_are_detected(line: str) -> None:
    findings = run_rules(WorkspaceDocs(raw_texts={"lab.yaml": line}))
    assert [f.code for f in findings] == [FindingCode.SECRET_DETECTED]


@pytest.mark.parametrize(
    "line",
    [
        "  token: ${LAB_REGISTRY_TOKEN}",
        '  password: "${DB_PASSWORD}"',
        "  api_key: $LAB_API_KEY",
        "  # token: ghp_0123456789abcdefghijklmnopqrstuvwxyz",
        "  description: password rotation experiment",
    ],
)
def test_placeholders_and_prose_are_not_secrets(line: str) -> None:
    assert run_rules(WorkspaceDocs(raw_texts={"lab.yaml": line})) == []
