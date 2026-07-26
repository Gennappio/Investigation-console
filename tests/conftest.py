from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from lab_domain.runs import CodeRef, ContainerRef, ResourceRequest, RunRecord, RunStatus

FIXTURE_MANIFESTS = Path(__file__).parent / "fixtures" / "manifests"


@pytest.fixture
def manifests() -> Path:
    """Directory holding the hand-written manifest fixtures."""
    return FIXTURE_MANIFESTS


@pytest.fixture
def lab_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate platform state so tests never touch the real ~/.lab."""
    home = tmp_path / "lab-home"
    monkeypatch.setenv("LAB_HOME", str(home))
    return home


@pytest.fixture
def make_run() -> Callable[..., RunRecord]:
    """Build a run record; pass field overrides as keyword arguments."""

    def build(status: RunStatus = RunStatus.CREATED, **changes: Any) -> RunRecord:
        base: dict[str, Any] = {
            "id": "RUN-000001",
            "experiment_id": "EXP-000001",
            "project_id": "PRJ-000001",
            "status": status,
            "backend": "local",
            "code": CodeRef(commit="a91bd29"),
            "container": ContainerRef(image="lab/demo:1", digest="sha256:abc"),
            "datasets": (),
            "configuration_hash": "sha256:deadbeef",
            "parameters": {"repetitions": 2},
            "seeds": (101,),
            "resources": ResourceRequest(cpus=1, memory_mb=1024, time_limit="00:10:00"),
            "command": ("python", "-m", "demo.run"),
            "submitted_by": "anna.rossi",
            "created_at": datetime(2026, 7, 26, tzinfo=UTC),
        }
        return RunRecord.model_validate({**base, **changes})

    return build


@pytest.fixture
def workspace_factory(tmp_path: Path) -> Iterator[Callable[..., Path]]:
    """Build a workspace directory from fixture manifests."""

    counter = 0

    def build(repository: str = "valid_lab.yaml", *experiments: str) -> Path:
        nonlocal counter
        counter += 1
        root = tmp_path / f"workspace-{counter}"
        (root / "experiments").mkdir(parents=True)
        (root / "lab.yaml").write_text((FIXTURE_MANIFESTS / repository).read_text())
        for name in experiments:
            (root / "experiments" / name).write_text(
                (FIXTURE_MANIFESTS / name).read_text()
            )
        return root

    yield build
