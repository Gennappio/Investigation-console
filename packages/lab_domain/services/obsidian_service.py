"""Projection of the record into an Obsidian vault (AGENTS.md section 12).

The vault is a view. Every fact here is read from the run store, the registry
and the manifests; the notes carry links back to those, never copies of them.
Human-authored sections are preserved by the merge, and a note that cannot be
parsed safely is left alone (ADR 0010).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from lab_domain.artifacts import ArtifactKind
from lab_domain.components import ComponentRecord
from lab_domain.errors import StateStoreError
from lab_domain.ids import ExperimentId, ProjectId, RunId
from lab_domain.manifests.models import ExperimentManifest, RepositoryManifest
from lab_domain.runs import RunRecord
from lab_domain.storage import ArtifactStore, ComponentStore, RunStore
from lab_domain.uris import artifacts_uri, lab_uri, report_uri
from lab_domain.validation.rules import find_secrets

MANAGED_BY = "lab-platform"

HUMAN_PLACEHOLDER = "\n".join(
    [
        "## Interpretation",
        "",
        "## Limitations",
        "",
        "## Follow-up",
        "",
    ]
)

PROJECT_PLACEHOLDER = "\n".join(
    [
        "## Context",
        "",
        "## Decisions",
        "",
        "## Open questions",
        "",
    ]
)


class NoteWriter(Protocol):
    def __call__(
        self,
        path: Path,
        *,
        frontmatter: dict[str, Any],
        managed: str,
        title: str,
        human_placeholder: str,
    ) -> Any: ...


class Renderer(Protocol):
    def __call__(self, template: str, context: dict[str, Any]) -> str: ...


class VaultPaths(Protocol):
    def project_note(
        self, project_id: ProjectId, override: str | None = None
    ) -> Path: ...

    def experiment_note(self, experiment_id: ExperimentId) -> Path: ...

    def run_note(self, run_id: RunId) -> Path: ...


class ProjectionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    notes: tuple[dict[str, str], ...]

    @property
    def conflicts(self) -> tuple[dict[str, str], ...]:
        return tuple(note for note in self.notes if note["outcome"] == "conflict")


def project_workspace(
    repository: RepositoryManifest,
    experiments: tuple[ExperimentManifest, ...],
    *,
    runs: RunStore,
    artifacts: ArtifactStore,
    components: ComponentStore | None,
    vault: VaultPaths,
    render: Renderer,
    write: NoteWriter,
) -> ProjectionResult:
    """Write the project, experiment and run notes of one repository."""
    written: list[dict[str, str]] = []
    project_id = repository.spec.project
    all_runs = runs.list_runs()
    project_runs = tuple(run for run in all_runs if run.project_id == project_id)

    for experiment in experiments:
        experiment_runs = tuple(
            run for run in all_runs if run.experiment_id == experiment.metadata.id
        )
        written.append(
            _write_experiment(experiment, experiment_runs, vault, render, write)
        )
        for run in experiment_runs:
            written.append(_write_run(run, artifacts, vault, render, write))

    published = (
        tuple(
            record
            for record in components.list_components()
            if record.project_id == project_id
        )
        if components is not None
        else ()
    )
    written.append(
        _write_project(
            repository, experiments, project_runs, published, vault, render, write
        )
    )
    return ProjectionResult(notes=tuple(written))


def project_run(
    run: RunRecord,
    repository: RepositoryManifest,
    experiment: ExperimentManifest,
    *,
    runs: RunStore,
    artifacts: ArtifactStore,
    components: ComponentStore | None,
    vault: VaultPaths,
    render: Renderer,
    write: NoteWriter,
) -> ProjectionResult:
    """Project one finished run, and refresh the notes that link to it."""
    return project_workspace(
        repository,
        (experiment,),
        runs=runs,
        artifacts=artifacts,
        components=components,
        vault=vault,
        render=render,
        write=write,
    )


def _write_run(
    run: RunRecord,
    artifacts: ArtifactStore,
    vault: VaultPaths,
    render: Renderer,
    write: NoteWriter,
) -> dict[str, str]:
    stored = tuple(
        artifact
        for artifact in artifacts.list_artifacts(run.id)
        if artifact.kind is not ArtifactKind.LOG
    )
    managed = render(
        "run.md.j2",
        {
            "run": run,
            "artifacts": stored,
            "duration": _duration(run),
            "report_uri": report_uri(run.id),
            "artifacts_uri": artifacts_uri(run.id),
            "reproduction_command": _reproduction(run),
        },
    )
    frontmatter = {
        "type": "run",
        "run_id": str(run.id),
        "experiment": f"[[{run.experiment_id}]]",
        "project": f"[[{run.project_id}]]",
        "status": run.status.value,
        "backend": run.backend,
        "external_job_id": run.external_job_id,
        "git_commit": run.code.commit,
        "container_digest": run.container.digest,
        "configuration_hash": run.configuration_hash,
        "report_uri": report_uri(run.id),
        "artifacts_uri": artifacts_uri(run.id),
        "managed_by": MANAGED_BY,
    }
    return _write(
        write,
        vault.run_note(run.id),
        frontmatter=frontmatter,
        managed=managed,
        title=str(run.id),
        human_placeholder=HUMAN_PLACEHOLDER,
    )


def _write_experiment(
    experiment: ExperimentManifest,
    runs: tuple[RunRecord, ...],
    vault: VaultPaths,
    render: Renderer,
    write: NoteWriter,
) -> dict[str, str]:
    managed = render("experiment.md.j2", {"experiment": experiment, "runs": runs})
    frontmatter = {
        "type": "experiment",
        "experiment_id": str(experiment.metadata.id),
        "project": f"[[{experiment.metadata.project}]]",
        "title": experiment.metadata.title,
        "owner": experiment.metadata.owner,
        "experiment_uri": lab_uri(experiment.metadata.id),
        "runs": len(runs),
        "managed_by": MANAGED_BY,
    }
    return _write(
        write,
        vault.experiment_note(experiment.metadata.id),
        frontmatter=frontmatter,
        managed=managed,
        title=f"{experiment.metadata.id}: {experiment.metadata.title}",
        human_placeholder=HUMAN_PLACEHOLDER,
    )


def _write_project(
    repository: RepositoryManifest,
    experiments: tuple[ExperimentManifest, ...],
    runs: tuple[RunRecord, ...],
    components: tuple[ComponentRecord, ...],
    vault: VaultPaths,
    render: Renderer,
    write: NoteWriter,
) -> dict[str, str]:
    project_id = repository.spec.project
    managed = render(
        "project.md.j2",
        {
            "repository": repository,
            "experiments": experiments,
            "runs": runs,
            "components": components,
            "project_uri": lab_uri(project_id),
        },
    )
    frontmatter = {
        "type": "project",
        "project_id": str(project_id),
        "name": repository.metadata.name,
        "project_uri": lab_uri(project_id),
        "experiments": len(experiments),
        "runs": len(runs),
        "managed_by": MANAGED_BY,
    }
    override = (
        repository.spec.obsidian.project_note if repository.spec.obsidian else None
    )
    return _write(
        write,
        vault.project_note(project_id, override),
        frontmatter=frontmatter,
        managed=managed,
        title=f"{project_id}: {repository.metadata.name}",
        human_placeholder=PROJECT_PLACEHOLDER,
    )


def _write(
    write: NoteWriter,
    path: Path,
    *,
    frontmatter: dict[str, Any],
    managed: str,
    title: str,
    human_placeholder: str,
) -> dict[str, str]:
    """Write a note, after checking that nothing secret is about to leave."""
    _refuse_secrets(managed, frontmatter, path)
    result = write(
        path,
        frontmatter=frontmatter,
        managed=managed,
        title=title,
        human_placeholder=human_placeholder,
    )
    note = {"path": str(result.path), "outcome": result.outcome.value}
    if result.sidecar is not None:
        note["sidecar"] = str(result.sidecar)
    if result.reason is not None:
        note["reason"] = result.reason
    return note


def _refuse_secrets(managed: str, frontmatter: dict[str, Any], path: Path) -> None:
    """The vault must never contain secrets (AGENTS.md section 12.3)."""
    rendered_frontmatter = "\n".join(
        f"{key}: {value}" for key, value in frontmatter.items()
    )
    for text in (managed, rendered_frontmatter):
        if find_secrets(text):
            raise StateStoreError(
                f"Refusing to write {path}: the generated note looks like it "
                "contains a secret."
            )


def _duration(run: RunRecord) -> str:
    if run.started_at is None or run.completed_at is None:
        return "not measured"
    seconds = (run.completed_at - run.started_at).total_seconds()
    if seconds < 60:
        return f"{seconds:.2f} s"
    minutes, remainder = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {remainder}s" if hours else f"{minutes}m {remainder}s"


def _reproduction(run: RunRecord) -> str:
    parts = ["lab run", f"--experiment {run.experiment_id}", f"--backend {run.backend}"]
    if not run.container.digest:
        parts.append("--no-container")
    return " ".join(parts)
