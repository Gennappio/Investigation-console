# lab-platform

A Research Execution Platform for a small bioinformatics laboratory: every
important experiment runs through a shared, deterministic protocol and leaves
behind an immutable, searchable, reviewable record.

`AGENTS.md` is the product and architecture specification. This README covers
what exists today and how to work on it.

## Status

**All six milestones are complete.** A researcher can scaffold a repository,
validate it, build its container, run its tests, execute the experiment locally
or on SLURM, get a structured report of what happened, publish the result as a
reusable component that others can find, read it all back as linked notes in an
Obsidian vault, and drive the whole thing from any coding agent.

| Command | Purpose |
|---|---|
| `lab init <name>` | Create a managed repository from the project template |
| `lab validate` | Validate `lab.yaml` and every experiment manifest |
| `lab inspect` | Summarize the project, runtime, commands and experiments |
| `lab build` | Build the declared container and record its digest |
| `lab test --profile <name>` | Run a command profile and record the evidence |
| `lab run --backend local\|slurm` | Execute the experiment and collect its outputs |
| `lab status <RUN-id>` | Show what is recorded about a run, and collect it if it has ended |
| `lab cancel <RUN-id>` | Stop a queued or running job |
| `lab report <RUN-id>` | Write the report bundle for a finished run |
| `lab publish component` | Register a component with the evidence behind it |
| `lab search components "..."` | Find registered components |
| `lab promote <CMP-id>` | Record a review that grants `validated` or `lab_standard` |
| `lab sync obsidian` | Project this repository into the Obsidian vault |
| `lab explain <RUN-id>` | Optional: a generated summary of a finished run |

The API and the agent client (Milestone 6) are still to come. There is no operational database and no HTTP API yet: state
lives under `LAB_HOME` (see `docs/adr/0005`).

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

## Running on a cluster

`sbatch` returns as soon as a job is queued, so a cluster run is submitted and
left to the scheduler; `lab status` reconciles it and collects its outputs the
first time anyone asks (ADR 0007). `--wait` polls in the foreground instead.

```console
$ lab run --backend slurm
RUN-000002: queued
  backend:    slurm   job: 481930
  ...
Next: lab status RUN-000002   (collects the outputs once it ends)

$ lab status RUN-000002
RUN-000002: completed
  ...
```

The generated `sbatch` script is collected as an artifact of the run, so what
was submitted survives after scratch is cleaned: it carries the run,
experiment, commit, container digest and configuration hash in its header, `set -euo pipefail`, the resource request as
`#SBATCH` directives, and the command with every argument shell-quoted.
Placeholders such as `${LAB_EXPERIMENT_CONFIG}` are expanded by the platform
before the script is written, so no shell ever interprets manifest content.

Cluster options come from the environment: `LAB_SLURM_PARTITION`,
`LAB_SLURM_ACCOUNT`, `LAB_SLURM_QOS`, `LAB_SLURM_CLUSTER`. Containers on a
cluster run through Apptainer (`apptainer exec --containall`), pinned by digest;
images are still built with Docker via `lab build`.

## Limits and scratch

`$LAB_HOME/policy.json` bounds what a run may request and what happens to its
scratch directory afterwards. Everything is optional; these are the defaults:

```json
{
  "max_cpus": 128,
  "max_memory_mb": 1048576,
  "max_gpus": 8,
  "max_time_seconds": 604800,
  "scratch": "keep_on_failure"
}
```

A request above a ceiling is refused before submission with exit code 3. An
experiment with no wall-time limit is refused outright: an unbounded job cannot
be scheduled. `scratch` is `keep`, `keep_on_failure` (the default: a failed run
is worth debugging) or `delete`; artifacts are already in permanent storage by
the time it applies.

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

## The component registry

A component is a reusable executable asset, declared in `components/<name>.yaml`
and published into the laboratory registry:

```console
$ lab test --profile smoke && lab test --profile test
$ lab publish component
Published demo-sensitivity-analysis 0.1.0 as CMP-000001
  maturity:   tested
  maintainer: anna.rossi
  evidence:
    integration_tests      passed (profile smoke)
    software_tests         passed (profile test)
  to advance: reproducibility_tests must pass

$ lab search components "sensitivity analysis"
1 component(s):
  CMP-000001  demo-sensitivity-analysis 0.1.0  [tested]
      Sensitivity analysis of the demo model...
      evidence: integration_tests=passed, software_tests=passed
```

**Maturity is not something a component claims about itself** (ADR 0009). Up to
`reproducible` the platform computes it from test results it recorded:
`runnable` needs integration tests passing, `tested` adds software tests,
`reproducible` adds reproducibility tests. The manifest says which command
profile proves each category; `lab publish` reads the latest result for each and
reports what is still missing for the next level.

`validated` and `lab_standard` cannot be earned by any number of passing tests
— they are granted by a person:

```bash
lab promote CMP-000001 --to validated --reviewer pi.rossi \
  --note "Recovered the published sensitivity ranking on the reference dataset."
```

