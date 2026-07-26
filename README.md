# lab-platform

A Research Execution Platform for a small bioinformatics laboratory: every
important experiment runs through a shared, deterministic protocol and leaves
behind an immutable, searchable, reviewable record.

`AGENTS.md` is the product and architecture specification. This README covers
what exists today and how to work on it.

## Status

**Milestone 1 (project and manifest foundation) is complete.** The platform can
scaffold a managed repository, validate its manifests, and describe it, through
a CLI that speaks JSON and stable exit codes.

| Command | Purpose |
|---|---|
| `lab init <name>` | Create a managed repository from the project template |
| `lab validate` | Validate `lab.yaml` and every experiment manifest |
| `lab inspect` | Summarize the project, runtime, commands and experiments |

`lab build`, `test`, `run`, `status`, `report`, `publish` and `search` arrive
with later milestones (AGENTS.md section 19). There is no database, no
execution backend and no API yet.

## Setup

```bash
uv sync
uv run lab --help
```

## Quickstart

```console
$ lab init demo
Created project PRJ-000001 at /tmp/demo
Registered experiment EXP-000001

Files:
  README.md
  configs/smoke.yaml
  containers/Dockerfile
  experiments/EXP-000001.yaml
  .gitignore
  lab.yaml
  src/demo/__init__.py
  src/demo/run.py
  tests/test_smoke.py

Next: cd demo && lab validate

$ cd demo && lab validate
valid (0 warnings)

$ lab inspect
demo (PRJ-000001)
  root:     /tmp/demo
  runtime:  python 3.12
  owners:   anna.rossi
  outputs:  results
  commands: run, smoke, test
  experiments (1):
    EXP-000001  Demo experiment  [anna.rossi]
```

## Machine-readable output

Every command takes `--json` and writes exactly one JSON document to stdout.

```console
$ lab validate --json
{
  "valid": false,
  "errors": [
    {
      "code": "MISSING_DATASET_VERSION",
      "path": "execution.dataset_refs[0]",
      "message": "Dataset DATA-000001 requires an explicit version.",
      "file": "experiments/EXP-000001.yaml"
    }
  ],
  "warnings": []
}
```

Exit codes follow AGENTS.md section 13.2. Milestone 1 uses:

| Code | Meaning |
|---|---|
| 0 | Success. Warnings do not fail a command |
| 1 | Unexpected internal error |
| 2 | Invalid command-line input |
| 3 | Validation failed, or the command ran outside a managed repository |
| 4 | Unusable platform state: corrupt `LAB_HOME`, missing template |
| 12 | Conflict: `lab init` target already exists |

Validation errors block a run; warnings (missing references, seed policy,
maintainer, scientific validation) are reported but do not fail. Finding codes
are stable identifiers, safe to branch on.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `LAB_HOME` | `~/.lab` | Platform state: identifier counters and the project index |
| `LAB_TEMPLATES_DIR` | installed templates | Override the project template directory |

`LAB_HOME/registry.json` allocates `PRJ-` and `EXP-` identifiers until the
operational database arrives in Milestone 2 (see `docs/adr/0003`).

## Repository layout

```text
packages/lab_domain      Domain models, manifest validation, application services
packages/lab_registry    Identifier allocation and the project index (local JSON store)
packages/lab_cli         Typer CLI: parses input, calls services, reports
schemas/                 JSON Schemas generated from the models (do not edit by hand)
templates/project/       What `lab init` renders
docs/adr/                Architecture decision records
tests/{unit,contract,integration,fixtures}
```

Business logic lives in `lab_domain`; the CLI never duplicates it, so the API
in Milestone 2 reuses the same services. Infrastructure sits behind protocols
(`lab_domain.registry.ProjectRegistry`) and is injected at the composition root
(`lab_cli.runtime`).

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy packages          # strict; becomes `mypy packages apps` when the API lands
uv run pytest
```

Regenerate the JSON Schemas after changing a manifest model, or the schema
contract test fails:

```bash
uv run python -m lab_domain.schema_export schemas/
```

### Troubleshooting

If `lab` fails with `ModuleNotFoundError: No module named 'lab_cli'` on macOS,
the editable install's `.pth` file carries the hidden file flag, which CPython's
`site` module skips. Clear it:

```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth
```

The flag is inherited from uv's cache through hardlinks; `UV_LINK_MODE=copy uv
sync` avoids it. The test suite is unaffected: it imports from `packages/`
directly.
