"""The operations an agent is offered, in one place.

The MCP adapter and any future IDE integration expose these; none of them adds
behaviour. Each operation is a thin call into :class:`LabClient`, which is
itself a thin call into the CLI, so there is one implementation of what
"publish a component" means no matter who asks (AGENTS.md section 2.6).

Each operation carries a real, annotated signature, because that signature is
what an agent sees as the tool's schema: a wrapper that takes ``**kwargs``
tells a caller nothing about what to pass.

Read operations come first deliberately. An agent should be able to look at a
laboratory's record without being able to spend its cluster time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lab_api_client.client import LabClient


@dataclass(frozen=True)
class Operation:
    name: str
    description: str
    call: Callable[..., dict[str, Any]]
    # Whether it changes a laboratory's record or spends its resources.
    writes: bool


def read_operations(client: LabClient) -> tuple[Operation, ...]:
    def lab_validate() -> dict[str, Any]:
        return client.validate()

    def lab_inspect() -> dict[str, Any]:
        return client.inspect()

    def lab_status(run_id: str) -> dict[str, Any]:
        return client.status(run_id)

    def lab_search_components(
        query: str = "", status: str | None = None
    ) -> dict[str, Any]:
        return client.search_components(query, status=status)

    return (
        Operation(
            name="lab_validate",
            description=(
                "Validate the manifests of the repository in the working "
                "directory. Returns {valid, errors, warnings}; each error "
                "carries a stable code, a path and a message."
            ),
            call=lab_validate,
            writes=False,
        ),
        Operation(
            name="lab_inspect",
            description=(
                "Summarise the repository: project, runtime, command profiles "
                "and experiments."
            ),
            call=lab_inspect,
            writes=False,
        ),
        Operation(
            name="lab_status",
            description=(
                "What is recorded about a run, including its artifacts and "
                "their checksums. This is the source of truth for a run's "
                "status, exit code, commit, container digest and deviations."
            ),
            call=lab_status,
            writes=False,
        ),
        Operation(
            name="lab_search_components",
            description=(
                "Search the component registry. Each result carries its "
                "maturity and the test evidence behind it; maturity without "
                "that evidence means nothing."
            ),
            call=lab_search_components,
            writes=False,
        ),
    )


def write_operations(client: LabClient) -> tuple[Operation, ...]:
    def lab_test(profile: str = "test") -> dict[str, Any]:
        return client.test(profile)

    def lab_run(
        backend: str = "local", no_container: bool = False, wait: bool = False
    ) -> dict[str, Any]:
        return client.run(backend=backend, no_container=no_container, wait=wait)

    def lab_report(run_id: str) -> dict[str, Any]:
        return client.report(run_id)

    def lab_publish_component(name: str | None = None) -> dict[str, Any]:
        return client.publish_component(name)

    return (
        Operation(
            name="lab_test",
            description=(
                "Run a command profile and record the evidence. A failing "
                "suite is a recorded result, not an error."
            ),
            call=lab_test,
            writes=True,
        ),
        Operation(
            name="lab_run",
            description=(
                "Execute the experiment and collect its outputs. Spends "
                "compute; a local run blocks until it finishes."
            ),
            call=lab_run,
            writes=True,
        ),
        Operation(
            name="lab_report",
            description="Write the report bundle of a finished run.",
            call=lab_report,
            writes=True,
        ),
        Operation(
            name="lab_publish_component",
            description=(
                "Publish a component with the evidence recorded for it. Never "
                "grants validated or lab_standard: those need a human review."
            ),
            call=lab_publish_component,
            writes=True,
        ),
    )


def operations(
    client: LabClient, *, allow_writes: bool = False
) -> tuple[Operation, ...]:
    """What to offer an agent. Writing is opt-in."""
    if allow_writes:
        return (*read_operations(client), *write_operations(client))
    return read_operations(client)


def client_for(workspace: Path | None = None, home: Path | None = None) -> LabClient:
    return LabClient(cwd=workspace, home=home)
