"""Assembly of the `lab` command-line application."""

from __future__ import annotations

import typer

from lab_cli.commands import (
    build,
    cancel,
    init,
    inspect,
    report,
    run,
    status,
    test,
    validate,
)

app = typer.Typer(
    name="lab",
    help="Research Execution Platform.",
    no_args_is_help=True,
    add_completion=False,
)

app.command("init")(init.init)
app.command("validate")(validate.validate)
app.command("inspect")(inspect.inspect)
app.command("build")(build.build)
app.command("test")(test.test)
app.command("run")(run.run)
app.command("status")(status.status)
app.command("cancel")(cancel.cancel)
app.command("report")(report.report)
