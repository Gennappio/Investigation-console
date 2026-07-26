"""Test execution (`lab test`, AGENTS.md section 10).

Each profile in ``lab.yaml`` maps to one of the four test categories, and the
result is recorded as structured evidence rather than a single green check.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from lab_domain.artifacts import ArtifactKind
from lab_domain.errors import ManifestInvalidError
from lab_domain.execution import ExecutionBackend, JobState, RunRequest
from lab_domain.ids import ArtifactId, RunId
from lab_domain.runs import ResourceRequest
from lab_domain.services.workspace_context import WorkspaceContext
from lab_domain.storage import ArtifactStore, RunStore
from lab_domain.suites import Check, CheckStatus, SuiteKind, SuiteResult

POLL_INTERVAL_SECONDS = 0.05
TEST_RESOURCES = ResourceRequest(cpus=1, memory_mb=1024)

PROFILE_SUITES = {
    "test": SuiteKind.SOFTWARE,
    "smoke": SuiteKind.INTEGRATION,
    "integration": SuiteKind.INTEGRATION,
    "reproducibility": SuiteKind.REPRODUCIBILITY,
    "validation": SuiteKind.SCIENTIFIC,
}


def suite_for_profile(profile: str) -> SuiteKind:
    """The test category a profile belongs to, defaulting to software tests."""
    return PROFILE_SUITES.get(profile, SuiteKind.SOFTWARE)


def run_test_profile(
    context: WorkspaceContext,
    profile: str,
    *,
    backend: ExecutionBackend,
    store: RunStore,
    artifacts: ArtifactStore,
    scratch_root: Path,
    suite: SuiteKind | None = None,
) -> SuiteResult:
    """Run one command profile and record what it proved."""
    commands = context.repository.spec.commands
    command = commands.get(profile)
    if command is None:
        available = ", ".join(sorted(commands)) or "none"
        raise ManifestInvalidError(
            f"lab.yaml defines no command profile {profile!r}. Available: {available}."
        )

    scratch = scratch_root / f"test-{profile}"
    started_at = datetime.now(UTC)
    request = RunRequest(
        # Tests run against the repository as it is checked out, so the
        # working directory is the project itself, not an isolated copy.
        run_id=RunId("RUN-000000"),
        argv=command,
        environment={"LAB_PROJECT_DIR": str(context.root), "PYTHONPATH": "src"},
        working_directory=context.root,
        output_directory=scratch / "outputs",
        log_directory=scratch / "logs",
        # A test profile runs on the machine that invoked it, not through a
        # scheduler, so it reserves nothing.
        resources=TEST_RESOURCES,
    )
    submission = backend.submit(request)
    while backend.status(submission.external_job_id).state is JobState.RUNNING:
        time.sleep(POLL_INTERVAL_SECONDS)
    collection = backend.collect(submission.external_job_id)

    stored: list[ArtifactId] = []
    for path, name in (
        (collection.stdout_path, f"{profile}-stdout.log"),
        (collection.stderr_path, f"{profile}-stderr.log"),
    ):
        if path.is_file():
            stored.append(artifacts.store(path, kind=ArtifactKind.LOG, name=name).id)

    status = CheckStatus.PASSED if collection.exit_code == 0 else CheckStatus.FAILED
    result = SuiteResult(
        project_id=context.repository.spec.project,
        suite=suite or suite_for_profile(profile),
        profile=profile,
        status=status,
        command=command,
        exit_code=collection.exit_code,
        started_at=started_at,
        completed_at=datetime.now(UTC),
        checks=(
            Check(
                name=f"{profile}_command_succeeded",
                status=status,
                message=f"exit code {collection.exit_code}",
            ),
        ),
        artifacts=tuple(stored),
    )
    store.save_test_result(result)
    return result
