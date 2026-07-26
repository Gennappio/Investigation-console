"""`lab validate`: check the manifests of the current repository."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lab_cli.exit_codes import ExitCode
from lab_cli.options import JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_domain.services import validate_workspace
from lab_domain.validation.findings import Finding, ValidationReport
from lab_domain.workspace import find_workspace_root


def validate(json_output: Annotated[bool, JSON_OPTION] = False) -> None:
    """Validate lab.yaml and every experiment manifest."""

    def action() -> ValidationReport:
        return validate_workspace(find_workspace_root(Path.cwd()))

    report = run_or_fail(json_output, action)
    emit(report.to_payload(), _render(report), json_output)
    raise typer.Exit(int(ExitCode.OK if report.valid else ExitCode.VALIDATION_FAILED))


def _render(report: ValidationReport) -> str:
    lines = [_line("error", f) for f in report.errors]
    lines += [_line("warning", f) for f in report.warnings]
    if report.valid:
        summary = f"valid ({len(report.warnings)} warnings)"
    else:
        summary = f"invalid ({len(report.errors)} errors, "
        summary += f"{len(report.warnings)} warnings)"
    lines.append(summary)
    return "\n".join(lines)


def _line(severity: str, finding: Finding) -> str:
    location = f"{finding.file}:{finding.path}" if finding.path else f"{finding.file}"
    return f"{severity}: {location}: [{finding.code.value}] {finding.message}"