That writes a decision record (`DEC-…`) and an audit entry, and the review
survives republishing, so a routine `lab publish` cannot quietly undo it.
Trying to promote to an evidenced level is refused: those are not a matter of
opinion. A published version is immutable — republishing the same version with
different content exits 12 and asks for a new version instead.

For a principal investigator, `lab search components --status tested --json`
is the list of components awaiting review.

## The Obsidian vault

Point the platform at a vault and finishing a run writes the notes for it:

```bash
export LAB_OBSIDIAN_VAULT=~/lab-vault     # or `vault` in $LAB_HOME/obsidian.json
lab run --backend local
#   ... vault: 3 notes written
```

You get `Projects/PRJ-000001.md`, `Experiments/EXP-000001.md` and
`Runs/RUN-000001.md`, cross-linked with `[[wikilinks]]`, with frontmatter
carrying the run's status, backend, commit, container digest and stable URIs
(`lab-report://RUN-000001`, `lab-run://RUN-000001/artifacts`). `lab sync
obsidian` regenerates everything, which is how you backfill a vault configured
after the fact.

**Your writing is safe** (ADR 0010). Each note has two halves:

```markdown
<!-- BEGIN LAB MANAGED -->    the platform owns this, and rewrites it
<!-- BEGIN HUMAN NOTES -->    you own this, and it is copied through untouched
```

Frontmatter keys the platform does not claim are preserved too. And if a note
cannot be parsed with confidence — no frontmatter, duplicated markers, or a
file you wrote by hand — the platform **does not touch it**. It writes the
generated version beside it as `RUN-000001.lab-conflict.md` and says so. It
never guesses which text is whose.

The vault holds links, not contents: notes name artifacts and address them by
URI, but no artifact contents, logs or filesystem paths are copied into it, and
generated notes are scanned for secrets before being written. Projection is off
until a vault is configured, and a vault problem is reported without failing
the run that produced the record.

## Using it from an agent or a script

The CLI's `--json` contract is the interface, documented in
`docs/protocols/cli.md` and pinned by the tests in `tests/contract/`. The Python
client and the MCP adapter are built on it and add no behaviour of their own
(ADR 0011).

```python
from lab_api_client import LabClient, LabCommandError

lab = LabClient(cwd="/path/to/repository")
if not lab.validate()["valid"]:
    ...
outcome = lab.run(backend="local", no_container=True)
print(outcome["run_id"], outcome["status"], outcome["deviations"])
```

A failing test suite and a failed run are returned rather than raised — both
recorded everything they promised. Anything else raises `LabCommandError`
carrying the stable exit code and error code.

For an MCP-speaking agent:

```bash
uv sync --extra mcp
uv run python -m lab_api_client.mcp_server --workspace .
```

Only read tools are offered by default (`lab_validate`, `lab_inspect`,
`lab_status`, `lab_search_components`). `--allow-writes` adds the ones that
execute things and spend compute. `docs/protocols/agents.md` has the Claude Code
registration snippet and a block of instructions worth pasting into your agent's
own configuration.

## The HTTP API

```bash
uv sync --extra api
uv run uvicorn api.main:app --app-dir apps
```

`/v1/runs`, `/v1/components`, `/v1/artifacts`, `/v1/projects`,
`/v1/execution-backends`, plus `/v1/runs/{id}/report`. Responses carry stable
`lab-*://` URIs and never filesystem paths.

**The API is read-only, deliberately.** Submitting a run spends compute and
publishing changes a laboratory's record, and the platform has no authorization
model yet — an unauthenticated POST that executes a repository's commands is the
wrong kind of convenient. The API reports; the CLI acts. Write endpoints arrive
with authorization, and will record a person rather than a service.

## Optional: generated summaries

The platform needs no language model. Nothing in validation, building, testing,
execution, collection or reporting calls one, and with no key configured every
command behaves exactly as documented above.

`lab explain <RUN-id>` is the single exception. It sends the facts already in
the run record to a model and stores the prose it gets back:

```bash
export OPENROUTER_API_KEY=sk-or-...        # the key lives in the environment, never in a file
export LAB_LLM_MODEL=vendor/model-name     # choose one from https://openrouter.ai/models
lab explain RUN-000001
```

Settings other than the key may live in `$LAB_HOME/llm.json`
(`model`, `base_url`, `max_tokens`, `temperature`, `timeout_seconds`);
environment variables win. There is deliberately **no default model**: which
one to use has cost and data-handling consequences, so the platform asks.

What it guarantees:

- The summary is stored as its own artifact, `explanation.md`, marked as
  generated and carrying the provider, the model that served the request and
  the SHA-256 of the prompt. The run record and the report are untouched — no
  factual field anywhere is produced by a model (AGENTS.md section 11).
- The exact prompt is stored beside it as `explanation.prompt.txt`, and the
  call is written to `audit.jsonl`, so what was sent to a third party is
  auditable afterwards.
