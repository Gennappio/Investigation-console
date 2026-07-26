"""Run reports (`lab report`, AGENTS.md section 11).

Every factual field comes from the run record and the stored artifacts. Nothing
here infers or narrates; interpretation is human-authored and lives elsewhere.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from lab_domain.artifacts import ArtifactKind, ArtifactRecord
from lab_domain.errors import NotFoundError
from lab_domain.ids import RunId
from lab_domain.runs import RunRecord, RunStatus
from lab_domain.storage import ArtifactStore, RunStore
from lab_domain.suites import SuiteResult

REPORT_JSON = "report.json"
REPORT_HTML = "report.html"
PROVENANCE_JSON = "provenance.json"
CHECKSUMS_TXT = "checksums.txt"
METRICS_FILENAME = "metrics.json"

HtmlRenderer = Callable[["ReportDocument"], str]


class ReportModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class ExperimentSection(ReportModel):
    id: str
    title: str
    question: str
    hypothesis: str
    references: tuple[str, ...]


class ResourceUsage(ReportModel):
    requested_cpus: int
    requested_memory_mb: int
    requested_gpus: int
    time_limit: str | None
    wall_time_seconds: float | None


class ReportDocument(ReportModel):
    """The structured report; ``report.json`` is this document verbatim."""

    generated_at: datetime
    run: RunRecord
    experiment: ExperimentSection
    datasets: tuple[dict[str, str], ...]
    code: dict[str, str | bool | None]
    container: dict[str, str | None]
    parameters: dict[str, Any]
    seeds: tuple[int, ...]
    resource_usage: ResourceUsage
    test_results: tuple[SuiteResult, ...]
    outputs: tuple[ArtifactRecord, ...]
    metrics: dict[str, Any]
    deviations: tuple[str, ...]
    limitations: str | None
    reproduction_command: str
    references: tuple[str, ...]


class ReportBundle(ReportModel):
    run_id: RunId
    document: ReportDocument
    artifacts: tuple[ArtifactRecord, ...]

    def artifact_named(self, name: str) -> ArtifactRecord | None:
        return next((a for a in self.artifacts if a.name == name), None)


def generate_report(
    run_id: RunId,
    *,
    store: RunStore,
    artifacts: ArtifactStore,
    scratch_root: Path,
    render_html: HtmlRenderer,
) -> ReportBundle:
    """Write the report bundle for a finished run and store it as artifacts."""
    record = store.get_run(run_id)
    if not record.is_terminal:
        raise NotFoundError(
            f"Run {run_id} is {record.status.value}; a report is written once a "
            "run has finished."
        )

    existing = artifacts.list_artifacts(run_id)
    document = build_document(record, store, existing, artifacts)

    scratch = scratch_root / str(run_id) / "report"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / REPORT_JSON).write_text(
        document.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (scratch / REPORT_HTML).write_text(render_html(document), encoding="utf-8")
    (scratch / PROVENANCE_JSON).write_text(
        json.dumps(_provenance(record, existing), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (scratch / CHECKSUMS_TXT).write_text(_checksums(existing), encoding="utf-8")

    stored = [
        artifacts.store(scratch / REPORT_JSON, kind=ArtifactKind.REPORT, run_id=run_id),
        artifacts.store(scratch / REPORT_HTML, kind=ArtifactKind.REPORT, run_id=run_id),
        artifacts.store(
            scratch / PROVENANCE_JSON, kind=ArtifactKind.PROVENANCE, run_id=run_id
        ),
        artifacts.store(
            scratch / CHECKSUMS_TXT, kind=ArtifactKind.CHECKSUMS, run_id=run_id
        ),
    ]
    return ReportBundle(run_id=run_id, document=document, artifacts=tuple(stored))


def build_document(
    record: RunRecord,
    store: RunStore,
    existing: tuple[ArtifactRecord, ...],
    artifacts: ArtifactStore,
) -> ReportDocument:
    experiment_section = _experiment_section(record, existing, artifacts)
    results = tuple(a for a in existing if a.kind is ArtifactKind.RESULT)
    wall_time = (
        (record.completed_at - record.started_at).total_seconds()
        if record.started_at and record.completed_at
        else None
    )
    test_results = tuple(
        result
        for result in store.list_test_results(record.project_id)
        if result.started_at <= record.created_at
    )
    return ReportDocument(
        generated_at=datetime.now(UTC),
        run=record,
        experiment=experiment_section,
        datasets=tuple(
            {"id": str(pin.id), "version": pin.version} for pin in record.datasets
        ),
        code=record.code.model_dump(mode="json"),
        container=record.container.model_dump(mode="json"),
        parameters=record.parameters,
        seeds=record.seeds,
        resource_usage=ResourceUsage(
            requested_cpus=record.resources.cpus,
            requested_memory_mb=record.resources.memory_mb,
            requested_gpus=record.resources.gpus,
            time_limit=record.resources.time_limit,
            wall_time_seconds=wall_time,
        ),
        test_results=test_results,
        outputs=results,
        metrics=_metrics(results, artifacts),
        deviations=record.deviations,
        limitations=None,
        reproduction_command=_reproduction_command(record),
        references=experiment_section.references,
    )


def _experiment_section(
    record: RunRecord, existing: tuple[ArtifactRecord, ...], artifacts: ArtifactStore
) -> ExperimentSection:
    """Scientific context, read back from the manifest snapshot of the run."""
    import yaml

    snapshot = next((a for a in existing if a.kind is ArtifactKind.SNAPSHOT), None)
    scientific: dict[str, Any] = {}
    title = str(record.experiment_id)
    if snapshot is not None:
        path = artifacts.resolve(snapshot)
        if path.is_file():
            documents = [
                d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d
            ]
            experiment = next(
                (d for d in documents if d.get("kind") == "Experiment"), None
            )
            if experiment is not None:
                scientific = experiment.get("scientific", {})
                title = experiment.get("metadata", {}).get("title", title)
    return ExperimentSection(
        id=str(record.experiment_id),
        title=title,
        question=scientific.get("question", "Not recorded."),
        hypothesis=scientific.get("hypothesis", "Not recorded."),
        references=tuple(scientific.get("references", ())),
    )


def _metrics(
    results: tuple[ArtifactRecord, ...], artifacts: ArtifactStore
) -> dict[str, Any]:
    """Metrics the run itself reported, by convention in ``metrics.json``."""
    metrics_artifact = next((a for a in results if a.name == METRICS_FILENAME), None)
    if metrics_artifact is None:
        return {}
    path = artifacts.resolve(metrics_artifact)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _provenance(
    record: RunRecord, existing: tuple[ArtifactRecord, ...]
) -> dict[str, Any]:
    return {
        "run": record.model_dump(mode="json"),
        "artifacts": [
            {
                "id": str(a.id),
                "name": a.name,
                "kind": a.kind.value,
                "checksum": a.checksum,
                "size_bytes": a.size_bytes,
                "uri": a.uri,
            }
            for a in existing
        ],
    }


def _checksums(existing: tuple[ArtifactRecord, ...]) -> str:
    lines = [
        f"{a.checksum.removeprefix('sha256:')}  {a.name}"
        for a in sorted(existing, key=lambda a: a.name)
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def _reproduction_command(record: RunRecord) -> str:
    """The command that reproduces this run from the recorded metadata."""
    parts = ["lab run", f"--experiment {record.experiment_id}", "--backend local"]
    if record.status is RunStatus.COMPLETED and not record.container.digest:
        parts.append("--no-container")
    return " ".join(parts)
