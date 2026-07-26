from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from lab_domain.errors import ImmutableRunError, InvalidTransitionError
from lab_domain.runs import RunRecord, RunStatus, configuration_hash, ensure_amendable

RunFactory = Callable[..., RunRecord]


def test_walks_the_documented_lifecycle(make_run: RunFactory) -> None:
    run = make_run()
    for status in (
        RunStatus.VALIDATED,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
        RunStatus.COMPLETED,
    ):
        run = run.transitioned_to(status)
    assert run.status is RunStatus.COMPLETED
    assert run.is_terminal


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunStatus.CREATED, RunStatus.RUNNING),
        (RunStatus.CREATED, RunStatus.COMPLETED),
        (RunStatus.QUEUED, RunStatus.COMPLETED),
        (RunStatus.COMPLETED, RunStatus.RUNNING),
        (RunStatus.FAILED, RunStatus.COMPLETED),
        (RunStatus.CANCELLED, RunStatus.RUNNING),
    ],
)
def test_rejects_impossible_transitions(
    make_run: RunFactory, current: RunStatus, target: RunStatus
) -> None:
    with pytest.raises(InvalidTransitionError, match="cannot move"):
        make_run(current).transitioned_to(target)


@pytest.mark.parametrize("status", [RunStatus.CANCELLED, RunStatus.FAILED])
def test_running_runs_can_fail_or_be_cancelled(
    make_run: RunFactory, status: RunStatus
) -> None:
    assert make_run(RunStatus.RUNNING).transitioned_to(status).status is status


def test_transitions_carry_execution_details(make_run: RunFactory) -> None:
    started = make_run(RunStatus.QUEUED).transitioned_to(
        RunStatus.RUNNING, started_at=datetime(2026, 7, 26, 1, tzinfo=UTC)
    )
    assert started.started_at is not None
    finished = started.transitioned_to(RunStatus.COMPLETED, exit_code=0)
    assert finished.exit_code == 0


def test_transitions_cannot_rewrite_provenance(make_run: RunFactory) -> None:
    with pytest.raises(ImmutableRunError, match="configuration_hash"):
        make_run().transitioned_to(
            RunStatus.VALIDATED, configuration_hash="sha256:other"
        )


def test_saving_a_changed_provenance_field_is_refused(make_run: RunFactory) -> None:
    previous = make_run(RunStatus.RUNNING)
    tampered = previous.model_copy(update={"seeds": (999,)})
    with pytest.raises(ImmutableRunError, match="seeds"):
        ensure_amendable(previous, tampered)


def test_a_finished_run_cannot_be_reopened(make_run: RunFactory) -> None:
    completed = make_run(RunStatus.COMPLETED)
    reopened = completed.model_copy(update={"status": RunStatus.RUNNING})
    with pytest.raises(ImmutableRunError, match="cannot be"):
        ensure_amendable(completed, reopened)


def test_amending_mutable_fields_is_allowed(make_run: RunFactory) -> None:
    running = make_run(RunStatus.RUNNING)
    ensure_amendable(running, running.model_copy(update={"artifacts": ("ART-000001",)}))


def test_configuration_hash_is_stable_and_order_independent(
    make_run: RunFactory,
) -> None:
    left = configuration_hash({"parameters": {"a": 1, "b": 2}, "seeds": [1]})
    right = configuration_hash({"seeds": [1], "parameters": {"b": 2, "a": 1}})
    assert left == right
    assert left.startswith("sha256:")
    assert left != configuration_hash({"parameters": {"a": 1}, "seeds": [2]})
