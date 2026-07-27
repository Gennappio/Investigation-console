"""`lab sync`: write the vault notes for this repository."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from lab_obsidian.vault import load_vault_settings

from lab_cli.exit_codes import ExitCode
from lab_cli.options import JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_cli.projection import note_payload, project_workspace_at
from lab_cli.runtime import lab_home
from lab_domain.errors import StateStoreError
from lab_domain.services.obsidian_service import ProjectionResult
from lab_domain.workspace import find_workspace_root

OBSIDIAN_TARGET = "obsidian"


def sync(
    target: Annotated[
        str, typer.Argument(help="What to sync. Currently: obsidian.")
    ] = OBSIDIAN_TARGET,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Project this repository, its experiments and its runs into the vault."""

    def action() -> ProjectionResult:
        if target != OBSIDIAN_TARGET:
            raise StateStoreError(
                f"Cannot sync {target!r}. Available: {OBSIDIAN_TARGET}."
            )
        if not load_vault_settings(lab_home()).enabled:
            raise StateStoreError(
                "No Obsidian vault is configured. Set LAB_OBSIDIAN_VAULT, or "
                "`vault` in $LAB_HOME/obsidian.json."
            )
        return project_workspace_at(find_workspace_root(Path.cwd()))

    result = run_or_fail(json_output, action)
    emit(
        {"notes": note_payload(result), "conflicts": len(result.conflicts)},
        _render(result),
        json_output,
    )
    raise typer.Exit(int(ExitCode.OK))


def _render(result: ProjectionResult) -> str:
    lines = [f"{len(result.notes)} note(s) written:"]
    lines += [f"  {note['outcome']:<10} {note['path']}" for note in result.notes]
    if result.conflicts:
        lines.append("")
        lines.append(
            "Some notes were left untouched because they could not be parsed "
            "safely. The generated version is beside each one:"
        )
        lines += [
            f"  {note['path']}\n    reason:   {note.get('reason')}"
            f"\n    generated: {note.get('sidecar')}"
            for note in result.conflicts
        ]
    return "\n".join(lines)
