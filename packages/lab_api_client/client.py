"""Driving the platform from Python, through the interface agents use.

Every call runs the CLI with ``--json`` and parses the documented payload. That
costs a process per call and buys three things: the client cannot drift from
the contract, it works against any installed version of the platform, and there
is exactly one implementation of what a command means.

Exit codes become exceptions. Codes are stable (AGENTS.md section 13.2), so
``error.exit_code`` and ``error.code`` are both safe to branch on.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

MODULE = "lab_cli"
JSON_FLAG = "--json"
DEFAULT_TIMEOUT_SECONDS = 3600


class LabCommandError(RuntimeError):
    """A command that did not succeed, with its exit code and error code."""

    def __init__(
        self, exit_code: int, code: str, message: str, command: Sequence[str]
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.exit_code = exit_code
        self.code = code
        self.message = message
        self.command = tuple(command)


class LabClient:
    """The platform, callable from Python.

    ``home`` and ``vault`` override where state lives, which is what makes the
    client usable from a service or a test without touching a real laboratory.
    """

    def __init__(
        self,
        *,
        cwd: Path | None = None,
        home: Path | None = None,
        executable: Sequence[str] | None = None,
        environment: dict[str, str] | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._cwd = Path(cwd) if cwd else Path.cwd()
        self._executable = tuple(executable or (sys.executable, "-m", MODULE))
        self._environment = {**os.environ, **(environment or {})}
        if home is not None:
            self._environment["LAB_HOME"] = str(home)
        self._timeout = timeout_seconds

    # Reading -----------------------------------------------------------------

    def validate(self) -> dict[str, Any]:
        """Validation report of the repository. Never raises on invalid input:
        an invalid manifest is an answer, not a failure of the call."""
        return self._invoke("validate", allowed_exit_codes=(0, 3))

    def inspect(self) -> dict[str, Any]:
        return self._invoke("inspect")

    def status(self, run_id: str) -> dict[str, Any]:
        """A run, reconciled with its backend if it is still in flight."""
        return self._invoke("status", run_id)

    def report(self, run_id: str) -> dict[str, Any]:
        return self._invoke("report", run_id)

    def search_components(
        self, query: str = "", *, status: str | None = None, limit: int = 20
    ) -> dict[str, Any]:
        arguments = ["search", "components", query, "--limit", str(limit)]
        if status:
            arguments += ["--status", status]
        return self._invoke(*arguments)

    # Doing -------------------------------------------------------------------

    def init(self, name: str) -> dict[str, Any]:
        return self._invoke("init", name)

    def test(self, profile: str = "test") -> dict[str, Any]:
        """Run a test profile. A failing suite is a result, not an exception."""
        return self._invoke("test", "--profile", profile, allowed_exit_codes=(0, 6))

    def build(self, tag: str | None = None) -> dict[str, Any]:
        return self._invoke("build", *(("--tag", tag) if tag else ()))

    def run(
        self,
        *,
        backend: str = "local",
        experiment: str | None = None,
        no_container: bool = False,
        wait: bool = False,
    ) -> dict[str, Any]:
        """Execute the experiment. A failed run is returned, not raised: the
        record of a failure is as much a result as a success."""
        arguments = ["run", "--backend", backend]
        if experiment:
            arguments += ["--experiment", experiment]
        if no_container:
            arguments.append("--no-container")
        if wait:
            arguments.append("--wait")
        return self._invoke(*arguments, allowed_exit_codes=(0, 8))

    def cancel(self, run_id: str) -> dict[str, Any]:
        return self._invoke("cancel", run_id)

    def publish_component(self, name: str | None = None) -> dict[str, Any]:
        arguments = ["publish", "component"]
        if name:
            arguments += ["--name", name]
        return self._invoke(*arguments)

    def promote_component(
        self,
        component_id: str,
        *,
        to: str,
        note: str,
        reviewer: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        arguments = ["promote", component_id, "--to", to, "--note", note]
        if reviewer:
            arguments += ["--reviewer", reviewer]
        if version:
            arguments += ["--version", version]
        return self._invoke(*arguments)

    def explain(self, run_id: str, *, model: str | None = None) -> dict[str, Any]:
        """Optional: needs a configured language model."""
        arguments = ["explain", run_id]
        if model:
            arguments += ["--model", model]
        return self._invoke(*arguments)

    def sync(self) -> dict[str, Any]:
        return self._invoke("sync", "obsidian")

    # Plumbing ----------------------------------------------------------------

    def _invoke(
        self, *arguments: str, allowed_exit_codes: tuple[int, ...] = (0,)
    ) -> dict[str, Any]:
        command = [*self._executable, *arguments, JSON_FLAG]
        try:
            completed = subprocess.run(
                command,
                cwd=self._cwd,
                env=self._environment,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise LabCommandError(
                1,
                "TIMEOUT",
                f"`lab {arguments[0]}` exceeded {self._timeout}s.",
                command,
            ) from exc

        payload = _decode(completed.stdout)
        if completed.returncode in allowed_exit_codes:
            if payload is None:
                raise LabCommandError(
                    completed.returncode,
                    "MALFORMED_OUTPUT",
                    f"`lab {arguments[0]}` did not print JSON.",
                    command,
                )
            return payload

        code, message = _error(payload, completed)
        raise LabCommandError(completed.returncode, code, message, command)


def _decode(stdout: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(stdout)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _error(
    payload: dict[str, Any] | None, completed: subprocess.CompletedProcess[str]
) -> tuple[str, str]:
    """The platform's own error object, or the best available description."""
    if payload and payload.get("status") == "error":
        return str(payload.get("code", "LAB_ERROR")), str(payload.get("message", ""))
    stderr = completed.stderr.strip()
    return "LAB_ERROR", stderr or f"exit code {completed.returncode}"
