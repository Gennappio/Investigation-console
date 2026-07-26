from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from lab_cli.app import app

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"

Invoke = Callable[..., Result]


@pytest.fixture
def invoke(tmp_path: Path, lab_home: Path, monkeypatch: pytest.MonkeyPatch) -> Invoke:
    """Run a `lab` command in an isolated directory and platform state."""
    monkeypatch.setenv("LAB_TEMPLATES_DIR", str(TEMPLATES_DIR))
    runner = CliRunner()

    def run(*arguments: str, cwd: Path | None = None) -> Result:
        monkeypatch.chdir(cwd or tmp_path)
        return runner.invoke(app, list(arguments), catch_exceptions=False)

    return run


@pytest.fixture
def payload() -> Callable[[Result], Any]:
    def parse(result: Result) -> Any:
        return json.loads(result.stdout)

    return parse
