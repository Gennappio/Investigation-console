"""The component registry, and what stands behind each entry."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import component_store
from lab_domain.components import ComponentRecord, Maturity
from lab_domain.ids import ComponentId
from lab_domain.services.component_service import search_components
from lab_domain.uris import lab_uri

router = APIRouter(prefix="/components", tags=["components"])


@router.get("")
def list_components(
    q: str = Query(default="", description="Words to match."),
    status: str | None = Query(default=None, description="Filter by maturity."),
    limit: int = Query(default=20, ge=1, le=200),
) -> dict[str, Any]:
    hits = search_components(
        q,
        store=component_store(),
        status=Maturity(status) if status else None,
        limit=limit,
    )
    return {
        "query": q,
        "count": len(hits),
        "results": [{**_summary(hit.component), "score": hit.score} for hit in hits],
    }


@router.get("/{component_id}")
def get_component(
    component_id: str,
    version: str | None = Query(default=None, description="Default is newest."),
) -> dict[str, Any]:
    store = component_store()
    record = store.get_component(ComponentId(component_id), version)
    decisions = store.list_decisions(record.id)
    return {
        **_summary(record),
        "command": list(record.command),
        "inputs": record.inputs,
        "outputs": record.outputs,
        "tests": record.tests,
        "references": list(record.references),
        "published_by": record.published_by,
        "published_at": record.published_at.isoformat(),
        "content_hash": record.content_hash,
        "decisions": [
            {
                "id": str(decision.id),
                "uri": lab_uri(decision.id),
                "from_status": decision.from_status.value,
                "to_status": decision.to_status.value,
                "reviewer": decision.reviewer,
                "note": decision.note,
                "decided_at": decision.decided_at.isoformat(),
            }
            for decision in decisions
        ],
    }


def _summary(record: ComponentRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "uri": lab_uri(record.id),
        "name": record.name,
        "version": record.version,
        "maturity": record.status.value,
        "maintainer": record.maintainer,
        "description": record.description,
        "keywords": list(record.keywords),
        "project": lab_uri(record.project_id),
        # Maturity means nothing without the evidence behind it, so the two
        # always travel together (AGENTS.md section 2.7).
        "evidence": [
            {
                "suite": item.suite.value,
                "profile": item.profile,
                "status": item.status.value,
            }
            for item in record.evidence
        ],
        "reviewed_by": record.review.reviewer if record.review else None,
    }
