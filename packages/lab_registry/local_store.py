"""File-backed registry for local development (see ADR 0003).

State lives in a single JSON document under ``$LAB_HOME`` and is rewritten
atomically. This is the Milestone 1 stand-in for the operational database.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from lab_domain.errors import StateStoreError
from lab_domain.ids import ExperimentId, ProjectId, TypedId
from lab_domain.registry import ProjectRecord

STATE_FILENAME = "registry.json"
SCHEMA_VERSION = 1


class RegistryState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    counters: dict[str, int] = {}
    projects: list[ProjectRecord] = []


class LocalRegistry:
    """``ProjectRegistry`` backed by ``$LAB_HOME/registry.json``."""

    def __init__(self, home: Path) -> None:
        self._home = home
        self._state_path = home / STATE_FILENAME

    @property
    def state_path(self) -> Path:
        return self._state_path

    def allocate_project_id(self) -> ProjectId:
        return self._allocate(ProjectId)

    def allocate_experiment_id(self) -> ExperimentId:
        return self._allocate(ExperimentId)

    def register_project(self, record: ProjectRecord) -> None:
        state = self._read()
        state.projects.append(record)
        self._write(state)

    def list_projects(self) -> tuple[ProjectRecord, ...]:
        return tuple(self._read().projects)

    def _allocate[IdT: TypedId](self, id_type: type[IdT]) -> IdT:
        state = self._read()
        next_value = state.counters.get(id_type.prefix, 0) + 1
        state.counters[id_type.prefix] = next_value
        self._write(state)
        return id_type.from_int(next_value)

    def _read(self) -> RegistryState:
        if not self._state_path.exists():
            return RegistryState()
        try:
            return RegistryState.model_validate_json(
                self._state_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, ValidationError) as exc:
            raise StateStoreError(
                f"Platform state at {self._state_path} is unreadable: {exc}. "
                "Fix or remove the file, then retry."
            ) from exc

    def _write(self, state: RegistryState) -> None:
        payload = state.model_dump_json(indent=2) + "\n"
        try:
            self._home.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self._home,
                prefix=f".{STATE_FILENAME}.",
                delete=False,
            ) as handle:
                handle.write(payload)
                temporary = Path(handle.name)
            os.replace(temporary, self._state_path)
        except OSError as exc:
            raise StateStoreError(
                f"Cannot write platform state to {self._state_path}: {exc.strerror}."
            ) from exc


def utc_now() -> datetime:
    """Current time in UTC (AGENTS.md section 16.1)."""
    return datetime.now(UTC)
