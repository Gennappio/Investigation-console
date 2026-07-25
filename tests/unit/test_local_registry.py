from __future__ import annotations

import json
from pathlib import Path

import pytest

from lab_domain.errors import StateStoreError
from lab_domain.registry import ProjectRecord, ProjectRegistry
from lab_registry.local_store import LocalRegistry, utc_now


def test_satisfies_the_registry_protocol(tmp_path: Path) -> None:
    registry: ProjectRegistry = LocalRegistry(tmp_path / "home")
    assert registry.list_projects() == ()


def test_allocates_sequentially_per_prefix(tmp_path: Path) -> None:
    registry = LocalRegistry(tmp_path / "home")
    assert registry.allocate_project_id() == "PRJ-000001"
    assert registry.allocate_project_id() == "PRJ-000002"
    assert registry.allocate_experiment_id() == "EXP-000001"


def test_state_survives_a_new_instance(tmp_path: Path) -> None:
    home = tmp_path / "home"
    LocalRegistry(home).allocate_project_id()
    assert LocalRegistry(home).allocate_project_id() == "PRJ-000002"


def test_registers_and_lists_projects(tmp_path: Path) -> None:
    registry = LocalRegistry(tmp_path / "home")
    project_id = registry.allocate_project_id()
    record = ProjectRecord(
        id=project_id, name="demo", path=str(tmp_path / "demo"), created_at=utc_now()
    )
    registry.register_project(record)
    assert registry.list_projects() == (record,)


def test_writes_are_atomic_leaving_no_partial_files(tmp_path: Path) -> None:
    home = tmp_path / "home"
    registry = LocalRegistry(home)
    registry.allocate_project_id()
    assert [p.name for p in home.iterdir()] == ["registry.json"]
    state = json.loads(registry.state_path.read_text())
    assert state["schema_version"] == 1
    assert state["counters"] == {"PRJ": 1}


def test_corrupt_state_is_reported(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "registry.json").write_text("{not json")
    with pytest.raises(StateStoreError, match="unreadable"):
        LocalRegistry(home).allocate_project_id()


def test_unwritable_home_is_reported(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.mkdir(mode=0o500)
    with pytest.raises(StateStoreError, match="Cannot write platform state"):
        LocalRegistry(blocked / "home").allocate_project_id()
