"""Domain exceptions. Each maps to a CLI exit code (AGENTS.md section 13.2)."""

from __future__ import annotations


class LabError(Exception):
    """Base class for expected, reportable platform failures."""

    code: str = "LAB_ERROR"


class WorkspaceNotFoundError(LabError):
    """No lab.yaml was found in the current directory or any parent."""

    code = "MANIFEST_NOT_FOUND"


class InvalidNameError(LabError):
    """A user-supplied name does not meet the naming rules."""

    code = "INVALID_NAME"


class TargetExistsError(LabError):
    """The target path for a new project already exists."""

    code = "TARGET_EXISTS"


class StateStoreError(LabError):
    """The platform state directory or a template source is unusable."""

    code = "STATE_STORE_ERROR"
