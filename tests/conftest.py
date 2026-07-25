from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

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
