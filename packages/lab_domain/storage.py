"""Storage ports: where runs, artifacts and test evidence are kept.

Implementations live in ``lab_registry`` and ``lab_artifacts``. The operational
database replaces the file-backed ones without touching services (ADR 0005).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from lab_domain.artifacts import ArtifactKind, ArtifactRecord
from lab_domain.components import ComponentRecord, DecisionRecord
from lab_domain.ids import (
    ArtifactId,
    ComponentId,
    DecisionId,
    ExperimentId,
    ProjectId,
    RunId,
)
from lab_domain.runs import RunRecord
from lab_domain.suites import SuiteResult


class RunStore(Protocol):
    def allocate_run_id(self) -> RunId: ...

    def save_run(self, record: RunRecord) -> None: ...

    def get_run(self, run_id: RunId) -> RunRecord: ...

    def list_runs(
        self, experiment_id: ExperimentId | None = None
    ) -> tuple[RunRecord, ...]: ...

    def save_test_result(self, result: SuiteResult) -> None: ...

    def list_test_results(self, project_id: ProjectId) -> tuple[SuiteResult, ...]: ...


class ComponentStore(Protocol):
    def allocate_component_id(self) -> ComponentId: ...

    def allocate_decision_id(self) -> DecisionId: ...

    def save_component(self, record: ComponentRecord) -> None: ...

    def get_component(
        self, component_id: ComponentId, version: str | None = None
    ) -> ComponentRecord: ...

    def find_by_name(
        self, project_id: ProjectId, name: str
    ) -> tuple[ComponentRecord, ...]: ...

    def list_components(self) -> tuple[ComponentRecord, ...]: ...

    def save_decision(self, decision: DecisionRecord) -> None: ...

    def list_decisions(
        self, component_id: ComponentId | None = None
    ) -> tuple[DecisionRecord, ...]: ...


class ArtifactStore(Protocol):
    def allocate_artifact_id(self) -> ArtifactId: ...

    def store(
        self,
        source: Path,
        *,
        kind: ArtifactKind,
        run_id: RunId | None = None,
        name: str | None = None,
    ) -> ArtifactRecord: ...

    def list_artifacts(self, run_id: RunId) -> tuple[ArtifactRecord, ...]: ...

    def resolve(self, record: ArtifactRecord) -> Path: ...
