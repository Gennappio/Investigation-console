"""`lab test`: run one command profile and record the evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lab_cli.exit_codes import ExitCode
from lab_cli.identifiers import parse_optional_id
from lab_cli.options import EXPERIMENT_OPTION, JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_cli.runtime import (
    default_artifact_store,
    default_run_store,
    execution_backend,
    scratch_root,
)
from lab_domain.ids import ExperimentId
from lab_domain.services import load_validated_workspace, run_test_profile
from lab_domain.suites import CheckStatus, SuiteResult
from lab_domain.workspace import find_workspace_root


def test(
    profile: Annotated[
        str, typer.Option("--profile", help="Command profile from lab.yaml.")
    ] = "test",
    json_output: Annotated[bool, JSON_OPTION] = False,
    experiment: Annotated[str | None, EXPERIMENT_OPTION] = None,
) -> None:
    """Run a test profile. Each profile is recorded as its own suite."""

    def action() -> SuiteResult:
        chosen = parse_optional_id(ExperimentId, experiment)
        context = load_validated_workspace(find_workspace_root(Path.cwd()), chosen)
        return run_test_profile(
            context,
            profile,
            backend=execution_backend(),
            store=default_run_store(),
            artifacts=default_artifact_store(),
            scratch_root=scratch_root(),
        )

    result = run_or_fail(json_output, action)
    emit(
        {
            "suite": result.suite.value,
            "profile": result.profile,
            "status": result.status.value,
            "exit_code": result.exit_code,
            "command": list(result.command),
            "artifacts": [str(artifact) for artifact in result.artifacts],
        },
        "\n".join(
            [
                f"{result.suite.value}: {result.status.value} "
                f"(profile {result.profile}, exit code {result.exit_code})",
                f"  command: {' '.join(result.command)}",
                f"  logs:    {', '.join(str(a) for a in result.artifacts) or 'none'}",
            ]
        ),
        json_output,
    )
    raise typer.Exit(
        int(
            ExitCode.OK
            if result.status is CheckStatus.PASSED
            else ExitCode.TESTS_FAILED
        )
    )
