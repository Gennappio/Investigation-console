"""`lab run`: execute an experiment and record the run."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lab_cli.exit_codes import ExitCode
from lab_cli.identifiers import parse_optional_id
from lab_cli.options import EXPERIMENT_OPTION, JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_cli.runtime import (
    actor,
    default_artifact_store,
    default_audit_log,
    default_container_engine,
    default_execution_backend,
    default_run_store,
    lab_home,
)
from lab_domain.errors import ExecutionFailedError
from lab_domain.ids import ExperimentId
from lab_domain.runs import RunStatus
from lab_domain.services import RunOutcome, execute_run, load_validated_workspace
from lab_domain.workspace import find_workspace_root

SUPPORTED_BACKENDS = ("local",)


def run(
    backend: Annotated[
        str, typer.Option("--backend", help="Execution backend.")
    ] = "local",
    json_output: Annotated[bool, JSON_OPTION] = False,
    experiment: Annotated[str | None, EXPERIMENT_OPTION] = None,
    no_container: Annotated[
        bool,
        typer.Option(
            "--no-container",
            help="Execute on the host; recorded as a deviation from protocol.",
        ),
    ] = False,
) -> None:
    """Execute the experiment once, then collect its outputs."""

    def action() -> RunOutcome:
        if backend not in SUPPORTED_BACKENDS:
            raise ExecutionFailedError(
                f"Unknown backend {backend!r}. Available: "
                f"{', '.join(SUPPORTED_BACKENDS)}. SLURM arrives in Milestone 3."
            )
        chosen = parse_optional_id(ExperimentId, experiment)
        context = load_validated_workspace(find_workspace_root(Path.cwd()), chosen)
        return execute_run(
            context,
            backend=default_execution_backend(),
            store=default_run_store(),
            artifacts=default_artifact_store(),
            audit=default_audit_log(),
            home=lab_home(),
            actor=actor(),
            engine=default_container_engine(),
            use_container=not no_container,
        )

    outcome = run_or_fail(json_output, action)
    record = outcome.run
    emit(
        {
            "run_id": str(record.id),
            "status": record.status.value,
            "backend": record.backend,
            "experiment_id": str(record.experiment_id),
            "exit_code": record.exit_code,
            "container_digest": record.container.digest,
            "configuration_hash": record.configuration_hash,
            "resources": record.resources.model_dump(mode="json"),
            "artifacts": [str(a.id) for a in outcome.artifacts],
            "deviations": list(record.deviations),
        },
        _render(outcome),
        json_output,
    )
    raise typer.Exit(
        int(
            ExitCode.OK
            if record.status is RunStatus.COMPLETED
            else ExitCode.EXECUTION_FAILED
        )
    )


def _render(outcome: RunOutcome) -> str:
    record = outcome.run
    lines = [
        f"{record.id}: {record.status.value} (exit code {record.exit_code})",
        f"  backend:    {record.backend}",
        f"  experiment: {record.experiment_id}",
        f"  container:  {record.container.digest or 'none: executed on the host'}",
        f"  config:     {record.configuration_hash}",
        f"  resources:  {record.resources.cpus} cpus, "
        f"{record.resources.memory_mb} MB, "
        f"limit {record.resources.time_limit or 'none'}",
        f"  artifacts:  {len(outcome.artifacts)}",
    ]
    lines += [f"    {a.id}  {a.name}" for a in outcome.artifacts]
    if record.deviations:
        lines.append("  deviations:")
        lines += [f"    - {deviation}" for deviation in record.deviations]
    if record.failure_reason:
        lines.append(f"  failure:    {record.failure_reason}")
    lines.append(f"\nNext: lab report {record.id}")
    return "\n".join(lines)
