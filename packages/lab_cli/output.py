"""The only module that writes CLI output.

Machine-readable mode prints one JSON document on stdout and nothing else, so
an external agent never has to parse prose (AGENTS.md section 13.3).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import typer

from lab_cli.exit_codes import exit_code_for
from lab_domain.errors import LabError


def emit(payload: dict[str, Any], human: str, json_mode: bool) -> None:
    typer.echo(json.dumps(payload, indent=2) if json_mode else human)


def emit_error(error: LabError, json_mode: bool) -> None:
    if json_mode:
        typer.echo(
            json.dumps(
                {"status": "error", "code": error.code, "message": str(error)},
                indent=2,
            )
        )
    else:
        typer.echo(f"error: {error}", err=True)


def run_or_fail[ResultT](json_mode: bool, action: Callable[[], ResultT]) -> ResultT:
    """Run an application service, turning domain errors into exit codes."""
    try:
        return action()
    except LabError as error:
        emit_error(error, json_mode)
        raise typer.Exit(int(exit_code_for(error))) from error
