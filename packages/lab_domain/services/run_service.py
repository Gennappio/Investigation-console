"""Execution of an experiment (`lab run`).

The run record is written before anything executes and advanced through the
state machine of AGENTS.md section 16.3 as the execution progresses, so an
interrupted command still leaves a truthful record behind.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import BaseModel, ConfigDict

from lab_domain.artifacts import ArtifactKind, ArtifactRecord
from lab_domain.containers import ContainerEngine, ContainerRunSpec, Mount
from lab_domain.errors import CollectionFailedError, ExecutionFailedError
from lab_domain.execution import ExecutionBackend, JobState, JobStatus, RunRequest
from lab_domain.ids import RunId
from lab_domain.manifests.models import ExperimentManifest, ResourceSpec
from lab_domain.manifests.quantities import parse_memory_to_mb, time_limit_to_seconds
from lab_domain.runs import (
    CodeRef,
    ContainerRef,
    DatasetPin,
    ResourceRequest,
    RunRecord,
    RunStatus,
    configuration_hash,
)
from lab_domain.services.workspace_context import WorkspaceContext, describe_code
from lab_domain.storage import ArtifactStore, RunStore

POLL_INTERVAL_SECONDS = 0.05
CONFIG_FILENAME = "config.yaml"
SNAPSHOT_FILENAME = "manifest.snapshot.yaml"
CONTAINER_WORKDIR = "/scratch"
CONTAINER_PROJECT_DIR = "/workspace"

DEVIATION_NO_CONTAINER = (
    "Executed directly on the host although the repository declares a container."
)
DEVIATION_NO_VCS = "Code was not under version control, so no commit was recorded."
DEVIATION_DIRTY_TREE = (
    "The working tree had uncommitted changes; the recorded commit is incomplete."
)


class AuditSink(Protocol):
    def record(self, action: str, actor: str, **context: Any) -> None: ...


class RunOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    run: RunRecord
    artifacts: tuple[ArtifactRecord, ...]


def scratch_directory(home: Path, run_id: str) -> Path:
    """Temporary working area of a run; permanent storage is separate."""
    return home / "work" / run_id


def execute_run(
    context: WorkspaceContext,
    *,
    backend: ExecutionBackend,
    store: RunStore,
    artifacts: ArtifactStore,
    audit: AuditSink,
    home: Path,
    actor: str,
    engine: ContainerEngine | None = None,
    use_container: bool = True,
) -> RunOutcome:
    """Execute the experiment once and record everything about it."""
    command = context.repository.spec.commands.get("run")
    if not command:
        raise ExecutionFailedError(
            "lab.yaml defines no `run` command profile, so there is nothing to execute."
        )

    experiment = context.experiment
    code = describe_code(context.root)
    deviations = _deviations(code)

    container_ref = ContainerRef()
    container_spec: ContainerRunSpec | None = None
    declared = context.repository.spec.container
    if declared is not None and use_container:
        container_ref, container_spec = _prepare_container(context, engine)
    elif declared is not None:
        deviations.append(DEVIATION_NO_CONTAINER)

    resources = _resource_request(experiment)
    datasets = tuple(
        DatasetPin(id=ref.id, version=ref.version or "")
        for ref in experiment.execution.dataset_refs
    )
    seeds = experiment.execution.seeds.values if experiment.execution.seeds else ()

    run_id = store.allocate_run_id()
    record = RunRecord(
        id=run_id,
        experiment_id=experiment.metadata.id,
        project_id=context.repository.spec.project,
        status=RunStatus.CREATED,
        backend=backend.name,
        code=code,
        container=container_ref,
        datasets=datasets,
        configuration_hash=configuration_hash(
            {
                "command": list(command),
                "container_digest": container_ref.digest,
                "datasets": [d.model_dump(mode="json") for d in datasets],
                "parameters": experiment.execution.parameters,
                "resources": resources.model_dump(mode="json"),
                "seeds": list(seeds),
            }
        ),
        parameters=dict(experiment.execution.parameters),
        seeds=tuple(seeds),
        resources=resources,
        command=command,
        submitted_by=actor,
        created_at=datetime.now(UTC),
        deviations=tuple(deviations),
    )
    store.save_run(record)
    audit.record(
        "run.created", actor=actor, run_id=run_id, experiment=record.experiment_id
    )

    scratch = scratch_directory(home, str(run_id))
    outputs = scratch / (
        context.repository.spec.outputs.directory
        if context.repository.spec.outputs
        else "results"
    )
    logs = scratch / "logs"
    config_path = _write_run_config(scratch, record, experiment)
    snapshot_path = _write_manifest_snapshot(scratch, context)

    record = record.transitioned_to(RunStatus.VALIDATED)
    store.save_run(record)

    environment = {
        "LAB_RUN_ID": str(run_id),
        "LAB_EXPERIMENT_ID": str(experiment.metadata.id),
        "LAB_PROJECT_DIR": str(context.root),
        "LAB_EXPERIMENT_CONFIG": str(config_path),
        "LAB_OUTPUT_DIR": str(outputs),
        "PYTHONPATH": str(context.root / "src"),
    }
    if container_spec is not None:
        container_spec = container_spec.model_copy(
            update={
                "environment": {
                    **environment,
                    "LAB_PROJECT_DIR": CONTAINER_PROJECT_DIR,
                    "LAB_EXPERIMENT_CONFIG": f"{CONTAINER_WORKDIR}/{CONFIG_FILENAME}",
                    "LAB_OUTPUT_DIR": f"{CONTAINER_WORKDIR}/{outputs.name}",
                    "PYTHONPATH": f"{CONTAINER_PROJECT_DIR}/src",
                }
            }
        )

    request = RunRequest(
        run_id=run_id,
        argv=command,
        environment=environment,
        working_directory=scratch,
        output_directory=outputs,
        log_directory=logs,
        timeout_seconds=(
            time_limit_to_seconds(resources.time_limit)
            if resources.time_limit
            else None
        ),
        container=container_spec,
    )

    record = record.transitioned_to(RunStatus.QUEUED)
    store.save_run(record)
    try:
        submission = backend.submit(request)
    except ExecutionFailedError as exc:
        record = record.transitioned_to(
            RunStatus.FAILED,
            completed_at=datetime.now(UTC),
            failure_reason=str(exc),
        )
        store.save_run(record)
        audit.record("run.failed", actor=actor, run_id=run_id, reason=str(exc))
        raise

    record = record.transitioned_to(
        RunStatus.RUNNING,
        started_at=submission.submitted_at,
        external_job_id=submission.external_job_id,
    )
    store.save_run(record)
    audit.record(
        "run.submitted",
        actor=actor,
        run_id=run_id,
        backend=backend.name,
        job=submission.external_job_id,
    )

    status = _wait_for_completion(backend, submission.external_job_id)
    collection = backend.collect(submission.external_job_id)

    try:
        stored = _collect_artifacts(
            artifacts,
            run_id,
            collection.stdout_path,
            collection.stderr_path,
            collection.output_paths,
            snapshot_path,
        )
    except CollectionFailedError:
        record = record.transitioned_to(
            RunStatus.FAILED,
            completed_at=datetime.now(UTC),
            exit_code=collection.exit_code,
            failure_reason="Outputs could not be collected into permanent storage.",
        )
        store.save_run(record)
        audit.record("run.failed", actor=actor, run_id=run_id, reason="collection")
        raise

    completed_at = status.completed_at or datetime.now(UTC)
    if status.state is JobState.COMPLETED:
        record = record.transitioned_to(
            RunStatus.COMPLETED,
            completed_at=completed_at,
            exit_code=collection.exit_code,
            artifacts=tuple(record.artifacts) + tuple(a.id for a in stored),
        )
        audit.record("run.completed", actor=actor, run_id=run_id)
    elif status.state is JobState.CANCELLED:
        record = record.transitioned_to(
            RunStatus.CANCELLED,
            completed_at=completed_at,
            exit_code=collection.exit_code,
            artifacts=tuple(record.artifacts) + tuple(a.id for a in stored),
            failure_reason=status.detail,
        )
        audit.record("run.cancelled", actor=actor, run_id=run_id)
    else:
        record = record.transitioned_to(
            RunStatus.FAILED,
            completed_at=completed_at,
            exit_code=collection.exit_code,
            artifacts=tuple(record.artifacts) + tuple(a.id for a in stored),
            failure_reason=status.detail or f"Exit code {collection.exit_code}.",
        )
        audit.record("run.failed", actor=actor, run_id=run_id, reason=status.detail)

    store.save_run(record)
    return RunOutcome(run=record, artifacts=tuple(stored))


def _wait_for_completion(backend: ExecutionBackend, job_id: str) -> JobStatus:
    while True:
        status = backend.status(job_id)
        if status.state is not JobState.RUNNING:
            return status
        time.sleep(POLL_INTERVAL_SECONDS)


def _deviations(code: CodeRef) -> list[str]:
    deviations = []
    if code.commit is None:
        deviations.append(DEVIATION_NO_VCS)
    elif code.dirty:
        deviations.append(DEVIATION_DIRTY_TREE)
    return deviations


def _prepare_container(
    context: WorkspaceContext, engine: ContainerEngine | None
) -> tuple[ContainerRef, ContainerRunSpec]:
    from lab_domain.services.build_service import image_tag

    if engine is None:
        raise ExecutionFailedError(
            "This repository declares a container but no container engine is "
            "configured. Run with --no-container to execute on the host."
        )
    reference = image_tag(context)
    image = engine.inspect(reference)
    spec = ContainerRunSpec(
        image=image.reference,
        digest=image.digest,
        workdir=CONTAINER_WORKDIR,
        mounts=(
            Mount(source=context.root, target=CONTAINER_PROJECT_DIR, read_only=True),
        ),
    )
    return ContainerRef(image=image.reference, digest=image.digest), spec


def _resource_request(experiment: ExperimentManifest) -> ResourceRequest:
    resources: ResourceSpec | None = experiment.execution.resources
    if resources is None:  # pragma: no cover - validation rejects this earlier
        raise ExecutionFailedError("The experiment requests no resources.")
    return ResourceRequest(
        cpus=resources.cpus,
        memory_mb=parse_memory_to_mb(resources.memory),
        gpus=resources.gpus,
        time_limit=resources.time_limit,
    )


def _write_run_config(
    scratch: Path, record: RunRecord, experiment: ExperimentManifest
) -> Path:
    """Flat configuration file handed to the command via LAB_EXPERIMENT_CONFIG."""
    document: dict[str, Any] = {
        "run_id": str(record.id),
        "experiment_id": str(experiment.metadata.id),
        **record.parameters,
    }
    if record.seeds:
        document["seed"] = record.seeds[0]
        document["seeds"] = list(record.seeds)
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / CONFIG_FILENAME
    lines = [f"{key}: {json.dumps(value)}" for key, value in document.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_manifest_snapshot(scratch: Path, context: WorkspaceContext) -> Path:
    """Exact manifests this run executed, kept with the run for reproduction."""
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / SNAPSHOT_FILENAME
    documents = [
        context.repository.model_dump(mode="json", by_alias=True),
        context.experiment.model_dump(mode="json", by_alias=True),
    ]
    path.write_text(yaml.safe_dump_all(documents, sort_keys=False), encoding="utf-8")
    return path


def _collect_artifacts(
    artifacts: ArtifactStore,
    run_id: RunId,
    stdout_path: Path,
    stderr_path: Path,
    output_paths: tuple[Path, ...],
    snapshot_path: Path,
) -> list[ArtifactRecord]:
    stored = []
    for path in (stdout_path, stderr_path):
        if path.is_file():
            stored.append(artifacts.store(path, kind=ArtifactKind.LOG, run_id=run_id))
    for path in output_paths:
        stored.append(artifacts.store(path, kind=ArtifactKind.RESULT, run_id=run_id))
    stored.append(
        artifacts.store(snapshot_path, kind=ArtifactKind.SNAPSHOT, run_id=run_id)
    )
    return stored
