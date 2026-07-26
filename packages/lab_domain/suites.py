"""Test evidence (AGENTS.md section 10).

Test status is never collapsed into one green check: each suite is recorded
separately, and passing software tests say nothing about scientific validity.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from lab_domain.ids import ArtifactId, ProjectId


class SuiteKind(StrEnum):
    SOFTWARE = "software_tests"
    INTEGRATION = "integration_tests"
    REPRODUCIBILITY = "reproducibility_tests"
    SCIENTIFIC = "scientific_validation"


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"


class SuiteModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class Check(SuiteModel):
    name: str
    status: CheckStatus
    observed: float | None = None
    threshold: float | None = None
    message: str | None = None


class SuiteResult(SuiteModel):
    project_id: ProjectId
    suite: SuiteKind
    profile: str
    status: CheckStatus
    command: tuple[str, ...]
    exit_code: int | None
    started_at: datetime
    completed_at: datetime
    checks: tuple[Check, ...] = ()
    artifacts: tuple[ArtifactId, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status is CheckStatus.PASSED
