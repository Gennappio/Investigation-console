"""Exit codes are part of the agent-facing contract (AGENTS.md section 13.2)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import Result

from lab_cli.exit_codes import ExitCode

Invoke = Callable[..., Result]


def test_successful_commands_return_zero(invoke: Invoke, tmp_path: Path) -> None:
    assert invoke("init", "demo").exit_code == ExitCode.OK
    project = tmp_path / "demo"
    assert invoke("validate", cwd=project).exit_code == ExitCode.OK
    assert invoke("inspect", cwd=project).exit_code == ExitCode.OK


def test_warnings_do_not_fail_validation(
    invoke: Invoke, tmp_path: Path, manifests: Path
) -> None:
    invoke("init", "demo")
    project = tmp_path / "demo"
    (project / "experiments" / "EXP-000001.yaml").write_text(
        (manifests / "warnings_only.yaml").read_text()
    )
    assert invoke("validate", cwd=project).exit_code == ExitCode.OK


@pytest.mark.parametrize("name", ["Demo", "-demo"])
def test_invalid_input_returns_two(invoke: Invoke, name: str) -> None:
    assert invoke("init", name).exit_code == ExitCode.INVALID_INPUT


def test_unknown_command_returns_two(invoke: Invoke) -> None:
    assert invoke("nonexistent").exit_code == ExitCode.INVALID_INPUT


def test_invalid_manifest_returns_three(
    invoke: Invoke, tmp_path: Path, manifests: Path
) -> None:
    invoke("init", "demo")
    project = tmp_path / "demo"
    (project / "experiments" / "EXP-000001.yaml").write_text(
        (manifests / "missing_dataset_version.yaml").read_text()
    )
    assert invoke("validate", cwd=project).exit_code == ExitCode.VALIDATION_FAILED


def test_outside_a_workspace_returns_three(invoke: Invoke) -> None:
    assert invoke("validate").exit_code == ExitCode.VALIDATION_FAILED
    assert invoke("inspect").exit_code == ExitCode.VALIDATION_FAILED


def test_unusable_platform_state_returns_four(
    invoke: Invoke, lab_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lab_home.mkdir(parents=True)
    (lab_home / "registry.json").write_text("{corrupt")
    assert invoke("init", "demo").exit_code == ExitCode.ENVIRONMENT_ERROR


def test_missing_template_returns_four(
    invoke: Invoke, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LAB_TEMPLATES_DIR", str(tmp_path / "absent"))
    assert invoke("init", "demo").exit_code == ExitCode.ENVIRONMENT_ERROR


def test_existing_target_returns_twelve(invoke: Invoke) -> None:
    invoke("init", "demo")
    assert invoke("init", "demo").exit_code == ExitCode.CONFLICT


def test_human_errors_go_to_stderr(invoke: Invoke) -> None:
    result = invoke("validate")
    assert result.stdout == ""
    assert "error:" in result.stderr
