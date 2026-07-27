"""Stable laboratory URIs (AGENTS.md section 2.4).

An identifier is the canonical handle for an object; a URI is that identifier
in a form something else can link to. Neither is a filesystem path: where the
bytes currently live is the platform's business and may change.

The scheme was reserved by ADR 0002 and is implemented here now that runs,
artifacts and reports exist to point at (ADR 0010).
"""

from __future__ import annotations

import re

from lab_domain.ids import (
    ArtifactId,
    ComponentId,
    DatasetId,
    DecisionId,
    ExperimentId,
    ProjectId,
    RunId,
    TypedId,
    WorkflowId,
)

SCHEMES: dict[type[TypedId], str] = {
    ProjectId: "lab-project",
    ExperimentId: "lab-experiment",
    RunId: "lab-run",
    ComponentId: "lab-component",
    WorkflowId: "lab-workflow",
    DatasetId: "lab-dataset",
    ArtifactId: "lab-artifact",
    DecisionId: "lab-decision",
}

_BY_SCHEME = {scheme: id_type for id_type, scheme in SCHEMES.items()}
_URI = re.compile(
    r"^(?P<scheme>lab-[a-z]+)://(?P<identifier>[A-Z]+-\d+)(?P<path>/.*)?$"
)

REPORT_SCHEME = "lab-report"
ARTIFACTS_PATH = "/artifacts"


def lab_uri(identifier: TypedId, path: str = "") -> str:
    """The URI of an object, optionally of something within it."""
    scheme = SCHEMES.get(type(identifier))
    if scheme is None:
        raise ValueError(f"No URI scheme for {type(identifier).__name__}.")
    return f"{scheme}://{identifier}{path}"


def report_uri(run_id: RunId) -> str:
    """Where the report of a run is addressed from (AGENTS.md section 12.2)."""
    return f"{REPORT_SCHEME}://{run_id}"


def artifacts_uri(run_id: RunId) -> str:
    return lab_uri(run_id, ARTIFACTS_PATH)


def parse_lab_uri(uri: str) -> TypedId:
    """The identifier a URI addresses, ignoring any path within it."""
    match = _URI.match(uri.strip())
    if match is None:
        raise ValueError(f"Malformed lab URI {uri!r}.")
    id_type = _BY_SCHEME.get(match["scheme"])
    if id_type is None:
        known = ", ".join(sorted(_BY_SCHEME))
        raise ValueError(f"Unknown URI scheme in {uri!r}. Known: {known}.")
    return id_type(match["identifier"])
