"""`lab init`: create a managed repository from the project template."""

from __future__ import annotations

import getpass
from pathlib import Path
from typing import Annotated

import typer

from lab_cli.exit_codes import ExitCode
from lab_cli.options import JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_cli.runtime import default_registry, project_template_dir
from lab_domain.services import InitResult, init_project


def init(
    name: Annotated[str, typer.Argument(help="Project name: lowercase, hyphenated.")],
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Create a new managed repository in the current directory."""

    def action() -> InitResult:
        return init_project(
            name=name,
            parent=Path.cwd(),
            registry=default_registry(),
            template_dir=project_template_dir(),
            owner=getpass.getuser(),
        )

    result = run_or_fail(json_output, action)
    emit(
        {
            "status": "created",
            "project_id": str(result.project_id),
            "experiment_id": str(result.experiment_id),
            "path": result.root,
            "files": list(result.files),
        },
        _render(result),
        json_output,
    )
    raise typer.Exit(int(ExitCode.OK))


def _render(result: InitResult) -> str:
    lines = [
        f"Created project {result.project_id} at {result.root}",
        f"Registered experiment {result.experiment_id}",
        "",
        "Files:",
        *(f"  {name}" for name in result.files),
        "",
        f"Next: cd {Path(result.root).name} && lab validate",
    ]
    return "\n".join(lines)
