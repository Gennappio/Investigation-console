"""Summary of a managed repository (`lab inspect`)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lab_domain.errors import WorkspaceNotFoundError
from lab_domain.ids import ExperimentId, ProjectId
from lab_domain.manifests.models import RuntimeSpec
from lab_domain.services.validate_service import load_workspace_docs
from lab_domain.workspace import MANIFEST_NAME


class ExperimentSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: ExperimentId
    title: str
    owner: str
    file: str


class WorkspaceInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    root: str
    name: str
    description: str | None
    project_id: ProjectId
    owners: tuple[str, ...]
    runtime: RuntimeSpec
    commands: dict[str, tuple[str, ...]]
    outputs_directory: str | None
    experiments: tuple[ExperimentSummary, ...]


def inspect_workspace(root: Path) -> WorkspaceInfo:
    """Describe the repository at ``root``.

    Raises ``WorkspaceNotFoundError`` when ``lab.yaml`` cannot be parsed: there
    is nothing to describe, and `lab validate` reports exactly why.
    """
    docs, _ = load_workspace_docs(root)
    if docs.repository is None:
        raise WorkspaceNotFoundError(
            f"Cannot read {root / MANIFEST_NAME}. Run `lab validate` for details."
        )

    repository = docs.repository
    return WorkspaceInfo(
        root=str(root),
        name=repository.metadata.name,
        description=repository.metadata.description,
        project_id=repository.spec.project,
        owners=repository.metadata.owners,
        runtime=repository.spec.runtime,
        commands=repository.spec.commands,
        outputs_directory=(
            repository.spec.outputs.directory if repository.spec.outputs else None
        ),
        experiments=tuple(
            ExperimentSummary(
                id=doc.manifest.metadata.id,
                title=doc.manifest.metadata.title,
                owner=doc.manifest.metadata.owner,
                file=doc.file,
            )
            for doc in docs.experiments
        ),
    )