- The prompt itself is a template in `templates/prompts/`, readable and
  editable without touching code.
- Without a key, the command exits 4 saying so. Nothing else changes.

The reasoning, and what it deliberately does not do, is in `docs/adr/0008`.
Note that dataset classifications (section 15.2) are not yet in the run record,
so `lab explain` cannot refuse a run over restricted or clinical data; if you
work with patient-derived data, read the stored prompt before enabling it.

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
| 8 | Execution failed, or an unknown backend |
| 9 | Artifact collection failed |
| 11 | No such run |
| 12 | Conflict: target exists, or an attempt to rewrite a recorded run or published version |

Finding codes and artifact identifiers are stable, safe to branch on.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `LAB_HOME` | `~/.lab` | Platform state: identifiers, runs, artifacts, audit log |
| `LAB_TEMPLATES_DIR` | installed templates | Override the templates directory |
| `LAB_SLURM_PARTITION`, `LAB_SLURM_ACCOUNT`, `LAB_SLURM_QOS` | unset | Cluster submission options |
| `LAB_OBSIDIAN_VAULT` | unset | Vault to project notes into; unset disables projection |
| `OPENROUTER_API_KEY` | unset | Credential for `lab explain`; without it the command is simply unavailable |
| `LAB_LLM_MODEL`, `LAB_LLM_BASE_URL` | unset | Model choice and endpoint for `lab explain` |

`LAB_HOME` holds `registry.json` (identifier counters and projects),
`runs/`, `tests/`, `artifacts/` (permanent storage), `components/` and
`decisions/` (the registry and its reviews), `work/` (scratch, safe to delete
between runs), `slurm/` (job identifiers, so a later command can collect a
cluster run), `policy.json` and `audit.jsonl` (append-only record of
significant actions).

## Repository layout

```text
packages/lab_domain      Domain models, validation, ports, application services
packages/lab_registry    Identifiers, run records, test evidence, audit log
packages/lab_artifacts   Filesystem artifact storage with checksums
packages/lab_containers  Docker engine behind the container port
packages/lab_execution   Local execution backend, and running external commands
packages/lab_slurm       SLURM backend: sbatch rendering, submission, polling
packages/lab_reporting   HTML report rendering
packages/lab_obsidian    Vault projection: note merge, templates, settings
packages/lab_api_client  Python client, agent operations, MCP adapter
apps/api                 Read-only HTTP API (optional extra)
packages/lab_llm         Optional language-model adapter (OpenRouter) and prompts
packages/lab_cli         Typer CLI: parses input, calls services, reports
schemas/                 JSON Schemas generated from the models (never edited by hand)
templates/project/       What `lab init` renders, including an example component
templates/report/        The report template
docs/adr/                Architecture decision records
docs/protocols/          The CLI JSON contract and agent instructions
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
uv run mypy packages apps     # strict
uv run pytest                              # extras-dependent tests skip if absent
uv run --extra api --extra mcp pytest      # everything
```

Regenerate the JSON Schemas after changing a manifest or run model, or the
schema contract test fails:

```bash
uv run python -m lab_domain.schema_export schemas/
```

Neither Docker, a cluster nor an API key is needed for the test suite, and a
session-wide fixture fails any test that opens a socket, so nothing reaches a
provider by accident. The container
engines are exercised through a fake that captures the argument lists, and
`tests/integration/test_acceptance_m3.py` drives the real CLI against fake
`sbatch`, `squeue`, `sacct` and `scancel` executables (`tests/fixtures/
fake_slurm.py`) that behave like the scheduler: jobs queue, start, finish, fail
and cancel. What that cannot prove is that a particular cluster accepts the
generated script; submitting to the laboratory cluster is the remaining
Milestone 3 acceptance step.

### Troubleshooting

**`ModuleNotFoundError: No module named 'lab_cli'` on macOS.** The cause is
almost always that the virtualenv sits in an iCloud-synced folder. If `Desktop
& Documents Folders` syncing is on, everything under `~/Documents` is managed
by iCloud, which sets the macOS `hidden` flag on the files it manages — and
CPython's `site` module skips hidden `.pth` files, so the editable install's
path file is ignored and the packages become invisible.

Check with:

```bash
ls -lO .venv/lib/python3.12/site-packages/*.pth     # "hidden" in the flags column
defaults read com.apple.finder FXICloudDriveDesktop # 1 means Documents is synced
```

Keep the environment out of the synced folder:

```bash
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/lab-platform"   # put this in ~/.zshrc
uv sync
```

`chflags nohidden …` clears the flag but iCloud re-applies it, and
`uv sync --no-editable` is reverted by the next `uv run`; neither is a fix.

Better still, keep the whole repository outside iCloud (`~/Developer`, for
instance). Syncing a `.git` directory and a virtualenv through iCloud is slow
and can evict files into `.icloud` placeholders, which breaks builds in more
confusing ways than a missing module.

The test suite is unaffected either way: it adds `packages/` and `apps/` to the
path itself.
