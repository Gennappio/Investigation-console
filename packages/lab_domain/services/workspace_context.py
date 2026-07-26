"""Everything the execution services need from a validated workspace."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from lab_domain.errors import ManifestInvalidError, NotFoundError
from lab_domain.ids import ExperimentId
from lab_domain.manifests.loader import load_manifest
from lab_domain.manifests.models import ExperimentManifest, RepositoryManifest
from lab_domain.runs import CodeRef
from lab_domain.services.validate_service import validate_workspace
from lab_domain.validation.findings import ValidationReport
from lab_domain.workspace import experiment_manifest_paths


@dataclass(frozen=True)
class WorkspaceContext:
    root: Path
    repository: RepositoryManifest
    experiment: ExperimentManifest
    experiment_file: Path
    report: ValidationReport


def load_validated_workspace(
    root: Path, experiment_id: ExperimentId | None = None
) -> WorkspaceContext:
    """Validate the workspace and select the experiment to work with.

    Commands that build or execute refuse to proceed on manifests that do not
    validate: an invalid manifest cannot describe a reproducible run.
    """
    from lab_domain.manifests.loader import load_manifest

    report = validate_workspace(root)
    if not report.valid:
        raise ManifestInvalidError(
            f"{len(report.errors)} validation error(s) in {root}. "
            "Run `lab validate` for the details."
        )

    repository, _ = load_manifest(RepositoryManifest, root / "lab.yaml", "lab.yaml")
    if repository is None:  # pragma: no cover - validation already guarantees this
        raise ManifestInvalidError(f"Cannot read {root / 'lab.yaml'}.")

    experiment, experiment_file = _select_experiment(root, experiment_id)
    return WorkspaceContext(
        root=root,
        repository=repository,
        experiment=experiment,
        experiment_file=experiment_file,
        report=report,
    )


def _select_experiment(
    root: Path, experiment_id: ExperimentId | None
) -> tuple[ExperimentManifest, Path]:
    candidates = []
    for path in experiment_manifest_paths(root):
        manifest, _ = load_manifest(
            ExperimentManifest, path, path.relative_to(root).as_posix()
        )
        if manifest is not None:
            candidates.append((manifest, path))

    if not candidates:
        raise NotFoundError(
            f"No experiment manifest found under {root / 'experiments'}."
        )
    if experiment_id is None:
        if len(candidates) > 1:
            names = ", ".join(str(m.metadata.id) for m, _ in candidates)
            raise ManifestInvalidError(
                f"This repository defines several experiments ({names}). "
                "Choose one with --experiment."
            )
        return candidates[0]

    for manifest, path in candidates:
        if manifest.metadata.id == experiment_id:
            return manifest, path
    raise NotFoundError(f"No experiment {experiment_id} in {root}.")


def describe_code(root: Path) -> CodeRef:
    """Git provenance of the working tree, when it is under version control."""
    commit = _git(root, "rev-parse", "HEAD")
    if commit is None:
        return CodeRef()
    remote = _git(root, "config", "--get", "remote.origin.url")
    status = _git(root, "status", "--porcelain")
    return CodeRef(repository=remote, commit=commit, dirty=bool(status))


def _git(root: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
