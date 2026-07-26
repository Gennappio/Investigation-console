"""Storage ports: where runs, artifacts and test evidence are kept.

Implementations live in ``lab_registry`` and ``lab_artifacts``. The operational
database replaces the file-backed ones without touching services (ADR 0005).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from lab_domain.artifacts import ArtifactKind, ArtifactRecord
from lab_domain.ids import ArtifactId, ExperimentId, ProjectId, RunId
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
