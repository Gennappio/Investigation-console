"""Docker is driven through argument lists; these tests need no daemon."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from lab_containers.docker_engine import DockerEngine

from lab_domain.containers import (
    BuildRequest,
    ContainerEngine,
    ContainerRunSpec,
    Mount,
)
from lab_domain.errors import BuildFailedError, DependencyError

INSPECT_OUTPUT = json.dumps(
    {"Id": "sha256:image-id", "RepoDigests": ["lab/demo@sha256:abcdef"]}
)


@dataclass
class FakeDocker:
    """Records the argument lists and replays canned results."""

    results: dict[str, tuple[int, str, str]] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)

    def __call__(
        self, argv: Sequence[str], *, timeout: int | None = None
    ) -> FakeResult:
        self.calls.append(list(argv))
        key = " ".join(argv[1:3])
        code, out, err = self.results.get(key, (0, "", ""))
        return FakeResult(returncode=code, stdout=out, stderr=err)


@dataclass
class FakeResult:
    returncode: int
    stdout: str
    stderr: str


DAEMON_UP = {"version --format": (0, "24.0.6\n", "")}


def engine_with(
    results: dict[str, tuple[int, str, str]] | None = None,
) -> tuple[DockerEngine, FakeDocker]:
    """An engine whose docker calls are answered from a table.

    Keys are the first two docker arguments, e.g. ``"image inspect"``.
    """
    fake = FakeDocker(results={**DAEMON_UP, **(results or {})})
    return DockerEngine(runner=fake), fake


def test_satisfies_the_container_port() -> None:
    engine, _ = engine_with()
    port: ContainerEngine = engine
    assert port.available() is True


def test_availability_reflects_the_daemon() -> None:
    engine, _ = engine_with(
        {"version --format": (1, "", "Cannot connect to the daemon")}
    )
    assert engine.available() is False


def test_build_passes_dockerfile_context_and_tag(tmp_path: Path) -> None:
    engine, fake = engine_with({"image inspect": (0, INSPECT_OUTPUT, "")})
    outcome = engine.build(
        BuildRequest(
            context=tmp_path,
            dockerfile=tmp_path / "containers" / "Dockerfile",
            tag="lab/demo:1.0.0",
        )
    )
    build_call = next(call for call in fake.calls if call[1] == "build")
    assert build_call == [
        "docker",
        "build",
        "--file",
        str(tmp_path / "containers" / "Dockerfile"),
        "--tag",
        "lab/demo:1.0.0",
        str(tmp_path),
    ]
    assert outcome.image.digest == "sha256:abcdef"


def test_build_failure_is_reported_with_output(tmp_path: Path) -> None:
    engine, _ = engine_with({"build --file": (1, "", "step 3 failed\nno such file")})
    with pytest.raises(BuildFailedError, match="no such file"):
        engine.build(
            BuildRequest(
                context=tmp_path, dockerfile=tmp_path / "Dockerfile", tag="x:1"
            )
        )


def test_missing_image_points_at_lab_build() -> None:
    engine, _ = engine_with({"image inspect": (1, "", "No such image: lab/demo:1")})
    with pytest.raises(DependencyError, match="Run `lab build` first"):
        engine.inspect("lab/demo:1")


def test_build_without_a_daemon_is_a_dependency_error(tmp_path: Path) -> None:
    engine, _ = engine_with({"version --format": (1, "", "no daemon")})
    with pytest.raises(DependencyError, match="daemon is not reachable"):
        engine.build(
            BuildRequest(
                context=tmp_path, dockerfile=tmp_path / "Dockerfile", tag="x:1"
            )
        )


def test_daemon_reporting_no_server_version_is_unavailable() -> None:
    """`docker version` exits 0 with an empty server when the daemon is down."""
    engine, _ = engine_with({"version --format": (0, "\n", "cannot connect")})
    assert engine.available() is False


def test_inspect_falls_back_to_the_image_id() -> None:
    engine, _ = engine_with(
        {
            "image inspect": (
                0,
                json.dumps({"Id": "sha256:only-id", "RepoDigests": []}),
                "",
            )
        }
    )
    assert engine.inspect("lab/demo:1").digest == "sha256:only-id"


def test_run_argv_disables_network_and_pins_the_digest(tmp_path: Path) -> None:
    engine, _ = engine_with()
    spec = ContainerRunSpec(
        image="lab/demo:1.0.0",
        digest="sha256:abcdef",
        workdir="/scratch",
        mounts=(
            Mount(source=tmp_path / "project", target="/workspace"),
            Mount(source=tmp_path / "scratch", target="/scratch", read_only=False),
        ),
        environment={"LAB_RUN_ID": "RUN-000001"},
    )
    argv = engine.wrap(spec, ["python", "-m", "demo.run"])

    assert argv[:3] == ("docker", "run", "--rm")
    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert "no-new-privileges" in argv
    assert f"{tmp_path / 'project'}:/workspace:ro" in argv
    assert f"{tmp_path / 'scratch'}:/scratch" in argv
    assert "LAB_RUN_ID=RUN-000001" in argv
    assert argv[-4:] == ("lab/demo@sha256:abcdef", "python", "-m", "demo.run")


def test_network_is_opt_in() -> None:
    engine, _ = engine_with()
    argv = engine.wrap(ContainerRunSpec(image="x:1", network=True), ["echo"])
    assert "--network" not in argv


def test_unpinned_image_is_used_as_written() -> None:
    engine, _ = engine_with()
    argv = engine.wrap(ContainerRunSpec(image="lab/demo:1.0.0"), ["echo"])
    assert argv[-2] == "lab/demo:1.0.0"
