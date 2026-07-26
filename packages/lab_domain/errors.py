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


class ManifestInvalidError(LabError):
    """A command that requires valid manifests was run on invalid ones."""

    code = "MANIFEST_INVALID"


class DependencyError(LabError):
    """A required external tool is missing or not reachable."""

    code = "DEPENDENCY_UNAVAILABLE"


class BuildFailedError(LabError):
    """Building the container image failed."""

    code = "BUILD_FAILED"


class TestsFailedError(LabError):
    """A test suite reported failures."""

    code = "TESTS_FAILED"


class ExecutionFailedError(LabError):
    """The execution itself failed or was rejected by the backend."""

    code = "EXECUTION_FAILED"


class CollectionFailedError(LabError):
    """Outputs could not be collected into permanent storage."""

    code = "COLLECTION_FAILED"


class NotFoundError(LabError):
    """A requested record does not exist."""

    code = "NOT_FOUND"


class ImmutableRunError(LabError):
    """An attempt to rewrite the recorded history of a run (section 2.3)."""

    code = "RUN_IMMUTABLE"


class InvalidTransitionError(LabError):
    """A run state transition that the state machine forbids."""

    code = "INVALID_TRANSITION"
