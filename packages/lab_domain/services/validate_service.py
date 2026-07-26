"""Validation of a managed repository (`lab validate`)."""

from __future__ import annotations

from pathlib import Path

from lab_domain.manifests.loader import load_manifest
from lab_domain.manifests.models import ExperimentManifest, RepositoryManifest
from lab_domain.validation.findings import Finding, ValidationReport
from lab_domain.validation.rules import (
    LAB_MANIFEST,
    ManifestDoc,
    WorkspaceDocs,
    run_rules,
)
from lab_domain.workspace import experiment_manifest_paths


def load_workspace_docs(root: Path) -> tuple[WorkspaceDocs, list[Finding]]:
    """Parse every manifest of a workspace.

    Returns what parsed successfully plus the structural findings for what did
    not, so validation can report all problems in one pass.
    """
    findings: list[Finding] = []
    raw_texts: dict[str, str] = {}

    manifest_path = root / LAB_MANIFEST
    repository, repository_findings = load_manifest(
        RepositoryManifest, manifest_path, LAB_MANIFEST
    )
    findings.extend(repository_findings)
    _record_text(raw_texts, manifest_path, LAB_MANIFEST)

    experiments: list[ManifestDoc] = []
    for path in experiment_manifest_paths(root):
        label = path.relative_to(root).as_posix()
        experiment, experiment_findings = load_manifest(ExperimentManifest, path, label)
        findings.extend(experiment_findings)
        _record_text(raw_texts, path, label)
        if experiment is not None:
            experiments.append(ManifestDoc(file=label, manifest=experiment))

    docs = WorkspaceDocs(
        repository=repository,
        experiments=tuple(experiments),
        raw_texts=raw_texts,
    )
    return docs, findings


def validate_workspace(root: Path) -> ValidationReport:
    """Validate ``lab.yaml`` and every experiment manifest under ``root``."""
    docs, findings = load_workspace_docs(root)
    return ValidationReport.from_findings(findings + run_rules(docs))


def _record_text(texts: dict[str, str], path: Path, label: str) -> None:
    try:
        texts[label] = path.read_text(encoding="utf-8")
    except OSError:
        return
