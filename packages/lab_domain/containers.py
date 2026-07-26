"""Container port (AGENTS.md section 9). Docker and Apptainer implement it."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class ContainerModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class ImageInfo(ContainerModel):
    """An image, pinned by digest rather than by a mutable tag."""

    reference: str
    digest: str | None = None


class BuildRequest(ContainerModel):
    context: Path
    dockerfile: Path
    tag: str


class BuildOutcome(ContainerModel):
    image: ImageInfo
    log: str


class Mount(ContainerModel):
    source: Path
    target: str
    read_only: bool = True


class ContainerRunSpec(ContainerModel):
    image: str
    digest: str | None = None
    workdir: str = "/workspace"
    mounts: tuple[Mount, ...] = ()
    environment: dict[str, str] = {}
    # Execution containers have no network unless a run explicitly asks for it
    # and the request is recorded (AGENTS.md section 9.3).
    network: bool = False

    @property
    def pinned_reference(self) -> str:
        """The digest-pinned image where known, so a run is reproducible."""
        if self.digest and self.digest.startswith("sha256:"):
            repository = self.image.split(":")[0]
            return f"{repository}@{self.digest}"
        return self.image


class ContainerEngine(Protocol):
    def available(self) -> bool: ...

    def build(self, request: BuildRequest) -> BuildOutcome: ...

    def inspect(self, reference: str) -> ImageInfo: ...

    def wrap(self, spec: ContainerRunSpec, argv: Sequence[str]) -> tuple[str, ...]: ...
