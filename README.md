# lab-platform

A Research Execution Platform for a small bioinformatics laboratory: every
important experiment runs through a shared, deterministic protocol and leaves
behind an immutable, searchable, reviewable record.

`AGENTS.md` is the product and architecture specification. This README covers
what exists today and how to work on it.

## Status

**Milestones 1 and 2 are complete.** A researcher can scaffold a repository,
validate it, build its container, run its tests, execute the experiment
locally, and get a structured report of what happened.

| Command | Purpose |
|---|---|
| `lab init <name>` | Create a managed repository from the project template |
| `lab validate` | Validate `lab.yaml` and every experiment manifest |
| `lab inspect` | Summarize the project, runtime, commands and experiments |
| `lab build` | Build the declared container and record its digest |
| `lab test --profile <name>` | Run a command profile and record the evidence |
| `lab run --backend local` | Execute the experiment and collect its outputs |
| `lab status <RUN-id>` | Show what is recorded about a run |
| `lab report <RUN-id>` | Write the report bundle for a finished run |

`lab publish` and `lab search` (the component registry) and the SLURM backend
arrive with later milestones. There is no operational database and no HTTP API
yet: state lives under `LAB_HOME` (see `docs/adr/0005`).

## Setup

```bash
uv sync
uv run lab --help
```

## Quickstart

```console
$ lab init demo && cd demo
Created project PRJ-000001 at /tmp/demo
Registered experiment EXP-000001
...

$ lab validate
valid (0 warnings)

$ lab test --profile smoke
integration_tests: passed (profile smoke, exit code 0)
  command: python -m demo.run --config configs/smoke.yaml
  logs:    ART-000001, ART-000002

$ lab run --backend local --no-container
RUN-000001: completed (exit code 0)
  backend:    local
  experiment: EXP-000001
  container:  none: executed on the host
  config:     sha256:6ea9150e45a20d5b577d8830d97f5467c9edb6fb2e6b29a2dc51e19cd2d4a5d0
  resources:  1 cpus, 1074 MB, limit 00:10:00
  artifacts:  5
    ART-000003  stdout.log
    ART-000004  stderr.log
    ART-000005  metrics.json
    ART-000006  summary.json
    ART-000007  manifest.snapshot.yaml
  deviations:
    - Code was not under version control, so no commit was recorded.
    - Executed directly on the host although the repository declares a container.

Next: lab report RUN-000001

$ lab report RUN-000001
Report for RUN-000001 (completed)
  report.json       file:///…/artifacts/RUN-000001/report.json
  report.html       file:///…/artifacts/RUN-000001/report.html
  provenance.json   file:///…/artifacts/RUN-000001/provenance.json
  checksums.txt     file:///…/artifacts/RUN-000001/checksums.txt
```

## How a run is recorded

A run advances through `created → validated → queued → running → completed`
(or `failed`/`cancelled`), and every transition is saved. Impossible
transitions are rejected, and the fields that make a run reproducible — code
revision, container digest, datasets, parameters, seeds, resources,
configuration hash — can never be rewritten afterwards. A correction is a new
run, not an edit.

What the platform cannot guarantee, it records as a **deviation from protocol**
rather than hiding: running on the host instead of in the declared container,
or executing code that is not under version control. Deviations appear in
`lab status`, in `report.json`, and in the report's own section.

Test evidence is kept per suite, never collapsed into one green check: a passing
`software_tests` suite says nothing about `scientific_validation`, and the
report says so.

## The execution contract

`lab run` executes the `run` profile from `lab.yaml` in an isolated scratch
directory, with these variables (full rationale in `docs/adr/0006`):

| Variable | Meaning |
|---|---|
| `LAB_RUN_ID`, `LAB_EXPERIMENT_ID` | Identifiers of this execution |
| `LAB_EXPERIMENT_CONFIG` | Generated configuration file to read |
| `LAB_OUTPUT_DIR` | Where to write outputs |
| `LAB_PROJECT_DIR` | Repository root, read-only during the run |

`${NAME}` placeholders in a command are expanded by the platform from that
table and executed as an argument list. No shell is ever involved, so manifest
content is data, never code. Outputs are checksummed into permanent storage,
and a run is marked completed only once they are safely stored. If the output
directory contains `metrics.json`, its contents become the report's metrics.

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

Exit codes follow AGENTS.md section 13.2:

| Code | Meaning |
|---|---|
| 0 | Success. Warnings do not fail a command |
| 1 | Unexpected internal error |
| 2 | Invalid command-line input, including a malformed identifier |
| 3 | Validation failed, or the command ran outside a managed repository |
| 4 | Environment problem: unusable `LAB_HOME`, missing template, no container engine |
| 5 | Container build failed |
| 6 | Tests failed |
| 8 | Execution failed |
| 9 | Artifact collection failed |
| 11 | No such run |
| 12 | Conflict: target exists, or an attempt to rewrite a recorded run |

Finding codes and artifact identifiers are stable, safe to branch on.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `LAB_HOME` | `~/.lab` | Platform state: identifiers, runs, artifacts, audit log |
| `LAB_TEMPLATES_DIR` | installed templates | Override the templates directory |

`LAB_HOME` holds `registry.json` (identifier counters and projects),
`runs/`, `tests/`, `artifacts/` (permanent storage), `work/` (scratch, safe to
delete between runs) and `audit.jsonl` (append-only record of significant
actions).

## Repository layout

```text
packages/lab_domain      Domain models, validation, ports, application services
packages/lab_registry    Identifiers, run records, test evidence, audit log
packages/lab_artifacts   Filesystem artifact storage with checksums
packages/lab_containers  Docker engine behind the container port
packages/lab_execution   Local execution backend
packages/lab_reporting   HTML report rendering
packages/lab_cli         Typer CLI: parses input, calls services, reports
schemas/                 JSON Schemas generated from the models (never edited by hand)
templates/project/       What `lab init` renders
templates/report/        The report template
docs/adr/                Architecture decision records
tests/{unit,contract,integration,fixtures}
```

Business logic lives in `lab_domain`; the CLI never duplicates it, so the
future API reuses the same services. Infrastructure sits behind protocols
(`ProjectRegistry`, `RunStore`, `ArtifactStore`, `ContainerEngine`,
`ExecutionBackend`) and is injected at the composition root (`lab_cli.runtime`),
which is what lets the SLURM backend arrive without touching the domain.

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy packages          # strict; becomes `mypy packages apps` when the API lands
uv run pytest
```

Regenerate the JSON Schemas after changing a manifest or run model, or the
schema contract test fails:

```bash
uv run python -m lab_domain.schema_export schemas/
```

Docker is not needed for the test suite: the container engine is exercised
through a fake that captures the argument lists.

### Troubleshooting

If `lab` fails with `ModuleNotFoundError: No module named 'lab_cli'` on macOS,
the editable install's `.pth` file carries the hidden file flag, which CPython's
`site` module skips. Clear it:

```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth
```

uv writes the flag whenever it rebuilds the editable wheel, so this can recur
after a packaging or dependency change; `link-mode` does not affect it. The test
suite is unaffected: it imports from `packages/` directly.
