"""`lab run`: execute an experiment and record the run."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lab_cli.exit_codes import ExitCode
from lab_cli.identifiers import parse_optional_id
from lab_cli.options import EXPERIMENT_OPTION, JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_cli.projection import describe, note_payload, project_after
from lab_cli.runtime import (
    BACKENDS,
    LOCAL_BACKEND,
    actor,
    default_artifact_store,
    default_audit_log,
    default_container_engine,
    default_policy,
    default_run_store,
    execution_backend,
    lab_home,
)
from lab_domain.ids import ExperimentId
from lab_domain.runs import RunRecord, RunStatus
from lab_domain.services import (
    RunOutcome,
    load_validated_workspace,
    start_run,
    wait_for_run,
)
from lab_domain.workspace import find_workspace_root


def run(
    backend: Annotated[
        str,
        typer.Option("--backend", help=f"Execution backend: {', '.join(BACKENDS)}."),
    ] = LOCAL_BACKEND,
    json_output: Annotated[bool, JSON_OPTION] = False,
    experiment: Annotated[str | None, EXPERIMENT_OPTION] = None,
    no_container: Annotated[
        bool,
        typer.Option(
            "--no-container",
            help="Execute on the host; recorded as a deviation from protocol.",
        ),
    ] = False,
    wait: Annotated[
        bool,
        typer.Option(
            "--wait",
            help="Poll until the job finishes and collect its outputs.",
        ),
    ] = False,
) -> None:
    """Execute the experiment once.

    A local run always waits. A cluster job is submitted and left to the
    scheduler unless --wait is given; `lab status` collects it once it ends.
    """

    def action() -> RunOutcome | RunRecord:
        chosen = parse_optional_id(ExperimentId, experiment)
        context = load_validated_workspace(find_workspace_root(Path.cwd()), chosen)
        engine = execution_backend(backend)
        started = start_run(
            context,
            backend=engine,
            store=default_run_store(),
            audit=default_audit_log(),
            home=lab_home(),
            actor=actor(),
            policy=default_policy(),
            engine=default_container_engine(backend),
            use_container=not no_container,
        )
        # The local backend owns its child process: nothing else can collect it.
        if wait or backend == LOCAL_BACKEND:
            return wait_for_run(
                started,
                backend=engine,
                store=default_run_store(),
                artifacts=default_artifact_store(),
                audit=default_audit_log(),
                home=lab_home(),
                actor=actor(),
                policy=default_policy(),
            )
        return started

    result = run_or_fail(json_output, action)
    outcome = (
        result
        if isinstance(result, RunOutcome)
        else RunOutcome(run=result, artifacts=())
    )
    record = outcome.run
    projected = project_after(record, Path.cwd())
    emit(
        {
            "run_id": str(record.id),
            "status": record.status.value,
            "backend": record.backend,
            "experiment_id": str(record.experiment_id),
            "external_job_id": record.external_job_id,
            "exit_code": record.exit_code,
            "container_digest": record.container.digest,
            "configuration_hash": record.configuration_hash,
            "resources": record.resources.model_dump(mode="json"),
            "artifacts": [str(a.id) for a in outcome.artifacts],
            "deviations": list(record.deviations),
            "notes": note_payload(projected),
        },
        "\n".join([_render(outcome), *describe(projected)]),
        json_output,
    )
    raise typer.Exit(int(_exit_code(record)))


def _exit_code(record: RunRecord) -> ExitCode:
    if record.status is RunStatus.COMPLETED or not record.is_terminal:
        # A submitted job that has not finished is not a failure.
        return ExitCode.OK
    return ExitCode.EXECUTION_FAILED


def _render(outcome: RunOutcome) -> str:
    record = outcome.run
    lines = [
        f"{record.id}: {record.status.value}"
        + (f" (exit code {record.exit_code})" if record.is_terminal else ""),
        f"  backend:    {record.backend}"
        + (f"   job: {record.external_job_id}" if record.external_job_id else ""),
        f"  experiment: {record.experiment_id}",
        f"  container:  {record.container.digest or 'none: executed on the host'}",
        f"  config:     {record.configuration_hash}",
        f"  resources:  {record.resources.cpus} cpus, "
        f"{record.resources.memory_mb} MB, "
        f"limit {record.resources.time_limit or 'none'}",
    ]
    if outcome.artifacts:
        lines.append(f"  artifacts:  {len(outcome.artifacts)}")
        lines += [f"    {a.id}  {a.name}" for a in outcome.artifacts]
    if record.deviations:
        lines.append("  deviations:")
        lines += [f"    - {deviation}" for deviation in record.deviations]
    if record.failure_reason:
        lines.append(f"  failure:    {record.failure_reason}")
    lines.append(
        f"\nNext: lab report {record.id}"
        if record.is_terminal
        else f"\nNext: lab status {record.id}   (collects the outputs once it ends)"
    )
    return "\n".join(lines)
