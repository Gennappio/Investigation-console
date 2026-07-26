"""File-backed component registry and decision log (see ADR 0005).

One document per published version under ``$LAB_HOME/components``, one per
decision under ``$LAB_HOME/decisions``. A published version is never rewritten
in place: the publish service compares content and refuses a silent change.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from lab_domain.components import ComponentRecord, DecisionRecord
from lab_domain.errors import NotFoundError, StateStoreError
from lab_domain.ids import ComponentId, DecisionId, ProjectId
from lab_domain.registry import IdAllocator
from lab_registry.files import write_atomically

COMPONENTS_DIRECTORY = "components"
DECISIONS_DIRECTORY = "decisions"


class FileComponentStore:
    """``ComponentStore`` backed by ``$LAB_HOME``."""

    def __init__(self, home: Path, allocator: IdAllocator) -> None:
        self._components = home / COMPONENTS_DIRECTORY
        self._decisions = home / DECISIONS_DIRECTORY
        self._allocator = allocator

    def allocate_component_id(self) -> ComponentId:
        return self._allocator.allocate_component_id()

    def allocate_decision_id(self) -> DecisionId:
        return self._allocator.allocate_decision_id()

    def save_component(self, record: ComponentRecord) -> None:
        write_atomically(
            self._components / f"{record.id}-{record.version}.json",
            record.model_dump_json(indent=2) + "\n",
        )

    def get_component(
        self, component_id: ComponentId, version: str | None = None
    ) -> ComponentRecord:
        versions = [r for r in self.list_components() if r.id == component_id]
        if not versions:
            raise NotFoundError(f"No component {component_id} in {self._components}.")
        if version is None:
            return max(
                versions, key=lambda r: (_version_key(r.version), r.published_at)
            )
        for record in versions:
            if record.version == version:
                return record
        known = ", ".join(sorted(r.version for r in versions))
        raise NotFoundError(
            f"Component {component_id} has no version {version}. Published: {known}."
        )

    def find_by_name(
        self, project_id: ProjectId, name: str
    ) -> tuple[ComponentRecord, ...]:
        return tuple(
            record
            for record in self.list_components()
            if record.project_id == project_id and record.name == name
        )

    def list_components(self) -> tuple[ComponentRecord, ...]:
        if not self._components.is_dir():
            return ()
        records = [
            self._load(path, ComponentRecord)
            for path in sorted(self._components.glob("CMP-*.json"))
        ]
        return tuple(records)

    def save_decision(self, decision: DecisionRecord) -> None:
        write_atomically(
            self._decisions / f"{decision.id}.json",
            decision.model_dump_json(indent=2) + "\n",
        )

    def list_decisions(
        self, component_id: ComponentId | None = None
    ) -> tuple[DecisionRecord, ...]:
        if not self._decisions.is_dir():
            return ()
        decisions = [
            self._load(path, DecisionRecord)
            for path in sorted(self._decisions.glob("DEC-*.json"))
        ]
        if component_id is not None:
            decisions = [d for d in decisions if d.component_id == component_id]
        return tuple(sorted(decisions, key=lambda d: d.decided_at))

    def _load[RecordT: (ComponentRecord, DecisionRecord)](
        self, path: Path, model: type[RecordT]
    ) -> RecordT:
        try:
            return model.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise StateStoreError(f"Record {path} is unreadable: {exc}.") from exc


def _version_key(version: str) -> tuple[int, ...]:
    """Order versions numerically, so 1.10.0 comes after 1.9.0."""
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:  # pragma: no cover - the manifest pattern prevents this
        return (0,)
