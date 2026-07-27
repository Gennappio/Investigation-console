"""Milestone 6 (AGENTS.md section 19): an external agent needs no special
integration.

The client, the MCP adapter and the API are checked here against a real
repository, driving the same commands a researcher would run by hand.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from lab_api_client import LabClient, LabCommandError
from lab_api_client.operations import operations

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPOSITORY_ROOT / "packages"
TEMPLATES = REPOSITORY_ROOT / "templates"


@pytest.fixture
def lab(tmp_path: Path) -> Iterator[LabClient]:
    """A client pointed at a scratch platform state and a fresh repository."""
    environment = {
        "PYTHONPATH": str(PACKAGES),
        "LAB_TEMPLATES_DIR": str(TEMPLATES),
    }
    home = tmp_path / "lab-home"
    bootstrap = LabClient(cwd=tmp_path, home=home, environment=environment)
    created = bootstrap.init("demo")
    assert created["project_id"] == "PRJ-000001"
    yield LabClient(cwd=tmp_path / "demo", home=home, environment=environment)


def test_the_client_reads_what_the_platform_recorded(lab: LabClient) -> None:
    assert lab.validate() == {"valid": True, "errors": [], "warnings": []}

    workspace = lab.inspect()
    assert workspace["project_id"] == "PRJ-000001"
    assert "smoke" in workspace["commands"]

    executed = lab.run(no_container=True)
    assert executed["status"] == "completed"
    run_id = executed["run_id"]

    recorded = lab.status(run_id)
    assert recorded["id"] == run_id
    assert recorded["exit_code"] == 0
    assert {a["name"] for a in recorded["artifacts"]} >= {"metrics.json"}
    assert all(a["checksum"].startswith("sha256:") for a in recorded["artifacts"])


def test_recorded_failures_are_returned_not_raised(
    lab: LabClient, tmp_path: Path
) -> None:
    """A failed run and a failed suite are results; the record exists."""
    manifest = tmp_path / "demo" / "lab.yaml"
    manifest.write_text(
        manifest.read_text().replace(
            "    run:\n      - python\n      - -m\n      - demo.run\n"
            '      - --config\n      - "${LAB_EXPERIMENT_CONFIG}"\n',
            "    run:\n      - python\n      - -c\n      - raise SystemExit(3)\n",
        )
    )
    failed = lab.run(no_container=True)
    assert failed["status"] == "failed"
    assert failed["exit_code"] == 3
    assert lab.status(failed["run_id"])["status"] == "failed"


def test_other_failures_raise_with_the_stable_code(lab: LabClient) -> None:
    with pytest.raises(LabCommandError) as raised:
        lab.status("RUN-000999")
    assert raised.value.exit_code == 11
    assert raised.value.code == "NOT_FOUND"

    with pytest.raises(LabCommandError) as malformed:
        lab.status("nonsense")
    assert malformed.value.exit_code == 2


def test_the_registry_is_reachable_from_python(lab: LabClient) -> None:
    lab.test("smoke")
    published = lab.publish_component()
    assert published["maturity"] == "runnable"

    found = lab.search_components("sensitivity analysis")
    assert found["count"] == 1
    component = found["results"][0]
    assert component["id"] == published["component_id"]
    assert component["evidence"], "maturity is meaningless without its evidence"

    promoted = lab.promote_component(
        component["id"],
        to="validated",
        note="Reviewed against the reference dataset.",
        reviewer="pi.rossi",
    )
    assert promoted["maturity"] == "validated"
    assert promoted["decision_id"].startswith("DEC-")


def test_the_agent_operations_are_read_only_until_asked(lab: LabClient) -> None:
    read_only = {operation.name for operation in operations(lab)}
    everything = {operation.name for operation in operations(lab, allow_writes=True)}

    assert read_only == {
        "lab_validate",
        "lab_inspect",
        "lab_status",
        "lab_search_components",
    }
    assert everything - read_only == {
        "lab_test",
        "lab_run",
        "lab_report",
        "lab_publish_component",
    }
    assert not any(operation.writes for operation in operations(lab))


def test_an_operation_returns_the_cli_payload_unchanged(lab: LabClient) -> None:
    """The adapter adds nothing: what a tool returns is what the CLI printed."""
    validate = next(o for o in operations(lab) if o.name == "lab_validate")
    assert validate.call() == lab.validate()


def test_the_mcp_server_offers_the_operations_as_tools(lab: LabClient) -> None:
    import asyncio

    pytest.importorskip("mcp", reason="needs the mcp extra")
    from lab_api_client.mcp_server import build_server

    server = build_server(lab, allow_writes=True)
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}

    assert "lab_status" in names
    assert "lab_run" in names
    assert all(tool.description for tool in tools)

    read_only = asyncio.run(build_server(lab).list_tools())
    assert "lab_run" not in {tool.name for tool in read_only}


def test_the_mcp_adapter_reports_platform_errors_as_data(lab: LabClient) -> None:
    import asyncio

    pytest.importorskip("mcp", reason="needs the mcp extra")
    from lab_api_client.mcp_server import build_server

    server = build_server(lab)
    answer = asyncio.run(server.call_tool("lab_status", {"run_id": "RUN-000999"}))
    payload = json.loads(_text_of(answer))

    assert payload["status"] == "error"
    assert payload["code"] == "NOT_FOUND"
    assert payload["exit_code"] == 11


def test_the_api_serves_the_same_records(lab: LabClient, tmp_path: Path) -> None:
    pytest.importorskip("fastapi", reason="needs the api extra")
    from fastapi.testclient import TestClient

    lab.run(no_container=True)
    lab.test("smoke")
    lab.publish_component()

    os.environ["LAB_HOME"] = str(tmp_path / "lab-home")
    sys.path.insert(0, str(REPOSITORY_ROOT / "apps"))
    from api.main import app

    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"

    runs = client.get("/v1/runs").json()
    assert runs["count"] == 1
    summary = runs["results"][0]
    assert summary["uri"] == f"lab-run://{summary['id']}"
    assert summary["report_uri"].startswith("lab-report://")

    detail = client.get(f"/v1/runs/{summary['id']}").json()
    assert detail["status"] == "completed"
    assert all(a["uri"].startswith("lab-artifact://") for a in detail["artifacts"])
    # Operational paths are not published (AGENTS.md section 14).
    assert "file://" not in json.dumps(detail)
    assert str(tmp_path) not in json.dumps(detail)

    components = client.get("/v1/components", params={"q": "sensitivity"}).json()
    assert components["count"] == 1
    assert components["results"][0]["evidence"]

    missing = client.get("/v1/runs/RUN-000999")
    assert missing.status_code == 404
    assert missing.json()["code"] == "NOT_FOUND"


def test_the_api_does_not_offer_writes(tmp_path: Path) -> None:
    """Executing and publishing need an authorization model the platform
    does not have yet, so the API reports and the CLI acts (ADR 0011)."""
    pytest.importorskip("fastapi", reason="needs the api extra")
    sys.path.insert(0, str(REPOSITORY_ROOT / "apps"))
    from api.main import app

    methods = {
        method.upper()
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    assert methods <= {"GET", "HEAD"}


def _text_of(answer: object) -> str:
    """The text of an MCP tool result, across return shapes."""
    content = answer[0] if isinstance(answer, tuple) else answer
    first = content[0] if isinstance(content, list) else content
    return str(getattr(first, "text", first))
