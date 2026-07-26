"""Running external commands.

Both the container engines and the SLURM backend shell out to client tools, and
both are tested by injecting a fake runner instead of a real process. The
protocol and the one real implementation live here so neither adapter has to
own process handling.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from typing import Protocol

from lab_domain.errors import DependencyError

PLACEHOLDER = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}")


def expand_placeholders(
    argv: Sequence[str], environment: dict[str, str]
) -> tuple[str, ...]:
    """Replace ``${NAME}`` in an argument list from ``environment``.

    The platform expands these itself so no shell ever interprets manifest
    content (ADR 0006). Unknown names are left untouched: silently emptying an
    argument would change what is executed without saying so.
    """
    return tuple(
        PLACEHOLDER.sub(lambda m: environment.get(m["name"], m[0]), argument)
        for argument in argv
    )


class CommandResult(Protocol):
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def __call__(
        self, argv: Sequence[str], *, timeout: int | None = None
    ) -> CommandResult: ...


def subprocess_runner(
    argv: Sequence[str], *, timeout: int | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a command as an argument list. No shell is involved, ever."""
    try:
        return subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DependencyError(f"{argv[0]} is not installed or not on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise DependencyError(f"{argv[0]} did not respond within {timeout}s.") from exc
