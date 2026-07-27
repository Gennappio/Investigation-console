# The CLI JSON contract

This is the interface external tools and coding agents integrate against. It is
stable: the keys below are pinned by the tests in `tests/contract/`, and
changing one is changing a published interface.

Every command accepts `--json` and then writes **exactly one JSON document to
stdout and nothing else**. Human-readable output goes to stdout only without
`--json`; errors in human mode go to stderr. Never parse the prose.

## Errors

Any command that fails writes the same object, and exits with a code from the
table below:

```json
{ "status": "error", "code": "MANIFEST_NOT_FOUND", "message": "..." }
```

`code` is a stable identifier; `message` is for people and may be reworded.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. Warnings never fail a command |
| 1 | Unexpected internal error |
| 2 | Invalid input: bad arguments, malformed identifier, unknown kind |
| 3 | Validation failed, outside a repository, or a request above policy |
| 4 | Environment: unusable `LAB_HOME`, missing template, no container engine, no scheduler, no language model |
| 5 | Container build failed |
| 6 | Tests failed |
| 8 | Execution failed, or an unknown backend |
| 9 | Artifact collection failed |
| 11 | No such run or component |
| 12 | Conflict: target exists, rewriting a recorded run, or changing a published version |

Two of these are results rather than failures and are worth handling instead of
raising: **6** means a suite failed and was recorded, **8** means a run failed
and was recorded. Both still wrote everything they promised.

## Commands

### `lab init <name>`

```json
{ "status": "created", "project_id": "PRJ-000001", "experiment_id": "EXP-000001",
  "path": "/abs/demo", "files": ["lab.yaml", "..."] }
```

### `lab validate`

Exit 0 when valid, 3 when not; the payload is the same either way.

```json
{ "valid": false,
  "errors": [{ "code": "MISSING_DATASET_VERSION",
               "path": "execution.dataset_refs[0]",
               "message": "Dataset DATA-000001 requires an explicit version.",
               "file": "experiments/EXP-000001.yaml" }],
  "warnings": [] }
```

### `lab inspect`

`{root, name, description, project_id, owners, runtime, commands, outputs_directory, experiments[]}`

### `lab build`

`{status, image, digest, build_log_artifact}` — `digest` is what a run pins to.

### `lab test --profile <name>`

`{suite, profile, status, exit_code, command, artifacts[]}`. `status` is
`passed` or `failed`; a failure exits 6 with the result recorded.

### `lab run [--backend local|slurm] [--no-container] [--wait]`

```json
{ "run_id": "RUN-000001", "status": "completed", "backend": "local",
  "experiment_id": "EXP-000001", "external_job_id": null, "exit_code": 0,
  "container_digest": null, "configuration_hash": "sha256:...",
  "resources": {...}, "artifacts": ["ART-000003"], "deviations": [], "notes": [] }
```

A cluster run returns as soon as it is queued (`status: "queued"`, exit 0);
`lab status` collects it once it ends. `deviations` is the honest part: it
records what the run could not guarantee, such as executing on the host instead
of in the declared container.

### `lab status <RUN-id>`

The run record plus its artifacts. Reconciles an in-flight cluster job and
collects it if it has finished.

```json
{ "id": "RUN-000001", "status": "completed", "exit_code": 0,
  "configuration_hash": "sha256:...", "deviations": [],
  "artifacts": [{ "id": "ART-000003", "kind": "result", "name": "metrics.json",
                  "checksum": "sha256:...", "size_bytes": 55, "uri": "file://..." }],
  "notes": [] }
```

### `lab cancel <RUN-id>`

`{run_id, status, external_job_id, failure_reason}`. Exit 11 if the run has
already finished.

### `lab report <RUN-id>`

`{run_id, status, artifacts[]}` — `report.html`, `report.json`,
`provenance.json` and `checksums.txt`. Every fact in the report comes from the
run record.

### `lab publish component [--name <name>]`

```json
{ "status": "published", "component_id": "CMP-000001", "name": "...",
  "version": "0.1.0", "maturity": "tested", "project": "PRJ-000001",
  "evidence": [{ "suite": "integration_tests", "profile": "smoke", "status": "passed" }],
  "missing_for_next_level": ["reproducibility_tests"] }
```

Maturity is derived from recorded evidence up to `reproducible`. Publishing a
changed version under the same version number exits 12.

### `lab search components [query] [--status <maturity>] [--limit N]`

`{query, count, results[]}`, each result carrying `id, name, version, maturity,
maintainer, description, keywords, project, command, references, evidence[],
reviewed_by, score`. An empty query lists the registry.

### `lab promote <CMP-id> --to <maturity> --note "..." [--reviewer X]`

`{component_id, version, maturity, decision_id, from_status, reviewer, note}`.
Only `validated`, `lab_standard` and `deprecated` can be granted this way;
asking for an evidenced level exits 3.

### `lab sync obsidian`

`{notes: [{path, outcome, sidecar?, reason?}], conflicts: N}`. `outcome` is
`created`, `updated`, `unchanged` or `conflict`; a conflict means the existing
note was left untouched.

### `lab explain <RUN-id>`

Optional, needs a configured language model; exits 4 when there is none.
`{run_id, provider, model, text, artifact, prompt_artifact}`. The text is
generated and is stored as such, never as part of the run record.

## What an agent should rely on

Read `configuration_hash`, `deviations` and artifact `checksum` values rather
than re-deriving them: they are the record. Treat a component's `maturity` as
meaningless without the `evidence` beside it, and remember that no amount of
passing tests produces `validated` — that is a human judgement the platform
stores separately.

Identifiers (`PRJ-`, `EXP-`, `RUN-`, `CMP-`, `ART-`, `DEC-`) and the
`lab-*://` URIs are the durable handles. Filesystem paths are not.
