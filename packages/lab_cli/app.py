"""Assembly of the `lab` command-line application."""

from __future__ import annotations

import typer

from lab_cli.commands import init, inspect, validate

app = typer.Typer(
    name="lab",
    help="Research Execution Platform.",
    no_args_is_help=True,
    add_completion=False,
)

app.command("init")(init.init)
app.command("validate")(validate.validate)
app.command("inspect")(inspect.inspect)
