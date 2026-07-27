"""`lab status`: what is recorded about a run.

For a backend that outlives the submitting process, this is also where a
finished job is reconciled: its state is read from the scheduler and, once it
has ended, its outputs are collected into permanent storage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lab_cli.exit_codes import ExitCode
from lab_cli.identifiers import parse_id
from lab_cli.options import JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_cli.projection import describe, note_payload, project_after
from lab_cli.runtime import (
    actor,
    default_artifact_store,
    default_audit_log,
    default_policy,
    default_run_store,
    execution_backend,
    lab_home,
)
from lab_domain.artifacts import ArtifactRecord
from lab_domain.ids import RunId
from lab_domain.runs import RunRecord
from lab_domain.services import refresh_run


def status(
    run_id: Annotated[str, typer.Argument(help="Run identifier, e.g. RUN-000001.")],
    json_output: Annotated[bool, JSON_OPTION] = False,
    no_refresh: Annotated[
        bool,
        typer.Option(
            "--no-refresh", help="Report what is stored without asking the backend."
        ),
    ] = False,
) -> None:
    """Show the recorded status, provenance and artifacts of a run."""

    def action() -> tuple[RunRecord, tuple[ArtifactRecord, ...]]:
        store = default_run_store()
        artifacts = default_artifact_store()
        record = store.get_run(parse_id(RunId, run_id))
        if not no_refresh and not record.is_terminal and record.external_job_id:
            outcome = refresh_run(
                record,
                backend=execution_backend(record.backend),
                store=store,
                artifacts=artifacts,
                audit=default_audit_log(),
                home=lab_home(),
                actor=actor(),
                policy=default_policy(),
            )
            record = outcome.run
        return record, artifacts.list_artifacts(record.id)

    record, artifacts = run_or_fail(json_output, action)
    projected = project_after(record, Path.cwd())
    emit(
        {
            **record.model_dump(mode="json"),
            "artifacts": [
                {
                    "id": str(a.id),
                    "kind": a.kind.value,
                    "name": a.name,
                    "checksum": a.checksum,
                    "size_bytes": a.size_bytes,
                    "uri": a.uri,
                }
                for a in artifacts
            ],
            "notes": note_payload(projected),
        },
        "\n".join([_render(record, artifacts), *describe(projected)]),
        json_output,
    )
    raise typer.Exit(int(ExitCode.OK))


def _render(record: RunRecord, artifacts: tuple[ArtifactRecord, ...]) -> str:
    lines = [
        f"{record.id}: {record.status.value}",
        f"  experiment: {record.experiment_id}   project: {record.project_id}",
        f"  backend:    {record.backend}   job: {record.external_job_id or '—'}",
        f"  submitted:  {record.submitted_by} at {record.created_at}",
        f"  started:    {record.started_at or '—'}",
        f"  completed:  {record.completed_at or '—'}   exit code: {record.exit_code}",
        f"  commit:     {record.code.commit or 'not under version control'}",
        f"  container:  {record.container.digest or 'none: executed on the host'}",
        f"  config:     {record.configuration_hash}",
    ]
    if artifacts:
        lines.append(f"  artifacts ({len(artifacts)}):")
        lines += [f"    {a.id}  {a.kind.value:<10} {a.name}" for a in artifacts]
    else:
        lines.append("  artifacts: none")
    if record.deviations:
        lines.append("  deviations:")
        lines += [f"    - {deviation}" for deviation in record.deviations]
    if record.failure_reason:
        lines.append(f"  failure:    {record.failure_reason}")
    return "\n".join(lines)
