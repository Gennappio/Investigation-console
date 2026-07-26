"""Apptainer implementation of the container port, for HPC execution.

Clusters rarely allow a Docker daemon, so images are built with Docker, pushed
to a registry, and executed on the cluster by Apptainer. This engine therefore
runs images but does not build them: `lab build` is the Docker path.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from lab_execution.process import CommandRunner, subprocess_runner

from lab_domain.containers import (
    BuildOutcome,
    BuildRequest,
    ContainerRunSpec,
    ImageInfo,
)
from lab_domain.errors import DependencyError

APPTAINER = "apptainer"
DOCKER_URI_PREFIX = "docker://"
AVAILABILITY_TIMEOUT_SECONDS = 20


class ApptainerEngine:
    """``ContainerEngine`` driving the ``apptainer`` command-line client."""

    def __init__(self, runner: CommandRunner = subprocess_runner) -> None:
        self._run = runner

    def available(self) -> bool:
        try:
            result = self._run(
                [APPTAINER, "--version"], timeout=AVAILABILITY_TIMEOUT_SECONDS
            )
        except DependencyError:
            return False
        return result.returncode == 0

    def build(self, request: BuildRequest) -> BuildOutcome:
        raise DependencyError(
            "Apptainer does not build images here. Build with `lab build` "
            "(Docker), publish the image, and the cluster will run it."
        )

    def inspect(self, reference: str) -> ImageInfo:
        """Report what an image reference resolves to.

        Apptainer pulls from a registry at run time, so an image is described by
        the reference it was pinned to rather than by a local daemon lookup.
        """
        digest = reference.partition("@")[2] or None
        return ImageInfo(reference=reference, digest=digest)

    def wrap(self, spec: ContainerRunSpec, argv: Sequence[str]) -> tuple[str, ...]:
        """Argument list that runs ``argv`` inside the image on a cluster node."""
        wrapped = [APPTAINER, "exec"]
        # --containall isolates the container from the user's home and session;
        # without it an experiment silently picks up whatever is in $HOME.
        wrapped += ["--containall", "--no-home"]
        if not spec.network:
            wrapped.append("--net")
            wrapped += ["--network", "none"]
        for mount in spec.mounts:
            flags = ":ro" if mount.read_only else ":rw"
            wrapped += [
                "--bind",
                f"{Path(mount.source).absolute()}:{mount.target}{flags}",
            ]
        for key, value in sorted(spec.environment.items()):
            wrapped += ["--env", f"{key}={value}"]
        wrapped += ["--pwd", spec.workdir]
        wrapped.append(_image_uri(spec))
        wrapped += list(argv)
        return tuple(wrapped)


def _image_uri(spec: ContainerRunSpec) -> str:
    """Apptainer addresses registry images with a docker:// URI."""
    reference = spec.pinned_reference
    if "://" in reference or reference.endswith(".sif"):
        return reference
    return f"{DOCKER_URI_PREFIX}{reference}"
