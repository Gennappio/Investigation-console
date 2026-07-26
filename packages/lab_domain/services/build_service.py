"""Container image builds (`lab build`, AGENTS.md section 9.2)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lab_domain.artifacts import ArtifactKind
from lab_domain.containers import BuildRequest, ContainerEngine
from lab_domain.errors import ManifestInvalidError
from lab_domain.ids import ArtifactId
from lab_domain.services.workspace_context import WorkspaceContext, describe_code
from lab_domain.storage import ArtifactStore

DEVELOPMENT_TAG = "dev"


class BuildSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    image: str
    digest: str | None
    build_log_artifact: ArtifactId


def image_tag(context: WorkspaceContext) -> str:
    """Tag derived from the repository name and the commit being built.

    A commit-derived tag keeps images traceable; the digest recorded next to it
    is what a run actually pins to (AGENTS.md section 9.1).
    """
    commit = describe_code(context.root).commit
    version = commit[:12] if commit else DEVELOPMENT_TAG
    return f"lab/{context.repository.metadata.name}:{version}"


def build_image(
    context: WorkspaceContext,
    engine: ContainerEngine,
    artifacts: ArtifactStore,
    tag: str | None = None,
) -> BuildSummary:
    """Build the image the repository declares and record its digest."""
    container = context.repository.spec.container
    if container is None:
        raise ManifestInvalidError(
            f"{context.repository.metadata.name} declares no container. "
            "Add spec.container to lab.yaml before building."
        )

    dockerfile = context.root / container.dockerfile
    if not dockerfile.is_file():
        raise ManifestInvalidError(
            f"Dockerfile {container.dockerfile} does not exist in {context.root}."
        )

    reference = tag or image_tag(context)
    outcome = engine.build(
        BuildRequest(
            context=context.root / container.context,
            dockerfile=dockerfile,
            tag=reference,
        )
    )

    with tempfile.TemporaryDirectory() as scratch:
        log_path = Path(scratch) / "build.log"
        log_path.write_text(outcome.log, encoding="utf-8")
        log_artifact = artifacts.store(log_path, kind=ArtifactKind.BUILD_LOG)

    return BuildSummary(
        status="success",
        image=outcome.image.reference,
        digest=outcome.image.digest,
        build_log_artifact=log_artifact.id,
    )
