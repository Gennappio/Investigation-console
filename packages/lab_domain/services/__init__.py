"""Application services. The CLI and the future API both call these."""

from lab_domain.services.build_service import BuildSummary, build_image, image_tag
from lab_domain.services.init_service import InitResult, init_project
from lab_domain.services.inspect_service import (
    ExperimentSummary,
    WorkspaceInfo,
    inspect_workspace,
)
from lab_domain.services.report_service import (
    ReportBundle,
    ReportDocument,
    generate_report,
)
from lab_domain.services.run_service import (
    RunOutcome,
    cancel_run,
    execute_run,
    refresh_run,
    scratch_directory,
    start_run,
    wait_for_run,
)
from lab_domain.services.test_service import run_test_profile, suite_for_profile
from lab_domain.services.validate_service import validate_workspace
from lab_domain.services.workspace_context import (
    WorkspaceContext,
    load_validated_workspace,
)

__all__ = [
    "BuildSummary",
    "ExperimentSummary",
    "InitResult",
    "ReportBundle",
    "ReportDocument",
    "RunOutcome",
    "WorkspaceContext",
    "WorkspaceInfo",
    "build_image",
    "cancel_run",
    "execute_run",
    "generate_report",
    "image_tag",
    "init_project",
    "inspect_workspace",
    "load_validated_workspace",
    "refresh_run",
    "run_test_profile",
    "scratch_directory",
    "start_run",
    "suite_for_profile",
    "wait_for_run",
    "validate_workspace",
]
