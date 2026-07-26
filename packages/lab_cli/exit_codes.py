"""Exit codes of the `lab` CLI (AGENTS.md section 13.2).

The full table is declared here so later milestones reuse the same numbers.
Milestone 1 can return 0, 1, 2, 3, 4 and 12.
"""

from __future__ import annotations

from enum import IntEnum

from lab_domain.errors import (
    InvalidNameError,
    LabError,
    StateStoreError,
    TargetExistsError,
    WorkspaceNotFoundError,
)


class ExitCode(IntEnum):
    OK = 0
    INTERNAL_ERROR = 1
    INVALID_INPUT = 2
    VALIDATION_FAILED = 3
    ENVIRONMENT_ERROR = 4
    BUILD_FAILED = 5
    TESTS_FAILED = 6
    SUBMISSION_FAILED = 7
    EXECUTION_FAILED = 8
    COLLECTION_FAILED = 9
    AUTHORIZATION_DENIED = 10
    NOT_FOUND = 11
    CONFLICT = 12


_BY_ERROR: dict[type[LabError], ExitCode] = {
    # A missing or unreadable manifest is a manifest-level failure, so it shares
    # the code of a failed validation. 11 is reserved for registry lookups.
    WorkspaceNotFoundError: ExitCode.VALIDATION_FAILED,
    InvalidNameError: ExitCode.INVALID_INPUT,
    StateStoreError: ExitCode.ENVIRONMENT_ERROR,
    TargetExistsError: ExitCode.CONFLICT,
}


def exit_code_for(error: LabError) -> ExitCode:
    return _BY_ERROR.get(type(error), ExitCode.INTERNAL_ERROR)
