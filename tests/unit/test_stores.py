from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from lab_artifacts.filesystem_store import FilesystemArtifactStore, checksum_of

from lab_domain.artifacts import ArtifactKind
from lab_domain.errors import (
    CollectionFailedError,
    ImmutableRunError,
    NotFoundError,
    StateStoreError,
)
from lab_domain.runs import RunRecord, RunStatus
from lab_domain.storage import ArtifactStore, RunStore
from lab_domain.suites import CheckStatus, SuiteKind, SuiteResult
from lab_registry.audit import AuditLog
from lab_registry.local_store import LocalRegistry
from lab_registry.run_store import FileRunStore

RunFactory = Callable[..., RunRecord]


@pytest.fixture
def store(tmp_path: Path) -> FileRunStore:
    return FileRunStore(tmp_path / "home", LocalRegistry(tmp_path / "home"))


@pytest.fixture
def artifacts(tmp_path: Path) -> FilesystemArtifactStore:
    return FilesystemArtifactStore(
        tmp_path / "artifacts", LocalRegistry(tmp_path / "home")
    )


def test_stores_satisfy_their_ports(
    store: FileRunStore, artifacts: FilesystemArtifactStore
) -> None:
    run_store: RunStore = store
    artifact_store: ArtifactStore = artifacts
    assert run_store.list_runs() == ()
    assert run_store.allocate_run_id() == "RUN-000001"
    assert artifact_store.allocate_artifact_id() == "ART-000001"


def test_saves_and_reloads_a_run(store: FileRunStore, make_run: RunFactory) -> None:
    record = make_run()
    store.save_run(record)
    assert store.get_run(record.id) == record
    assert store.list_runs() == (record,)


def test_missing_run_is_reported(store: FileRunStore) -> None:
    with pytest.raises(NotFoundError, match="RUN-000404"):
        store.get_run("RUN-000404")


def test_runs_can_be_filtered_by_experiment(
    store: FileRunStore, make_run: RunFactory
) -> None:
    store.save_run(make_run())
    store.save_run(make_run(id="RUN-000002", experiment_id="EXP-000002"))
    assert [r.id for r in store.list_runs("EXP-000002")] == ["RUN-000002"]


def test_saving_progress_is_allowed(store: FileRunStore, make_run: RunFactory) -> None:
    record = make_run(RunStatus.QUEUED)
    store.save_run(record)
    store.save_run(record.transitioned_to(RunStatus.RUNNING))
    assert store.get_run(record.id).status is RunStatus.RUNNING


def test_rewriting_history_is_refused(
    store: FileRunStore, make_run: RunFactory
) -> None:
    record = make_run(RunStatus.RUNNING)
    store.save_run(record)
    with pytest.raises(ImmutableRunError, match="parameters"):
        store.save_run(record.model_copy(update={"parameters": {"repetitions": 99}}))
    assert store.get_run(record.id).parameters == {"repetitions": 2}


def test_corrupt_run_record_is_reported(
    store: FileRunStore, make_run: RunFactory, tmp_path: Path
) -> None:
    store.save_run(make_run())
    (tmp_path / "home" / "runs" / "RUN-000001.json").write_text("{oops")
    with pytest.raises(StateStoreError, match="unreadable"):
        store.get_run("RUN-000001")


def test_test_results_are_recorded_per_project(store: FileRunStore) -> None:
    result = SuiteResult(
        project_id="PRJ-000001",
        suite=SuiteKind.INTEGRATION,
        profile="smoke",
        status=CheckStatus.PASSED,
        command=("pytest", "-q"),
        exit_code=0,
        started_at=datetime(2026, 7, 26, tzinfo=UTC),
        completed_at=datetime(2026, 7, 26, 0, 1, tzinfo=UTC),
    )
    store.save_test_result(result)
    assert store.list_test_results("PRJ-000001") == (result,)
    assert store.list_test_results("PRJ-000002") == ()


def test_artifacts_are_copied_checksummed_and_indexed(
    artifacts: FilesystemArtifactStore, tmp_path: Path
) -> None:
    source = tmp_path / "summary.json"
    source.write_text('{"status": "ok"}')

    record = artifacts.store(source, kind=ArtifactKind.RESULT, run_id="RUN-000001")

    assert record.id == "ART-000001"
    assert record.name == "summary.json"
    assert record.media_type == "application/json"
    assert record.size_bytes == source.stat().st_size
    assert record.checksum == checksum_of(source)
    assert record.uri.startswith("file://")
    stored = artifacts.resolve(record)
    assert stored.read_text() == source.read_text()
    assert artifacts.list_artifacts("RUN-000001") == (record,)


def test_artifacts_survive_a_new_store_instance(
    artifacts: FilesystemArtifactStore, tmp_path: Path
) -> None:
    source = tmp_path / "a.log"
    source.write_text("log")
    artifacts.store(source, kind=ArtifactKind.LOG, run_id="RUN-000001")
    reopened = FilesystemArtifactStore(artifacts.root, LocalRegistry(tmp_path / "home"))
    assert [r.name for r in reopened.list_artifacts("RUN-000001")] == ["a.log"]


def test_artifacts_without_a_run_are_supported(
    artifacts: FilesystemArtifactStore, tmp_path: Path
) -> None:
    source = tmp_path / "build.log"
    source.write_text("Successfully built")
    record = artifacts.store(source, kind=ArtifactKind.BUILD_LOG)
    assert record.run_id is None
    assert artifacts.resolve(record).is_file()


def test_storing_a_missing_file_is_reported(
    artifacts: FilesystemArtifactStore, tmp_path: Path
) -> None:
    with pytest.raises(CollectionFailedError, match="not a readable file"):
        artifacts.store(tmp_path / "absent", kind=ArtifactKind.RESULT)


def test_audit_log_is_append_only(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "home")
    log.record("run.created", actor="anna.rossi", run_id="RUN-000001")
    log.record(
        "run.submitted", actor="anna.rossi", run_id="RUN-000001", backend="local"
    )
    entries = log.entries()
    assert [e["action"] for e in entries] == ["run.created", "run.submitted"]
    assert entries[1]["backend"] == "local"
    assert all("at" in entry for entry in entries)
