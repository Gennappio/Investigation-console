"""MCP adapter: the same operations, offered to an agent over MCP.

An adapter and nothing more (AGENTS.md section 2.6). It registers the
operations from :mod:`lab_api_client.operations` as tools and returns their
JSON payloads unchanged. Anything a tool can do, the CLI can do, identically.

Writing is off by default: an agent that connects gets to read a laboratory's
record, not to spend its cluster time. Start with ``--allow-writes`` to offer
the rest.

    uv run --extra mcp python -m lab_api_client.mcp_server --workspace .
"""

from __future__ import annotations

import argparse
import functools
from pathlib import Path
from typing import Any

from lab_api_client.client import LabClient, LabCommandError
from lab_api_client.operations import Operation, operations

SERVER_NAME = "lab-platform"
INSTRUCTIONS = """
This is a research execution platform for a bioinformatics laboratory.

Facts about runs come from the record, never from inference: read them with
lab_status rather than reconstructing them. A component's maturity is only
meaningful together with the evidence reported beside it, and no number of
passing tests makes a component scientifically validated - that requires a
human review the platform records separately.
""".strip()


def build_server(client: LabClient, *, allow_writes: bool = False) -> Any:
    """An MCP server exposing the platform's operations as tools."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - depends on the extra
        raise RuntimeError(
            "The MCP adapter needs the `mcp` extra: uv sync --extra mcp."
        ) from exc

    server = FastMCP(SERVER_NAME, instructions=INSTRUCTIONS)
    for operation in operations(client, allow_writes=allow_writes):
        _register(server, operation)
    return server


def _register(server: Any, operation: Operation) -> None:
    """Expose one operation, reporting platform errors as data, not crashes.

    ``functools.wraps`` carries the operation's signature onto the wrapper, and
    that signature becomes the tool's schema: without it an agent would be told
    the tool takes nothing.
    """

    @functools.wraps(operation.call)
    def tool(*arguments: Any, **keywords: Any) -> dict[str, Any]:
        try:
            return operation.call(*arguments, **keywords)
        except LabCommandError as error:
            # A platform error is an answer an agent can act on, not a crash.
            return {
                "status": "error",
                "code": error.code,
                "exit_code": error.exit_code,
                "message": error.message,
            }

    tool.__name__ = operation.name
    tool.__doc__ = operation.description
    server.tool(name=operation.name, description=operation.description)(tool)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MCP server for the lab platform.")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Repository the tools operate in. Defaults to the current directory.",
    )
    parser.add_argument(
        "--home", type=Path, default=None, help="Override LAB_HOME for platform state."
    )
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        help="Also offer the operations that execute, publish or spend compute.",
    )
    arguments = parser.parse_args(argv)

    server = build_server(
        LabClient(cwd=arguments.workspace, home=arguments.home),
        allow_writes=arguments.allow_writes,
    )
    server.run()
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
