"""Apptainer runs images on cluster nodes; these tests need no cluster."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from lab_containers.apptainer_engine import ApptainerEngine

from lab_domain.containers import BuildRequest, ContainerEngine, ContainerRunSpec, Mount
from lab_domain.errors import DependencyError


@dataclass
class FakeApptainer:
    result: tuple[int, str, str] = (0, "apptainer version 1.2.5\n", "")
    calls: list[list[str]] = field(default_factory=list)

    def __call__(
        self, argv: Sequence[str], *, timeout: int | None = None
    ) -> FakeResult:
        self.calls.append(list(argv))
        return FakeResult(*self.result)


@dataclass
class FakeResult:
    returncode: int
    stdout: str
    stderr: str


def test_satisfies_the_container_port() -> None:
    engine: ContainerEngine = ApptainerEngine(runner=FakeApptainer())
    assert engine.available() is True


def test_unavailable_when_apptainer_is_missing() -> None:
    def missing(argv: Sequence[str], *, timeout: int | None = None) -> FakeResult:
        raise DependencyError("apptainer is not installed or not on PATH.")

    assert ApptainerEngine(runner=missing).available() is False


def test_building_points_at_the_docker_path(tmp_path: Path) -> None:
    engine = ApptainerEngine(runner=FakeApptainer())
    with pytest.raises(DependencyError, match="lab build"):
        engine.build(
            BuildRequest(
                context=tmp_path, dockerfile=tmp_path / "Dockerfile", tag="x:1"
            )
        )


def test_inspect_reports_the_pinned_digest() -> None:
    engine = ApptainerEngine(runner=FakeApptainer())
    assert engine.inspect("lab/demo@sha256:abcdef").digest == "sha256:abcdef"
    assert engine.inspect("lab/demo:1.0.0").digest is None


def test_run_argv_isolates_the_container(tmp_path: Path) -> None:
    engine = ApptainerEngine(runner=FakeApptainer())
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

    assert argv[:2] == ("apptainer", "exec")
    assert "--containall" in argv and "--no-home" in argv
    assert argv[argv.index("--network") + 1] == "none"
    assert f"{tmp_path / 'project'}:/workspace:ro" in argv
    assert f"{tmp_path / 'scratch'}:/scratch:rw" in argv
    assert "LAB_RUN_ID=RUN-000001" in argv
    assert argv[-4:] == (
        "docker://lab/demo@sha256:abcdef",
        "python",
        "-m",
        "demo.run",
    )


def test_network_is_opt_in() -> None:
    engine = ApptainerEngine(runner=FakeApptainer())
    argv = engine.wrap(ContainerRunSpec(image="x:1", network=True), ["echo"])
    assert "--network" not in argv


def test_an_image_file_is_used_as_written() -> None:
    engine = ApptainerEngine(runner=FakeApptainer())
    argv = engine.wrap(ContainerRunSpec(image="/shared/images/demo.sif"), ["echo"])
    assert argv[-2] == "/shared/images/demo.sif"
