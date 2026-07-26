"""`lab report`: write the report bundle of a finished run."""

from __future__ import annotations

import functools
from typing import Annotated

import typer
from lab_reporting.renderer import render_html

from lab_cli.exit_codes import ExitCode
from lab_cli.identifiers import parse_id
from lab_cli.options import JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_cli.runtime import (
    default_artifact_store,
    default_run_store,
    report_template_dir,
    scratch_root,
)
from lab_domain.ids import RunId
from lab_domain.services import ReportBundle, generate_report


def report(
    run_id: Annotated[str, typer.Argument(help="Run identifier, e.g. RUN-000001.")],
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Generate report.html, report.json, provenance.json and checksums.txt."""

    def action() -> ReportBundle:
        return generate_report(
            parse_id(RunId, run_id),
            store=default_run_store(),
            artifacts=default_artifact_store(),
            scratch_root=scratch_root(),
            render_html=functools.partial(render_html, report_template_dir()),
        )

    bundle = run_or_fail(json_output, action)
    emit(
        {
            "run_id": str(bundle.run_id),
            "status": bundle.document.run.status.value,
            "artifacts": [
                {"id": str(a.id), "name": a.name, "uri": a.uri, "checksum": a.checksum}
                for a in bundle.artifacts
            ],
        },
        _render(bundle),
        json_output,
    )
    raise typer.Exit(int(ExitCode.OK))


def _render(bundle: ReportBundle) -> str:
    lines = [f"Report for {bundle.run_id} ({bundle.document.run.status.value})"]
    lines += [f"  {a.name:<17} {a.uri}" for a in bundle.artifacts]
    html = bundle.artifact_named("report.html")
    if html is not None:
        lines.append(f"\nOpen: {html.uri}")
    return "\n".join(lines)
