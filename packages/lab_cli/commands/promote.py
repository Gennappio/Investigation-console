"""`lab promote`: record a human judgement about a component."""

from __future__ import annotations

from typing import Annotated

import typer

from lab_cli.exit_codes import ExitCode
from lab_cli.identifiers import parse_id
from lab_cli.options import JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_cli.runtime import actor, default_audit_log, default_component_store
from lab_domain.components import ComponentRecord, DecisionRecord, Maturity
from lab_domain.errors import InvalidNameError
from lab_domain.ids import ComponentId
from lab_domain.services.component_service import promote_component


def promote(
    component_id: Annotated[
        str, typer.Argument(help="Component identifier, e.g. CMP-000001.")
    ],
    to: Annotated[
        str,
        typer.Option(
            "--to", help="Level to grant: validated, lab_standard, deprecated."
        ),
    ],
    note: Annotated[
        str,
        typer.Option("--note", help="What was reviewed. Becomes the decision record."),
    ],
    reviewer: Annotated[
        str | None, typer.Option("--reviewer", help="Who reviewed it.")
    ] = None,
    version: Annotated[
        str | None,
        typer.Option("--version", help="Version to promote; default is newest."),
    ] = None,
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Grant a maturity level that evidence alone cannot establish."""

    def action() -> tuple[ComponentRecord, DecisionRecord]:
        return promote_component(
            parse_id(ComponentId, component_id),
            to=_maturity(to),
            reviewer=reviewer or actor(),
            note=note,
            store=default_component_store(),
            audit=default_audit_log(),
            version=version,
        )

    component, decision = run_or_fail(json_output, action)
    emit(
        {
            "component_id": str(component.id),
            "version": component.version,
            "maturity": component.status.value,
            "decision_id": str(decision.id),
            "from_status": decision.from_status.value,
            "reviewer": decision.reviewer,
            "note": decision.note,
        },
        "\n".join(
            [
                f"{component.id} {component.version}: "
                f"{decision.from_status.value} → {component.status.value}",
                f"  reviewer: {decision.reviewer}",
                f"  decision: {decision.id}",
                f"  note:     {decision.note}",
            ]
        ),
        json_output,
    )
    raise typer.Exit(int(ExitCode.OK))


def _maturity(value: str) -> Maturity:
    try:
        return Maturity(value)
    except ValueError as exc:
        levels = ", ".join(level.value for level in Maturity)
        raise InvalidNameError(
            f"Unknown maturity {value!r}. Levels: {levels}."
        ) from exc
