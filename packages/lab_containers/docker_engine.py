"""Docker implementation of the container port (AGENTS.md section 9).

Every invocation goes through the CLI as an argument list, never a shell, and
machine-readable output is requested wherever Docker offers it. The command
runner is injected so the argument lists can be tested without a daemon.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from lab_execution.process import CommandRunner, subprocess_runner

from lab_domain.containers import (
    BuildOutcome,
    BuildRequest,
    ContainerRunSpec,
    ImageInfo,
)
from lab_domain.errors import BuildFailedError, DependencyError

DOCKER = "docker"
AVAILABILITY_TIMEOUT_SECONDS = 20


class DockerEngine:
    """``ContainerEngine`` driving the ``docker`` command-line client."""

    def __init__(self, runner: CommandRunner = subprocess_runner) -> None:
        self._run = runner

    def available(self) -> bool:
        """Whether the daemon answers.

        ``docker version`` is the probe rather than ``docker info``: the latter
        exits 0 with an empty result when the daemon is unreachable.
        """
        try:
            result = self._run(
                [DOCKER, "version", "--format", "{{.Server.Version}}"],
                timeout=AVAILABILITY_TIMEOUT_SECONDS,
            )
        except DependencyError:
            return False
        return result.returncode == 0 and bool(result.stdout.strip())

    def build(self, request: BuildRequest) -> BuildOutcome:
        self._require_daemon()
        argv = [
            DOCKER,
            "build",
            "--file",
            str(request.dockerfile),
            "--tag",
            request.tag,
            str(request.context),
        ]
        result = self._run(argv)
        log = result.stdout + result.stderr
        if result.returncode != 0:
            raise BuildFailedError(
                f"docker build failed with exit code {result.returncode}. "
                f"Last output: {_tail(log)}"
            )
        return BuildOutcome(image=self.inspect(request.tag), log=log)

    def inspect(self, reference: str) -> ImageInfo:
        self._require_daemon()
        result = self._run(
            [DOCKER, "image", "inspect", reference, "--format", "{{json .}}"]
        )
        if result.returncode != 0:
            raise DependencyError(
                f"Image {reference} is not available locally: "
                f"{_tail(result.stderr)}. Run `lab build` first."
            )
        return ImageInfo(reference=reference, digest=_digest_of(result.stdout))

    def wrap(self, spec: ContainerRunSpec, argv: Sequence[str]) -> tuple[str, ...]:
        """Argument list that runs ``argv`` inside the image."""
        wrapped = [DOCKER, "run", "--rm"]
        if not spec.network:
            wrapped += ["--network", "none"]
        wrapped += ["--security-opt", "no-new-privileges"]
        for mount in spec.mounts:
            flags = ":ro" if mount.read_only else ""
            wrapped += [
                "--volume",
                f"{Path(mount.source).absolute()}:{mount.target}{flags}",
            ]
        for key, value in sorted(spec.environment.items()):
            wrapped += ["--env", f"{key}={value}"]
        wrapped += ["--workdir", spec.workdir]
        wrapped.append(spec.pinned_reference)
        wrapped += list(argv)
        return tuple(wrapped)

    def _require_daemon(self) -> None:
        if not self.available():
            raise DependencyError(
                "Docker is installed but the daemon is not reachable. Start "
                "Docker, or run without a container."
            )


def _digest_of(payload: str) -> str | None:
    """First repository digest reported by ``docker image inspect``."""
    try:
        document = json.loads(payload)
    except ValueError:
        return None
    digests = document.get("RepoDigests") or []
    if digests:
        _, _, digest = str(digests[0]).partition("@")
        return digest or None
    image_id = document.get("Id")
    return str(image_id) if image_id else None


def _tail(text: str, lines: int = 5) -> str:
    return " / ".join(text.strip().splitlines()[-lines:]) or "no output"
