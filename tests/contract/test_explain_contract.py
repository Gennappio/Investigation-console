"""`lab explain` at the CLI boundary. No network: the transport is faked."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import Result

from lab_cli.exit_codes import ExitCode

Invoke = Callable[..., Result]
Payload = Callable[[Result], Any]

ANSWER = {
    "model": "vendor/model-served",
    "choices": [
        {"message": {"content": "The run completed."}, "finish_reason": "stop"}
    ],
}


@pytest.fixture
def finished_run(invoke: Invoke, tmp_path: Path) -> Path:
    """A project with one completed run."""
    invoke("init", "demo")
    project = tmp_path / "demo"
    assert invoke("run", "--no-container", cwd=project).exit_code == ExitCode.OK
    return project


@pytest.fixture
def model_configured(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Point the CLI at a fake provider and capture what it sends."""
    sent: list[dict[str, Any]] = []

    def transport(
        url: str, *, headers: dict[str, str], body: bytes, timeout: int
    ) -> tuple[int, bytes]:
        sent.append({"url": url, "headers": headers, "body": json.loads(body)})
        return 200, json.dumps(ANSWER).encode("utf-8")

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key")
    monkeypatch.setenv("LAB_LLM_MODEL", "vendor/model")
    monkeypatch.setattr("lab_llm.openrouter.urllib_transport", transport)
    return sent


def test_explain_reports_the_summary_and_where_it_was_stored(
    invoke: Invoke,
    payload: Payload,
    finished_run: Path,
    model_configured: list[dict[str, Any]],
) -> None:
    result = invoke("explain", "RUN-000001", "--json", cwd=finished_run)
    assert result.exit_code == ExitCode.OK

    body = payload(result)
    assert set(body) == {
        "run_id",
        "provider",
        "model",
        "text",
        "artifact",
        "prompt_artifact",
    }
    assert body["run_id"] == "RUN-000001"
    assert body["provider"] == "openrouter"
    assert body["model"] == "vendor/model-served"
    assert body["text"] == "The run completed."
    assert body["artifact"]["name"] == "explanation.md"
    assert body["prompt_artifact"]["name"] == "explanation.prompt.txt"

    assert model_configured[0]["headers"]["Authorization"] == "Bearer sk-test-key"
    assert model_configured[0]["body"]["model"] == "vendor/model"


def test_the_summary_appears_as_an_artifact_of_the_run(
    invoke: Invoke,
    payload: Payload,
    finished_run: Path,
    model_configured: list[dict[str, Any]],
) -> None:
    invoke("explain", "RUN-000001", cwd=finished_run)
    status = payload(invoke("status", "RUN-000001", "--json", cwd=finished_run))
    kinds = {a["name"]: a["kind"] for a in status["artifacts"]}
    assert kinds["explanation.md"] == "explanation"
    assert kinds["explanation.prompt.txt"] == "provenance"


def test_without_a_model_it_says_so_and_nothing_else_breaks(
    invoke: Invoke, finished_run: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LAB_LLM_MODEL", raising=False)

    refused = invoke("explain", "RUN-000001", cwd=finished_run)
    assert refused.exit_code == ExitCode.ENVIRONMENT_ERROR
    assert "OPENROUTER_API_KEY" in refused.stderr

    # The rest of the platform is unaffected by there being no model.
    assert invoke("status", "RUN-000001", cwd=finished_run).exit_code == ExitCode.OK
    assert invoke("report", "RUN-000001", cwd=finished_run).exit_code == ExitCode.OK
    assert invoke("validate", cwd=finished_run).exit_code == ExitCode.OK


def test_a_provider_refusal_is_reported_as_an_environment_problem(
    invoke: Invoke, finished_run: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refusing(
        url: str, *, headers: dict[str, str], body: bytes, timeout: int
    ) -> tuple[int, bytes]:
        return 402, json.dumps({"error": {"message": "Insufficient credits"}}).encode()

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key")
    monkeypatch.setenv("LAB_LLM_MODEL", "vendor/model")
    monkeypatch.setattr("lab_llm.openrouter.urllib_transport", refusing)

    result = invoke("explain", "RUN-000001", cwd=finished_run)
    assert result.exit_code == ExitCode.ENVIRONMENT_ERROR
    assert "Insufficient credits" in result.stderr


def test_explaining_an_unknown_run_returns_eleven(
    invoke: Invoke, finished_run: Path, model_configured: list[dict[str, Any]]
) -> None:
    result = invoke("explain", "RUN-000999", cwd=finished_run)
    assert result.exit_code == ExitCode.NOT_FOUND
