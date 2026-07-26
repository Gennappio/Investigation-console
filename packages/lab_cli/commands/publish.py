"""`lab publish`: register a reusable component in the laboratory registry."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lab_cli.exit_codes import ExitCode
from lab_cli.options import JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_cli.runtime import (
    actor,
    default_audit_log,
    default_component_store,
    default_run_store,
)
from lab_domain.errors import InvalidNameError
from lab_domain.services.component_service import PublishResult, publish_component
from lab_domain.workspace import find_workspace_root

COMPONENT_KIND = "component"


def publish(
    kind: Annotated[
        str, typer.Argument(help="What to publish. Currently: component.")
    ] = COMPONENT_KIND,
    name: Annotated[
        str | None,
        typer.Option(
            "--name", help="Component to publish, if the repository has several."
        ),
    ] = None,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Publish a component, recording the test evidence behind its maturity."""

    def action() -> PublishResult:
        if kind != COMPONENT_KIND:
            raise InvalidNameError(
                f"Cannot publish {kind!r}. Available: {COMPONENT_KIND}."
            )
        return publish_component(
            find_workspace_root(Path.cwd()),
            name=name,
            store=default_component_store(),
            runs=default_run_store(),
            audit=default_audit_log(),
            actor=actor(),
        )

    result = run_or_fail(json_output, action)
    component = result.component
    emit(
        {
            "status": "already_published" if result.already_published else "published",
            "component_id": str(component.id),
            "name": component.name,
            "version": component.version,
            "maturity": component.status.value,
            "project": str(component.project_id),
            "evidence": [
                {
                    "suite": item.suite.value,
                    "profile": item.profile,
                    "status": item.status.value,
                }
                for item in component.evidence
            ],
            "missing_for_next_level": list(result.missing_for_next),
        },
        _render(result),
        json_output,
    )
    raise typer.Exit(int(ExitCode.OK))


def _render(result: PublishResult) -> str:
    component = result.component
    verb = "Already published" if result.already_published else "Published"
    lines = [
        f"{verb} {component.name} {component.version} as {component.id}",
        f"  maturity:   {component.status.value}",
        f"  maintainer: {component.maintainer or 'none'}",
    ]
    if component.evidence:
        lines.append("  evidence:")
        lines += [
            f"    {item.suite.value:<22} {item.status.value} (profile {item.profile})"
            for item in component.evidence
        ]
    else:
        lines.append("  evidence:   none recorded; run `lab test` first")
    if result.missing_for_next:
        lines.append(f"  to advance: {', '.join(result.missing_for_next)} must pass")
    else:
        lines.append(
            "  to advance: validated and lab_standard need a reviewer (`lab promote`)"
        )
    return "\n".join(lines)
