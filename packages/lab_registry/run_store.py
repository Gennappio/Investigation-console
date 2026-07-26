"""File-backed run and test-evidence store (see ADR 0005).

One JSON document per run under ``$LAB_HOME/runs``. Saving a run that already
exists is checked against the immutability rules of AGENTS.md section 2.3
before anything is written.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from lab_domain.errors import NotFoundError, StateStoreError
from lab_domain.ids import ExperimentId, ProjectId, RunId
from lab_domain.registry import IdAllocator
from lab_domain.runs import RunRecord, ensure_amendable
from lab_domain.suites import SuiteResult
from lab_registry.files import write_atomically

RUNS_DIRECTORY = "runs"
TESTS_DIRECTORY = "tests"


class FileRunStore:
    """``RunStore`` backed by ``$LAB_HOME``."""

    def __init__(self, home: Path, allocator: IdAllocator) -> None:
        self._runs = home / RUNS_DIRECTORY
        self._tests = home / TESTS_DIRECTORY
        self._allocator = allocator

    def allocate_run_id(self) -> RunId:
        return self._allocator.allocate_run_id()

    def save_run(self, record: RunRecord) -> None:
        path = self._runs / f"{record.id}.json"
        if path.exists():
            ensure_amendable(self._load_run(path), record)
        write_atomically(path, record.model_dump_json(indent=2) + "\n")

    def get_run(self, run_id: RunId) -> RunRecord:
        path = self._runs / f"{run_id}.json"
        if not path.exists():
            raise NotFoundError(f"No run {run_id} recorded in {self._runs}.")
        return self._load_run(path)

    def list_runs(
        self, experiment_id: ExperimentId | None = None
    ) -> tuple[RunRecord, ...]:
        if not self._runs.is_dir():
            return ()
        records = [
            self._load_run(path) for path in sorted(self._runs.glob("RUN-*.json"))
        ]
        if experiment_id is not None:
            records = [r for r in records if r.experiment_id == experiment_id]
        return tuple(records)

    def save_test_result(self, result: SuiteResult) -> None:
        stamp = result.started_at.strftime("%Y%m%dT%H%M%S%f")
        path = self._tests / result.project_id / f"{result.suite.value}-{stamp}.json"
        write_atomically(path, result.model_dump_json(indent=2) + "\n")

    def list_test_results(self, project_id: ProjectId) -> tuple[SuiteResult, ...]:
        directory = self._tests / project_id
        if not directory.is_dir():
            return ()
        results = []
        for path in sorted(directory.glob("*.json")):
            try:
                results.append(
                    SuiteResult.model_validate_json(path.read_text(encoding="utf-8"))
                )
            except (OSError, ValidationError) as exc:
                raise StateStoreError(
                    f"Test result {path} is unreadable: {exc}."
                ) from exc
        return tuple(sorted(results, key=lambda r: r.started_at))

    def _load_run(self, path: Path) -> RunRecord:
        try:
            return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise StateStoreError(f"Run record {path} is unreadable: {exc}.") from exc
