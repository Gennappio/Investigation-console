"""`lab cancel`: stop a run that has not finished."""

from __future__ import annotations

from typing import Annotated

import typer

from lab_cli.exit_codes import ExitCode
from lab_cli.identifiers import parse_id
from lab_cli.options import JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_cli.runtime import (
    actor,
    default_artifact_store,
    default_audit_log,
    default_policy,
    default_run_store,
    execution_backend,
    lab_home,
)
from lab_domain.ids import RunId
from lab_domain.services import RunOutcome, cancel_run


def cancel(
    run_id: Annotated[str, typer.Argument(help="Run identifier, e.g. RUN-000001.")],
    json_output: Annotated[bool, JSON_OPTION] = False,
) -> None:
    """Cancel a queued or running job and record the outcome."""

    def action() -> RunOutcome:
        store = default_run_store()
        record = store.get_run(parse_id(RunId, run_id))
        return cancel_run(
            record,
            backend=execution_backend(record.backend),
            store=store,
            artifacts=default_artifact_store(),
            audit=default_audit_log(),
            home=lab_home(),
            actor=actor(),
            policy=default_policy(),
        )

    outcome = run_or_fail(json_output, action)
    record = outcome.run
    emit(
        {
            "run_id": str(record.id),
            "status": record.status.value,
            "external_job_id": record.external_job_id,
            "failure_reason": record.failure_reason,
        },
        f"{record.id}: {record.status.value}"
        + (f" ({record.failure_reason})" if record.failure_reason else ""),
        json_output,
    )
    raise typer.Exit(int(ExitCode.OK))
