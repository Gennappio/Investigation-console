"""Reusable components and how mature they are (AGENTS.md section 6.4).

Maturity is split in two. Up to ``reproducible`` it is *evidenced*: the
platform reads the test results it recorded and states the level it can
support. ``validated`` and ``lab_standard`` are *reviewed*: only a person can
grant them, and doing so leaves a decision record (ADR 0009).

A component that executes successfully is not scientifically valid, and this
module is where that distinction is enforced rather than described.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from lab_domain.ids import ComponentId, DecisionId, ProjectId
from lab_domain.suites import CheckStatus, SuiteKind


class Maturity(StrEnum):
    DRAFT = "draft"
    RUNNABLE = "runnable"
    TESTED = "tested"
    REPRODUCIBLE = "reproducible"
    VALIDATED = "validated"
    LAB_STANDARD = "lab_standard"
    DEPRECATED = "deprecated"


# The ladder the platform can climb on evidence alone, in order.
EVIDENCED_LADDER: tuple[Maturity, ...] = (
    Maturity.DRAFT,
    Maturity.RUNNABLE,
    Maturity.TESTED,
    Maturity.REPRODUCIBLE,
)

# Levels a person must grant, and which therefore need a decision record.
REVIEWED_LEVELS = frozenset(
    {Maturity.VALIDATED, Maturity.LAB_STANDARD, Maturity.DEPRECATED}
)

# What each evidenced level requires: every suite listed must have passed.
EVIDENCE_REQUIREMENTS: dict[Maturity, tuple[SuiteKind, ...]] = {
    Maturity.RUNNABLE: (SuiteKind.INTEGRATION,),
    Maturity.TESTED: (SuiteKind.SOFTWARE, SuiteKind.INTEGRATION),
    Maturity.REPRODUCIBLE: (
        SuiteKind.SOFTWARE,
        SuiteKind.INTEGRATION,
        SuiteKind.REPRODUCIBILITY,
    ),
}


class ComponentModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class SuiteEvidence(ComponentModel):
    """One recorded test result, as it stood when the component was published."""

    suite: SuiteKind
    profile: str
    status: CheckStatus
    completed_at: datetime | None = None

    @property
    def passed(self) -> bool:
        return self.status is CheckStatus.PASSED


class ReviewRef(ComponentModel):
    decision: DecisionId
    reviewer: str
    decided_at: datetime


class ComponentRecord(ComponentModel):
    """A published version of a component."""

    id: ComponentId
    project_id: ProjectId
    name: str
    version: str
    status: Maturity
    maintainer: str | None
    description: str | None
    keywords: tuple[str, ...]
    command: tuple[str, ...]
    inputs: dict[str, str]
    outputs: dict[str, str]
    container: str | None
    tests: dict[str, str]
    references: tuple[str, ...]
    evidence: tuple[SuiteEvidence, ...]
    # What the manifest said, so republishing a changed version is detectable.
    content_hash: str
    published_by: str
    published_at: datetime
    review: ReviewRef | None = None

    @property
    def evidenced_status(self) -> Maturity:
        return evidenced_maturity(self.evidence)


class DecisionRecord(ComponentModel):
    """A human judgement about a component (AGENTS.md sections 15.4, 20)."""

    id: DecisionId
    component_id: ComponentId
    component_version: str
    from_status: Maturity
    to_status: Maturity
    reviewer: str
    note: str
    decided_at: datetime


def evidenced_maturity(evidence: tuple[SuiteEvidence, ...]) -> Maturity:
    """The highest level the recorded evidence supports.

    Never returns a reviewed level: no amount of passing tests makes a
    component scientifically validated (AGENTS.md section 2.7).
    """
    passed = {item.suite for item in evidence if item.passed}
    reached = Maturity.DRAFT
    for level in EVIDENCED_LADDER[1:]:
        if set(EVIDENCE_REQUIREMENTS[level]).issubset(passed):
            reached = level
        else:
            break
    return reached


def missing_for_next_level(evidence: tuple[SuiteEvidence, ...]) -> tuple[str, ...]:
    """Which suites still have to pass to climb one more rung."""
    current = evidenced_maturity(evidence)
    if current is Maturity.REPRODUCIBLE:
        return ()
    next_level = EVIDENCED_LADDER[EVIDENCED_LADDER.index(current) + 1]
    passed = {item.suite for item in evidence if item.passed}
    return tuple(
        suite.value
        for suite in EVIDENCE_REQUIREMENTS[next_level]
        if suite not in passed
    )


def content_hash(payload: dict[str, Any]) -> str:
    """Stable hash of what a published version claims to be."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
