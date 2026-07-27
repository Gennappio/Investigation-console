"""Projecting the record into the vault, from the CLI.

Projection is a view of what already happened, so it never decides whether a
command succeeded: a run that finished is finished even if the vault is
unreachable. Failures are reported, not swallowed and not fatal.
"""

from __future__ import annotations

import functools
from pathlib import Path

from lab_obsidian.merge import write_note
from lab_obsidian.renderer import render
from lab_obsidian.vault import load_vault_settings

from lab_cli.runtime import (
    default_artifact_store,
    default_component_store,
    default_run_store,
    lab_home,
    obsidian_template_dir,
)
from lab_domain.errors import LabError
from lab_domain.manifests.loader import load_manifest
from lab_domain.manifests.models import ExperimentManifest, RepositoryManifest
from lab_domain.runs import RunRecord
from lab_domain.services.obsidian_service import ProjectionResult, project_workspace
from lab_domain.workspace import (
    MANIFEST_NAME,
    experiment_manifest_paths,
    find_workspace_root,
)


def project_workspace_at(root: Path) -> ProjectionResult:
    """Project a repository and everything recorded about it."""
    settings = load_vault_settings(lab_home())
    repository, findings = load_manifest(
        RepositoryManifest, root / MANIFEST_NAME, MANIFEST_NAME
    )
    if repository is None:
        raise LabError(f"Cannot read {root / MANIFEST_NAME}: {findings[0].message}")

    experiments = []
    for path in experiment_manifest_paths(root):
        manifest, _ = load_manifest(
            ExperimentManifest, path, path.relative_to(root).as_posix()
        )
        if manifest is not None:
            experiments.append(manifest)

    return project_workspace(
        repository,
        tuple(experiments),
        runs=default_run_store(),
        artifacts=default_artifact_store(),
        components=default_component_store(),
        vault=settings,
        render=functools.partial(render, obsidian_template_dir()),
        write=write_note,
    )


def project_after(record: RunRecord, cwd: Path) -> ProjectionResult | None:
    """Refresh the vault once a run has finished.

    Returns ``None`` when there is nothing to do: no vault configured, the run
    still in flight, or the command running outside a repository, which is
    where the manifests that describe the experiment live.
    """
    if not record.is_terminal:
        return None
    if not load_vault_settings(lab_home()).enabled:
        return None
    try:
        return project_workspace_at(find_workspace_root(cwd))
    except LabError:
        return None


def describe(result: ProjectionResult | None) -> list[str]:
    """Lines for the human-readable output of a command that projected."""
    if result is None:
        return []
    lines = [f"  vault:      {len(result.notes)} notes written"]
    for note in result.conflicts:
        lines.append(
            f"    conflict: {note['path']} left untouched; generated note at "
            f"{note.get('sidecar')}"
        )
    return lines


def note_payload(result: ProjectionResult | None) -> list[dict[str, str]]:
    return [dict(note) for note in result.notes] if result is not None else []
