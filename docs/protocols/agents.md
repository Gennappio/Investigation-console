# Working with a coding agent

Researchers choose their own agent (AGENTS.md section 2.6). The platform's job
is to be usable by any of them without special integration, through three
interfaces that all mean the same thing:

- the **CLI** with `--json` — the contract in `cli.md`, and what everything
  else is built on;
- the **Python client** — `LabClient`, for scripts and services;
- the **MCP adapter** — the same operations offered as tools.

## Python

```python
from lab_api_client import LabClient, LabCommandError

lab = LabClient(cwd="/path/to/repository")

report = lab.validate()  # never raises on an invalid manifest
if not report["valid"]:
    for error in report["errors"]:
        print(error["code"], error["path"], error["message"])

outcome = lab.run(backend="local", no_container=True)
print(outcome["run_id"], outcome["status"], outcome["deviations"])

try:
    lab.report("RUN-000999")
except LabCommandError as error:
    print(error.exit_code, error.code)  # 11 NOT_FOUND
```

A failing test suite and a failed run are returned, not raised: both are
recorded results. Everything else raises `LabCommandError` with the exit code
and the stable error code.

## MCP

```bash
uv sync --extra mcp
uv run python -m lab_api_client.mcp_server --workspace /path/to/repository
```

Tools offered by default are read-only: `lab_validate`, `lab_inspect`,
`lab_status`, `lab_search_components`. Add `--allow-writes` to also offer
`lab_test`, `lab_run`, `lab_report` and `lab_publish_component`, which execute
things and spend compute.

For Claude Code, register it in `.mcp.json`:

```json
{
  "mcpServers": {
    "lab-platform": {
      "command": "uv",
      "args": ["run", "--extra", "mcp", "python", "-m",
               "lab_api_client.mcp_server", "--workspace", "."]
    }
  }
}
```

## Instructions worth giving an agent

Paste this into `CLAUDE.md`, `AGENTS.md` or the equivalent for your agent:

> This repository is managed by a research execution platform. Use the `lab`
> CLI with `--json` for anything about experiments, runs or components; every
> command prints one JSON document and returns a stable exit code.
>
> Never state a fact about a run from memory or inference. Run `lab status
> <RUN-id> --json` and read it: the run record is the source of truth for
> status, exit code, commit, container digest, parameters, seeds and artifact
> checksums. Report a run's `deviations` when you summarise it — they say what
> the run could not guarantee.
>
> Do not edit anything under `$LAB_HOME`, and do not hand-edit the managed
> section of a note in the Obsidian vault. Do not rewrite a published component
> version; publish a new version.
>
> Passing tests are not scientific validity. A component's maturity means
> nothing without the evidence reported beside it, and `validated` and
> `lab_standard` come only from a recorded human review.
>
> Before proposing that an experiment is ready, check `lab validate --json` is
> clean and that the test profiles the component declares have actually run.

## What the platform will not do for an agent

It will not write scientific conclusions, promote a component, or mark anything
validated. Those require a person, and the platform records who and why
(`lab promote`, decision records). An LLM may draft prose about a finished run
through `lab explain`, and that output is stored as generated text, clearly
separated from the record.
