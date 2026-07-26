"""`lab inspect`: summarize the current repository."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lab_cli.exit_codes import ExitCode
from lab_cli.options import JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_domain.services import WorkspaceInfo, inspect_workspace
from lab_domain.workspace import find_workspace_root


def inspect(json_output: Annotated[bool, JSON_OPTION] = False) -> None:
    """Show the project, runtime, commands and experiments of this repository."""

    def action() -> WorkspaceInfo:
        return inspect_workspace(find_workspace_root(Path.cwd()))

    info = run_or_fail(json_output, action)
    emit(info.model_dump(mode="json"), _render(info), json_output)
    raise typer.Exit(int(ExitCode.OK))


def _render(info: WorkspaceInfo) -> str:
    lines = [
        f"{info.name} ({info.project_id})",
        f"  root:     {info.root}",
        f"  runtime:  {info.runtime.type} {info.runtime.version}",
        f"  owners:   {', '.join(info.owners) or '-'}",
        f"  outputs:  {info.outputs_directory or '-'}",
        f"  commands: {', '.join(sorted(info.commands)) or '-'}",
    ]
    if info.experiments:
        lines.append(f"  experiments ({len(info.experiments)}):")
        lines += [
            f"    {experiment.id}  {experiment.title}  [{experiment.owner}]"
            for experiment in info.experiments
        ]
    else:
        lines.append("  experiments: none")
    return "\n".join(lines)
