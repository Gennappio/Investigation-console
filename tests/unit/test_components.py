"""The maturity ladder: what evidence establishes, and what it never can."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lab_domain.components import (
    REVIEWED_LEVELS,
    ComponentRecord,
    DecisionRecord,
    Maturity,
    SuiteEvidence,
    content_hash,
    evidenced_maturity,
    missing_for_next_level,
)
from lab_domain.errors import NotFoundError, StateStoreError
from lab_domain.storage import ComponentStore
from lab_domain.suites import CheckStatus, SuiteKind
from lab_registry.component_store import FileComponentStore
from lab_registry.local_store import LocalRegistry

NOW = datetime(2026, 7, 26, tzinfo=UTC)


def passed(suite: SuiteKind, profile: str = "p") -> SuiteEvidence:
    return SuiteEvidence(suite=suite, profile=profile, status=CheckStatus.PASSED)


def failed(suite: SuiteKind, profile: str = "p") -> SuiteEvidence:
    return SuiteEvidence(suite=suite, profile=profile, status=CheckStatus.FAILED)


def make_component(**changes: object) -> ComponentRecord:
    base: dict[str, object] = {
        "id": "CMP-000001",
        "project_id": "PRJ-000001",
        "name": "sobol-sensitivity-analysis",
        "version": "1.0.0",
        "status": Maturity.TESTED,
        "maintainer": "anna.rossi",
        "description": "Variance-based sensitivity analysis",
        "keywords": ("sensitivity", "sobol"),
        "command": ("python", "-m", "demo.sobol"),
        "inputs": {},
        "outputs": {},
        "container": None,
        "tests": {"software_tests": "test"},
        "references": (),
        "evidence": (),
        "content_hash": "sha256:abc",
        "published_by": "anna.rossi",
        "published_at": NOW,
    }
    return ComponentRecord.model_validate({**base, **changes})


@pytest.fixture
def store(tmp_path: Path) -> FileComponentStore:
    return FileComponentStore(tmp_path / "home", LocalRegistry(tmp_path / "home"))


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ((), Maturity.DRAFT),
        ((passed(SuiteKind.SOFTWARE),), Maturity.DRAFT),
        ((passed(SuiteKind.INTEGRATION),), Maturity.RUNNABLE),
        (
            (passed(SuiteKind.SOFTWARE), passed(SuiteKind.INTEGRATION)),
            Maturity.TESTED,
        ),
        (
            (
                passed(SuiteKind.SOFTWARE),
                passed(SuiteKind.INTEGRATION),
                passed(SuiteKind.REPRODUCIBILITY),
            ),
            Maturity.REPRODUCIBLE,
        ),
        (
            (passed(SuiteKind.INTEGRATION), failed(SuiteKind.SOFTWARE)),
            Maturity.RUNNABLE,
        ),
    ],
)
def test_evidence_establishes_the_level(
    evidence: tuple[SuiteEvidence, ...], expected: Maturity
) -> None:
    assert evidenced_maturity(evidence) is expected


def test_evidence_never_reaches_a_reviewed_level() -> None:
    """No amount of passing tests makes a component scientifically valid."""
    everything = tuple(passed(suite) for suite in SuiteKind)
    assert evidenced_maturity(everything) is Maturity.REPRODUCIBLE
    assert evidenced_maturity(everything) not in REVIEWED_LEVELS


def test_the_next_step_is_named() -> None:
    assert missing_for_next_level(()) == ("integration_tests",)
    assert missing_for_next_level((passed(SuiteKind.INTEGRATION),)) == (
        "software_tests",
    )
    assert missing_for_next_level(
        (passed(SuiteKind.SOFTWARE), passed(SuiteKind.INTEGRATION))
    ) == ("reproducibility_tests",)
    assert (
        missing_for_next_level(
            (
                passed(SuiteKind.SOFTWARE),
                passed(SuiteKind.INTEGRATION),
                passed(SuiteKind.REPRODUCIBILITY),
            )
        )
        == ()
    )


def test_content_hash_is_order_independent() -> None:
    left = content_hash({"a": 1, "b": [2, 3]})
    right = content_hash({"b": [2, 3], "a": 1})
    assert left == right
    assert left != content_hash({"a": 1, "b": [2, 4]})


def test_the_store_satisfies_its_port(store: FileComponentStore) -> None:
    port: ComponentStore = store
    assert port.list_components() == ()
    assert port.allocate_component_id() == "CMP-000001"
    assert port.allocate_decision_id() == "DEC-000001"


def test_versions_are_kept_side_by_side(store: FileComponentStore) -> None:
    store.save_component(make_component(version="1.0.0"))
    store.save_component(make_component(version="1.10.0"))
    store.save_component(make_component(version="1.9.0"))

    assert len(store.list_components()) == 3
    # Newest means numerically newest, so 1.10.0 beats 1.9.0.
    assert store.get_component("CMP-000001").version == "1.10.0"
    assert store.get_component("CMP-000001", "1.0.0").version == "1.0.0"


def test_an_unknown_component_or_version_is_reported(store: FileComponentStore) -> None:
    with pytest.raises(NotFoundError, match="No component"):
        store.get_component("CMP-000404")
    store.save_component(make_component())
    with pytest.raises(NotFoundError, match="no version 9.9.9"):
        store.get_component("CMP-000001", "9.9.9")


def test_components_are_found_by_project_and_name(store: FileComponentStore) -> None:
    store.save_component(make_component())
    store.save_component(make_component(id="CMP-000002", name="other"))
    found = store.find_by_name("PRJ-000001", "sobol-sensitivity-analysis")
    assert [record.id for record in found] == ["CMP-000001"]
    assert store.find_by_name("PRJ-000002", "sobol-sensitivity-analysis") == ()


def test_decisions_are_recorded_and_listed(store: FileComponentStore) -> None:
    decision = DecisionRecord(
        id="DEC-000001",
        component_id="CMP-000001",
        component_version="1.0.0",
        from_status=Maturity.TESTED,
        to_status=Maturity.VALIDATED,
        reviewer="pi.rossi",
        note="Reproduced the published figure.",
        decided_at=NOW,
    )
    store.save_decision(decision)
    assert store.list_decisions() == (decision,)
    assert store.list_decisions("CMP-000001") == (decision,)
    assert store.list_decisions("CMP-000002") == ()


def test_a_corrupt_record_is_reported(
    store: FileComponentStore, tmp_path: Path
) -> None:
    store.save_component(make_component())
    (tmp_path / "home" / "components" / "CMP-000001-1.0.0.json").write_text("{oops")
    with pytest.raises(StateStoreError, match="unreadable"):
        store.list_components()
