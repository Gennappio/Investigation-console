"""Options shared by every command."""

from __future__ import annotations

import typer

JSON_OPTION = typer.Option("--json", help="Emit machine-readable JSON on stdout.")
