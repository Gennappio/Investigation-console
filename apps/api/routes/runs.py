"""Runs, their status and their reports.

Artifact URIs are the stable ``lab-artifact://`` form. Where the bytes sit on
disk is operational detail and is not published here (AGENTS.md section 14).
"""

from __future__ import annotations

import functools
from typing import Any

from fastapi import APIRouter, Query
from lab_reporting.renderer import render_html

from api.dependencies import (
    artifact_store,
    report_template_dir,
    run_store,
    scratch_root,
)
from lab_domain.artifacts import ArtifactRecord
from lab_domain.ids import ExperimentId, RunId
from lab_domain.runs import RunRecord
from lab_domain.services.report_service import generate_report
from lab_domain.uris import artifacts_uri, lab_uri, report_uri

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
def list_runs(
    experiment: str | None = Query(default=None, description="Filter by experiment."),
    status: str | None = Query(default=None, description="Filter by run status."),
) -> dict[str, Any]:
    records = run_store().list_runs(ExperimentId(experiment) if experiment else None)
    if status:
        records = tuple(record for record in records if record.status.value == status)
    return {"count": len(records), "results": [_summary(record) for record in records]}


@router.get("/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    record = run_store().get_run(RunId(run_id))
    artifacts = artifact_store().list_artifacts(record.id)
    return {
        **_summary(record),
        "code": record.code.model_dump(mode="json"),
        "container": record.container.model_dump(mode="json"),
        "datasets": [pin.model_dump(mode="json") for pin in record.datasets],
        "parameters": record.parameters,
        "seeds": list(record.seeds),
        "resources": record.resources.model_dump(mode="json"),
        "command": list(record.command),
        "submitted_by": record.submitted_by,
        "deviations": list(record.deviations),
        "failure_reason": record.failure_reason,
        "artifacts": [_artifact(artifact) for artifact in artifacts],
    }


@router.get("/{run_id}/status")
def get_status(run_id: str) -> dict[str, Any]:
    """What is recorded, without contacting the backend.

    Reconciling a cluster job is a state change, so it belongs to `lab status`.
    """
    record = run_store().get_run(RunId(run_id))
    return {
        "id": str(record.id),
        "status": record.status.value,
        "backend": record.backend,
        "external_job_id": record.external_job_id,
        "exit_code": record.exit_code,
        "started_at": _stamp(record.started_at),
        "completed_at": _stamp(record.completed_at),
        "terminal": record.is_terminal,
    }


@router.get("/{run_id}/report")
def get_report(run_id: str) -> dict[str, Any]:
    """The structured report of a finished run, generated if it is missing."""
    store = artifact_store()
    bundle = generate_report(
        RunId(run_id),
        store=run_store(),
        artifacts=store,
        scratch_root=scratch_root(),
        render_html=functools.partial(render_html, report_template_dir()),
    )
    return {
        "run_id": str(bundle.run_id),
        "report": bundle.document.model_dump(mode="json"),
        "artifacts": [_artifact(artifact) for artifact in bundle.artifacts],
    }


def _summary(record: RunRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "uri": lab_uri(record.id),
        "experiment": lab_uri(record.experiment_id),
        "project": lab_uri(record.project_id),
        "status": record.status.value,
        "backend": record.backend,
        "external_job_id": record.external_job_id,
        "exit_code": record.exit_code,
        "configuration_hash": record.configuration_hash,
        "created_at": _stamp(record.created_at),
        "completed_at": _stamp(record.completed_at),
        "report_uri": report_uri(record.id),
        "artifacts_uri": artifacts_uri(record.id),
    }


def _artifact(artifact: ArtifactRecord) -> dict[str, Any]:
    return {
        "id": str(artifact.id),
        "uri": lab_uri(artifact.id),
        "kind": artifact.kind.value,
        "name": artifact.name,
        "checksum": artifact.checksum,
        "size_bytes": artifact.size_bytes,
        "media_type": artifact.media_type,
    }


def _stamp(value: Any) -> str | None:
    return value.isoformat() if value is not None else None
