"""`lab search`: find registered components."""

from __future__ import annotations

from typing import Annotated

import typer

from lab_cli.exit_codes import ExitCode
from lab_cli.options import JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_cli.runtime import default_component_store
from lab_domain.components import Maturity
from lab_domain.errors import InvalidNameError
from lab_domain.services.component_service import SearchHit, search_components

COMPONENT_KIND = "components"


def search(
    kind: Annotated[
        str, typer.Argument(help="What to search. Currently: components.")
    ] = COMPONENT_KIND,
    query: Annotated[str, typer.Argument(help="Words to match.")] = "",
    json_output: Annotated[bool, JSON_OPTION] = False,
    status: Annotated[
        str | None, typer.Option("--status", help="Only this maturity level.")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum results.")] = 20,
) -> None:
    """Search the registry. An empty query lists everything registered."""

    def action() -> tuple[SearchHit, ...]:
        if kind != COMPONENT_KIND:
            raise InvalidNameError(
                f"Cannot search {kind!r}. Available: {COMPONENT_KIND}."
            )
        return search_components(
            query,
            store=default_component_store(),
            status=_maturity(status),
            limit=limit,
        )

    hits = run_or_fail(json_output, action)
    emit(
        {
            "query": query,
            "count": len(hits),
            "results": [
                {
                    "id": str(hit.component.id),
                    "name": hit.component.name,
                    "version": hit.component.version,
                    "maturity": hit.component.status.value,
                    "maintainer": hit.component.maintainer,
                    "description": hit.component.description,
                    "keywords": list(hit.component.keywords),
                    "project": str(hit.component.project_id),
                    "command": list(hit.component.command),
                    "references": list(hit.component.references),
                    "evidence": [
                        {"suite": e.suite.value, "status": e.status.value}
                        for e in hit.component.evidence
                    ],
                    "reviewed_by": (
                        hit.component.review.reviewer if hit.component.review else None
                    ),
                    "score": hit.score,
                }
                for hit in hits
            ],
        },
        _render(hits),
        json_output,
    )
    raise typer.Exit(int(ExitCode.OK))


def _maturity(status: str | None) -> Maturity | None:
    if status is None:
        return None
    try:
        return Maturity(status)
    except ValueError as exc:
        levels = ", ".join(level.value for level in Maturity)
        raise InvalidNameError(
            f"Unknown maturity {status!r}. Levels: {levels}."
        ) from exc


def _render(hits: tuple[SearchHit, ...]) -> str:
    if not hits:
        return "No components matched. Publish one with `lab publish component`."
    lines = [f"{len(hits)} component(s):"]
    for hit in hits:
        component = hit.component
        lines.append(
            f"  {component.id}  {component.name} {component.version}  "
            f"[{component.status.value}]"
        )
        if component.description:
            lines.append(f"      {component.description}")
        evidence = ", ".join(
            f"{item.suite.value}={item.status.value}" for item in component.evidence
        )
        lines.append(f"      evidence: {evidence or 'none recorded'}")
    return "\n".join(lines)
