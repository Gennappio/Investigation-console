# AGENTS.md

## 1. Purpose

This repository implements a **Research Execution Platform** for a small bioinformatics laboratory.

The platform is not a team-monitoring tool and is not a replacement for Git, SLURM, containers, notebooks, workflow engines, or external coding agents.

Its purpose is to make computational research:

- executable;
- reproducible;
- testable;
- traceable;
- reusable;
- searchable;
- reviewable by a Principal Investigator;
- accessible to coding agents through stable interfaces.

The core product is a deterministic platform that manages:

- projects;
- repositories;
- reusable components;
- workflows;
- datasets and dataset references;
- experiments;
- immutable runs;
- containers;
- tests;
- reports;
- provenance;
- publication into an internal registry;
- links to the laboratory Obsidian vault.

Researchers may use Claude Code, Codex, Cursor, terminal tools, notebooks, or no coding agent at all. The platform must remain **agent-agnostic**.

---

## 2. Product principles

All implementation decisions must follow these principles.

### 2.1 Deterministic core, optional intelligence

The platform must work without an LLM.

Core operations such as validation, container building, test execution, SLURM submission, artifact collection, report generation, and provenance capture must be deterministic.

LLM-based features may later assist with:

- repository inspection;
- documentation;
- report summarization;
- literature linking;
- code review;
- experiment suggestions;
- comparison of runs.

LLMs must not be required to reproduce or execute an experiment.

### 2.2 The experiment is the main scientific object

A repository is not an experiment.

A repository may support many experiments. An experiment may use several repositories or components.

The main hierarchy is:

```text
Project
  └── Experiment
        └── Run
```

Reusable technical assets are represented separately:

```text
Component
Workflow
Dataset
Artifact
Reference
```

### 2.3 Runs are immutable

A run records one concrete execution.

After a run starts, the following fields must never be silently changed:

- run identifier;
- experiment identifier;
- Git commit;
- container digest;
- dataset identifiers and versions;
- configuration;
- parameters;
- random seeds;
- execution backend;
- resource request;
- timestamps;
- stdout and stderr references;
- output artifact checksums;
- exit status.

Corrections create a new run or an explicit amendment record. They do not rewrite history.

### 2.4 Stable identifiers, not fragile paths

Never expose raw cluster paths as canonical identifiers.

Avoid storing values such as:

```text
/scratch/alice/project_x/run_14/result.csv
```

as permanent references.

Use stable identifiers and resolvable URIs:

```text
lab-project://PRJ-0001
lab-experiment://EXP-0001
lab-run://RUN-0001
lab-component://CMP-0001
lab-dataset://DATA-0001
lab-artifact://ART-0001
```

The platform may resolve these identifiers to current storage locations.

### 2.5 Obsidian is a knowledge interface, not the source of truth

Obsidian stores:

- scientific context;
- hypotheses;
- decisions;
- interpretation;
- limitations;
- links;
- summaries;
- generated run notes.

Obsidian does not store:

- large datasets;
- model checkpoints;
- container images;
- complete logs;
- job state;
- secrets;
- canonical provenance;
- authorization rules.

The operational database and artifact store remain authoritative.

### 2.6 Researchers choose their coding agent

Do not build a proprietary general-purpose coding agent in the MVP.

Instead, provide:

- a stable CLI;
- machine-readable JSON output;
- a REST API;
- versioned YAML/JSON schemas;
- clear exit codes;
- reproducible commands.

An MCP server or IDE integration may be added later as an adapter over the same interfaces.

### 2.7 Test status must be explicit

Do not collapse all validation into a single green check.

Track at least:

1. software tests;
2. workflow or integration tests;
3. reproducibility tests;
4. scientific validation.

Example:

```text
software_tests: passed
integration_tests: passed
reproducibility_tests: passed
scientific_validation: partial
```

A component that executes successfully is not automatically scientifically valid.

### 2.8 No productivity surveillance

Do not implement:

- researcher rankings;
- commit-based productivity scores;
- time-online tracking;
- code-volume rankings;
- automated employee performance judgments.

The PI interface focuses on:

- experiment status;
- evidence;
- blockers;
- reproducibility;
- decisions;
- reusable assets;
- scientific risks.

---

## 3. Initial scope

The first release must support one complete vertical workflow:

```text
Initialize project
→ validate manifest
→ build container
→ execute tests
→ run locally or on SLURM
→ collect artifacts
→ generate report
→ register run
→ generate/update Obsidian note
```

### 3.1 MVP commands

The initial CLI must expose:

```bash
lab init
lab validate
lab inspect
lab build
lab test
lab run
lab status
lab report
lab publish
lab search
```

Expected examples:

```bash
lab init tcell-calibration
lab validate
lab build
lab test --profile smoke
lab run --backend local
lab run --backend slurm
lab status RUN-0001
lab report RUN-0001
lab publish component
lab search components "sensitivity analysis" --json
```

### 3.2 Explicitly out of scope for the first release

Do not implement these before the vertical workflow is reliable:

- a proprietary coding agent;
- autonomous scientific conclusions;
- automatic paper writing;
- automatic promotion to `LAB_STANDARD`;
- full workflow composition by an LLM;
- a general ontology platform;
- real-time collaborative document editing;
- replacement of GitHub or GitLab;
- replacement of SLURM;
- replacement of Nextflow, Snakemake, or Galaxy;
- granular Obsidian access control;
- large-scale multi-institution tenancy;
- complex billing or resource accounting.

---

## 4. Recommended technology stack

Use the following stack unless a documented architectural decision changes it.

### Backend and domain

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic
- PostgreSQL
- Typer for the CLI

### Storage

For development:

- local filesystem artifact backend;
- SQLite may be used only for isolated tests.

For deployment:

- PostgreSQL for operational metadata;
- S3-compatible storage such as MinIO for reports and artifacts;
- GitLab or GitHub for source code;
- OCI registry for containers.

### Execution

- Docker for local development and CI;
- Apptainer/Singularity support for HPC execution;
- SLURM adapter using `sbatch`, `squeue`, `sacct`, and `scancel`;
- subprocess-based local runner;
- generic container execution before workflow-engine-specific integrations.

### Reporting

- Jinja2 for structured HTML reports;
- optional Quarto integration after the basic report path works;
- JSON report generated alongside HTML;
- RO-Crate support introduced incrementally.

### Testing and quality

- pytest;
- pytest-asyncio where needed;
- Ruff;
- mypy or pyright;
- pre-commit;
- coverage reporting;
- integration tests using temporary PostgreSQL and filesystem storage;
- SLURM command adapters tested through fakes, not a live cluster in unit tests.

### Frontend

Do not start with a large frontend.

The first interface is the CLI plus a minimal FastAPI API.

A React or Next.js interface may be added after the core execution workflow is stable.

---

## 5. Repository structure

Prefer a Python monorepo with clear package boundaries.

```text
.
├── AGENTS.md
├── README.md
├── pyproject.toml
├── alembic.ini
├── apps/
│   └── api/
│       ├── main.py
│       └── routes/
├── packages/
│   ├── lab_cli/
│   ├── lab_domain/
│   ├── lab_registry/
│   ├── lab_execution/
│   ├── lab_containers/
│   ├── lab_slurm/
│   ├── lab_artifacts/
│   ├── lab_reporting/
│   ├── lab_obsidian/
│   └── lab_api_client/
├── schemas/
│   ├── lab.schema.json
│   ├── experiment.schema.json
│   ├── component.schema.json
│   └── run.schema.json
├── templates/
│   ├── project/
│   ├── report/
│   └── obsidian/
├── examples/
│   ├── python-model/
│   └── container-job/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
├── migrations/
├── docs/
│   ├── architecture/
│   ├── adr/
│   └── protocols/
└── infra/
    ├── docker/
    └── compose/
```

Rules:

- Domain models belong in `lab_domain`.
- Infrastructure-specific code must not leak into domain models.
- SLURM commands belong in `lab_slurm`.
- Docker and Apptainer logic belongs in `lab_containers`.
- Obsidian generation belongs in `lab_obsidian`.
- API route handlers must remain thin.
- CLI commands must call application services, not duplicate business logic.

---

## 6. Domain model

Use typed identifiers. Do not pass unrelated IDs as plain interchangeable strings inside the domain layer.

Recommended identifiers:

```text
PRJ-000001
EXP-000001
RUN-000001
CMP-000001
WF-000001
DATA-000001
ART-000001
REF-000001
DEC-000001
```

### 6.1 Project

A project groups related scientific work.

Minimum fields:

```yaml
id: PRJ-000001
title: T-cell differentiation modelling
description: ...
status: active
owners:
  - user-id
repositories:
  - repository-id
created_at: ...
updated_at: ...
```

### 6.2 Experiment

An experiment represents a scientific question and a reproducible design.

Minimum fields:

```yaml
id: EXP-000001
project_id: PRJ-000001
title: IL-6 and Th17 differentiation
question: ...
hypothesis: ...
status: draft
owner: user-id
workflow_ref: WF-000001
dataset_refs:
  - DATA-000001
parameters:
  repetitions: 30
  seed_policy: explicit
references:
  - REF-000001
created_at: ...
```

Recommended states:

```text
draft
ready
running
completed
failed
under_review
validated
archived
```

### 6.3 Run

A run is an immutable execution record.

Minimum fields:

```yaml
id: RUN-000001
experiment_id: EXP-000001
status: queued
backend: slurm
code:
  repository: https://git.example/lab/tcell-model
  commit: a91bd29
container:
  image: registry.example/lab/tcell-model
  digest: sha256:...
datasets:
  - id: DATA-000001
    version: v4
configuration_hash: sha256:...
parameters:
  repetitions: 30
seeds:
  - 101
resources:
  cpus: 32
  memory_mb: 131072
  gpus: 0
execution:
  cluster: bio-cluster
  slurm_job_id: null
created_at: ...
```

### 6.4 Component

A component is a reusable executable asset.

Minimum fields:

```yaml
id: CMP-000001
name: sobol-sensitivity-analysis
version: 1.0.0
status: tested
maintainer: user-id
command:
  - python
  - -m
  - lab_components.sobol
inputs: {}
outputs: {}
container: {}
tests: {}
references: []
```

Recommended maturity levels:

```text
draft
runnable
tested
reproducible
validated
lab_standard
deprecated
```

Promotion to `validated` or `lab_standard` requires explicit human review.

### 6.5 Dataset

Store metadata and references, not necessarily the data itself.

Minimum fields:

```yaml
id: DATA-000001
name: murine-tcell-v4
version: v4
uri: s3://lab-data/tcell/murine-v4
checksum: sha256:...
classification: internal
owner: user-id
format: h5ad
```

### 6.6 Artifact

Every relevant run output becomes an artifact record.

Minimum fields:

```yaml
id: ART-000001
run_id: RUN-000001
kind: result
name: summary.parquet
uri: s3://lab-results/EXP-000001/RUN-000001/summary.parquet
checksum: sha256:...
size_bytes: 123456
media_type: application/vnd.apache.parquet
created_at: ...
```

---

## 7. Manifest files

### 7.1 `lab.yaml`

Every managed repository must contain a root-level `lab.yaml`.

Example:

```yaml
apiVersion: lab/v1
kind: Repository

metadata:
  name: tcell-model
  description: Agent-based model of T-cell differentiation
  owners:
    - anna.rossi

spec:
  project: PRJ-000001

  runtime:
    type: python
    version: "3.12"

  container:
    dockerfile: containers/Dockerfile
    context: .

  commands:
    test:
      - pytest
      - -q

    smoke:
      - python
      - -m
      - tcell_model.run
      - --config
      - configs/smoke.yaml

    run:
      - python
      - -m
      - tcell_model.run
      - --config
      - "${LAB_EXPERIMENT_CONFIG}"

  outputs:
    directory: results

  reporting:
    template: default

  obsidian:
    project_note: Projects/PRJ-000001.md
```

### 7.2 `experiment.yaml`

Each experiment must have a version-controlled specification.

Example:

```yaml
apiVersion: lab/v1
kind: Experiment

metadata:
  id: EXP-000001
  title: IL-6 and Th17 differentiation
  project: PRJ-000001
  owner: anna.rossi

scientific:
  question: Does increasing IL-6 alter the final Th1/Th17 ratio?
  hypothesis: Higher IL-6 increases the stable Th17 fraction.
  references:
    - doi:10.0000/example

execution:
  component: CMP-000001
  dataset_refs:
    - DATA-000001

  parameters:
    il6_values: [0, 1, 2, 5, 10]
    repetitions: 30

  seeds:
    strategy: explicit
    values: [101, 102, 103]

  resources:
    cpus: 32
    memory: 128GiB
    time_limit: "06:00:00"

validation:
  software_tests: required
  integration_tests: required
  reproducibility_tests: required
  scientific_validation: optional
```

### 7.3 Validation rules

The validator must reject:

- unknown schema versions;
- missing required identifiers;
- non-versioned container references for publishable runs;
- floating Git branches in immutable run records;
- missing dataset version;
- unbounded resource requests;
- missing output location;
- malformed stable URIs;
- secrets embedded in manifests.

Warnings may be emitted for:

- missing literature references;
- missing scientific validation;
- missing negative controls;
- missing seed policy;
- missing maintainer;
- use of mutable container tags.

---

## 8. Execution architecture

Define an execution backend interface.

```python
class ExecutionBackend(Protocol):
    def submit(self, request: RunRequest) -> SubmissionResult: ...
    def status(self, external_job_id: str) -> JobStatus: ...
    def cancel(self, external_job_id: str) -> None: ...
    def collect(self, external_job_id: str) -> CollectionResult: ...
```

Initial implementations:

- `LocalExecutionBackend`
- `SlurmExecutionBackend`

Future implementations may include Kubernetes or cloud batch services without changing the domain model.

### 8.1 Local execution

Local execution must:

- run in an isolated working directory;
- use a container when the manifest requires one;
- capture stdout and stderr;
- record exit code;
- calculate checksums;
- enforce timeouts;
- return structured errors.

### 8.2 SLURM execution

The SLURM adapter must:

1. render an `sbatch` script from a typed request;
2. submit it with `sbatch --parsable`;
3. store the returned job ID;
4. query state with `squeue` and `sacct`;
5. support cancellation with `scancel`;
6. collect logs and exit status;
7. copy final artifacts to permanent storage;
8. avoid treating scratch storage as permanent.

Do not parse human-formatted command output when a machine-readable option exists.

The generated job script must include:

- run ID;
- experiment ID;
- code commit;
- container digest;
- resource request;
- working directory;
- output directory;
- explicit environment variables;
- strict shell settings.

Recommended shell preamble:

```bash
set -euo pipefail
```

### 8.3 Scratch and permanent storage

Scratch is temporary:

```text
/scratch/$USER/lab/RUN-000001
```

Permanent artifact storage is separate.

A run must be marked `completed` only after required artifacts and metadata are safely stored in the permanent backend.

---

## 9. Containers

### 9.1 Container rules

- Record image digest, not only tag.
- Prefer multi-stage builds.
- Avoid installing packages at runtime.
- Run as a non-root user when possible.
- Keep images minimal but debuggable.
- Pin dependencies.
- Store build logs.
- Record build context hash.
- Support conversion or execution through Apptainer on SLURM.

### 9.2 Build contract

`lab build` must:

1. validate `lab.yaml`;
2. build the image;
3. inspect the resulting image;
4. record its digest;
5. optionally run a container smoke test;
6. write a machine-readable build result.

Example JSON output:

```json
{
  "status": "success",
  "image": "registry.lab/tcell-model:1.0.0",
  "digest": "sha256:...",
  "build_log_artifact": "lab-artifact://ART-000010"
}
```

### 9.3 Network policy

Execution containers should have network access disabled by default.

Network access must be explicitly requested and recorded when necessary.

Never pass long-lived credentials directly into generated scripts or Markdown files.

---

## 10. Testing protocol

### 10.1 Software tests

Examples:

- unit tests;
- type checks;
- static analysis;
- edge cases;
- error handling.

### 10.2 Integration tests

Examples:

- complete execution on small input;
- input/output format compatibility;
- container startup;
- workflow step integration;
- artifact production.

### 10.3 Reproducibility tests

Examples:

- clean container build;
- no undeclared local paths;
- fixed dependencies;
- explicit seeds;
- reproducible output within tolerance;
- output checksum or metric comparison;
- no hidden environment assumptions.

### 10.4 Scientific validation

Examples:

- known benchmark recovery;
- control dataset;
- negative control;
- comparison with a published baseline;
- expected monotonic behavior;
- robustness across seeds;
- sensitivity analysis;
- figure or table reproduction.

Scientific validation results must include:

- validation name;
- dataset;
- metric;
- threshold;
- observed value;
- pass/fail/partial;
- evidence artifact;
- reviewer where applicable.

### 10.5 Test result model

Every test execution must generate structured output.

```yaml
suite: reproducibility
status: passed
started_at: ...
completed_at: ...
checks:
  - name: clean_container_execution
    status: passed
  - name: explicit_seed
    status: passed
  - name: output_tolerance
    status: passed
    observed: 0.998
    threshold: 0.99
artifacts:
  - lab-artifact://ART-000020
```

---

## 11. Reporting

Every completed run must generate:

```text
report.html
report.json
provenance.json
manifest.snapshot.yaml
checksums.txt
```

A PDF report is optional in the MVP.

Minimum report sections:

1. scientific question;
2. hypothesis;
3. input datasets;
4. data provenance;
5. code revision;
6. container digest;
7. parameters;
8. resource usage;
9. test results;
10. outputs;
11. main metrics;
12. deviations from protocol;
13. limitations;
14. reproduction command;
15. literature references.

Do not let an LLM generate factual execution metadata. Metadata must come from the run record.

Human-authored interpretation may be added separately.

---

## 12. Obsidian integration

### 12.1 Role

The vault is a navigable projection of laboratory knowledge.

It must contain links and summaries, not heavy artifacts.

Suggested vault structure:

```text
Projects/
Experiments/
Runs/
Components/
Datasets/
Methods/
Papers/
Decisions/
People/
Templates/
```

### 12.2 Generated run note

Example:

```markdown
---
type: run
run_id: RUN-000001
experiment: "[[EXP-000001]]"
status: completed
backend: slurm
slurm_job_id: "948231"
git_commit: a91bd29
container_digest: sha256:...
report_uri: lab-report://RUN-000001
artifacts_uri: lab-run://RUN-000001/artifacts
managed_by: lab-platform
---

# RUN-000001

<!-- BEGIN LAB MANAGED -->

## Execution summary

- Status: completed
- Duration: 3h 37m
- CPUs: 32
- Memory: 128 GiB
- Tests: passed
- Report: [Open report](lab-report://RUN-000001)

## Main outputs

- [[ART-000001]]
- [[ART-000002]]

<!-- END LAB MANAGED -->

<!-- BEGIN HUMAN NOTES -->

## Interpretation

## Limitations

## Follow-up

<!-- END HUMAN NOTES -->
```

### 12.3 Synchronization rules

- The platform owns frontmatter fields marked as managed.
- The platform owns content inside `BEGIN LAB MANAGED`.
- Humans own content inside `BEGIN HUMAN NOTES`.
- Regeneration must preserve human-authored sections.
- Conflicts must fail safely and create a sidecar file rather than overwrite human text.
- The vault must never contain secrets.
- Generated links should use stable laboratory URIs where possible.

### 12.4 Source-of-truth rules

| Information | Source of truth |
|---|---|
| Run status | operational database |
| SLURM job ID | operational database |
| Git commit | run record |
| Container digest | run record |
| Artifact URI | artifact registry |
| Scientific interpretation | Obsidian or approved report |
| Human decision | decision record plus Obsidian note |
| Permissions | platform database |

---

## 13. CLI design

The CLI is the primary integration surface for humans and external coding agents.

### 13.1 Requirements

Every command must provide:

- human-readable output by default;
- `--json` machine-readable output;
- stable exit codes;
- actionable error messages;
- `--help`;
- dry-run support for destructive or expensive operations where applicable.

### 13.2 Exit codes

Recommended convention:

```text
0  success
2  invalid user input
3  manifest validation failed
4  dependency or environment error
5  build failed
6  tests failed
7  execution submission failed
8  execution failed
9  artifact collection failed
10 authorization denied
11 resource not found
12 conflict
```

### 13.3 Agent-friendly output

Do not require parsing prose.

Example:

```bash
lab validate --json
```

```json
{
  "valid": false,
  "errors": [
    {
      "code": "MISSING_DATASET_VERSION",
      "path": "execution.dataset_refs[0]",
      "message": "Dataset DATA-000001 requires an explicit version."
    }
  ],
  "warnings": []
}
```

### 13.4 No hidden mutations

Commands that modify state must state what they changed.

Commands that submit expensive jobs must print:

- run ID;
- backend;
- requested resources;
- estimated scope where available;
- external job ID after submission.

---

## 14. API design

The API mirrors the CLI capabilities.

Initial resources:

```text
/projects
/experiments
/runs
/components
/datasets
/artifacts
/reports
/execution-backends
```

Recommended endpoints:

```text
POST   /experiments
GET    /experiments/{id}
POST   /runs
GET    /runs/{id}
POST   /runs/{id}/submit
GET    /runs/{id}/status
POST   /runs/{id}/cancel
GET    /runs/{id}/report
GET    /components
POST   /components/{id}/publish
```

Rules:

- Use idempotency keys for run creation and submission.
- Return typed error objects.
- Do not expose internal filesystem paths unless the caller is authorized and explicitly requests operational details.
- Prefer stable URIs in API responses.
- Version the API.

---

## 15. Security and privacy

### 15.1 Secrets

Never commit or write to Obsidian:

- access tokens;
- database passwords;
- SSH private keys;
- cloud credentials;
- registry passwords;
- patient identifiers;
- protected dataset credentials.

Use environment injection, a secret manager, or short-lived credentials.

### 15.2 Data classification

Every dataset should have a classification such as:

```text
public
internal
restricted
clinical
```

Execution and artifact access policies must respect classification.

### 15.3 Cluster safety

- Validate resource requests.
- Limit maximum CPU, memory, GPU, and wall time by policy.
- Disable container privilege escalation.
- Avoid arbitrary host mounts.
- Sanitize generated job names and paths.
- Never interpolate untrusted text directly into shell scripts.
- Use typed templates and shell escaping.
- Record who submitted each run.

### 15.4 Auditability

Record significant actions:

- experiment created;
- run created;
- run submitted;
- run cancelled;
- artifact published;
- component promoted;
- report approved;
- decision recorded.

Audit logs are append-only.

---

## 16. Coding standards

### 16.1 Python

- Use full type annotations.
- Prefer dataclasses or Pydantic models for structured data.
- Do not pass unstructured dictionaries across package boundaries.
- Avoid global mutable state.
- Use dependency injection for database, storage, and execution backends.
- Keep functions small and explicit.
- Raise domain-specific exceptions.
- Preserve exception causes with `raise ... from ...`.
- Use UTC internally.
- Serialize timestamps in ISO 8601.
- Use `pathlib.Path`.
- Never call shell commands with `shell=True` unless a reviewed exception is documented.

### 16.2 Database

- Use migrations for schema changes.
- Do not manually edit production tables.
- Add indexes for stable IDs, status, project, experiment, and creation time.
- Store immutable run snapshots.
- Use transactions around state transitions.
- Validate allowed state transitions in the application layer.

### 16.3 State transitions

State transitions must be explicit.

Example:

```text
created → validated → queued → running → completed
                                  └────→ failed
queued → cancelled
running → cancelled
```

Reject impossible transitions.

### 16.4 Logging

Use structured logs containing, where applicable:

```text
project_id
experiment_id
run_id
external_job_id
component_id
artifact_id
```

Do not log secrets or protected data.

---

## 17. Development workflow for coding agents

When modifying this repository, agents must follow this sequence.

### 17.1 Before coding

1. Read this file.
2. Read the relevant package README.
3. Inspect existing tests.
4. Identify the domain boundary affected.
5. State assumptions in the pull request or implementation notes.
6. Avoid adding dependencies without justification.

### 17.2 During coding

1. Modify the smallest responsible package.
2. Add or update typed models first.
3. Keep infrastructure behind interfaces.
4. Add tests with the implementation.
5. Preserve backward compatibility unless an ADR approves a breaking change.
6. Update schemas when manifest behavior changes.
7. Update examples when public interfaces change.
8. Do not introduce LLM calls into deterministic execution paths.

### 17.3 Before finishing

Run:

```bash
ruff check .
ruff format --check .
mypy packages apps
pytest
```

Also run the relevant contract or integration tests.

The final response or pull request summary must state:

- what changed;
- why;
- tests run;
- migration impact;
- security impact;
- remaining limitations.

### 17.4 Prohibited shortcuts

Agents must not:

- fake successful command output;
- mark tests as passed without execution;
- weaken validation to make a test pass;
- swallow exceptions silently;
- store raw secrets;
- write directly to managed Obsidian sections without preserving human notes;
- update a completed run in place;
- infer scientific validity from software test success;
- make network access the default;
- add a general-purpose coding agent to the core.

---

## 18. Architectural decision records

Significant decisions require an ADR in:

```text
docs/adr/
```

Use:

```text
0001-record-architecture-decisions.md
0002-stable-lab-uri-scheme.md
0003-slurm-execution-adapter.md
0004-obsidian-projection-model.md
```

An ADR must include:

- context;
- decision;
- alternatives considered;
- consequences;
- migration implications.

---

## 19. First implementation milestones

### Milestone 1: project and manifest foundation

Deliver:

- `lab init`;
- `lab.yaml` schema;
- `experiment.yaml` schema;
- typed domain models;
- validation;
- project template;
- JSON CLI output.

Acceptance criteria:

```bash
lab init demo
cd demo
lab validate
```

must succeed on the generated project.

### Milestone 2: local execution

Deliver:

- local backend;
- container build;
- test execution;
- run record;
- stdout and stderr capture;
- artifact checksums;
- HTML and JSON report.

Acceptance criteria:

```bash
lab build
lab test --profile smoke
lab run --backend local
lab report RUN-...
```

must complete using the example project.

### Milestone 3: SLURM execution

Deliver:

- SLURM backend;
- `sbatch` generation;
- submission;
- state polling;
- cancellation;
- artifact collection;
- scratch cleanup policy;
- fake-SLURM integration tests.

Acceptance criteria:

- a real test job can be submitted to the laboratory cluster;
- job status is reflected in the platform;
- final outputs are copied to permanent storage;
- the run report includes SLURM metadata.

### Milestone 4: registry

Deliver:

- component registration;
- maturity state;
- test summaries;
- versioning;
- search;
- publish workflow.

Acceptance criteria:

```bash
lab search components "sensitivity analysis"
```

returns registered, tested components with machine-readable metadata.

### Milestone 5: Obsidian projection

Deliver:

- project note generation;
- experiment note generation;
- immutable run note generation;
- managed/human section preservation;
- stable URI links.

Acceptance criteria:

- completion of a run creates or updates the expected Markdown notes;
- human text is preserved after regeneration.

### Milestone 6: external agent integration

Deliver:

- documented CLI JSON contracts;
- Python client;
- optional MCP adapter;
- example instructions for Claude Code and Codex.

The adapter must not duplicate business logic.

---

## 20. Definition of done for the MVP

The MVP is complete when a researcher can:

1. create a project from a template;
2. define an experiment in YAML;
3. validate it;
4. build a pinned container;
5. run software and smoke tests;
6. launch the same experiment locally or through SLURM;
7. inspect status;
8. obtain logs and artifacts;
9. generate a structured report;
10. reproduce the run from recorded metadata;
11. publish a reusable component;
12. browse generated project, experiment, and run notes in Obsidian;
13. use an external coding agent through CLI or API without special integration.

The PI must be able to:

1. open an experiment;
2. see its scientific question and status;
3. inspect completed runs;
4. distinguish software correctness from scientific validation;
5. open reports and artifacts through stable links;
6. identify components ready for review;
7. record an approval, rejection, or requested follow-up.

---

## 21. Guiding product statement

When uncertain, optimize for this outcome:

> A researcher may use any coding environment, but every important experiment can be executed through a shared, deterministic protocol and leaves behind an immutable, searchable, reviewable, and reusable scientific record.

The durable value of the platform is not the language model.

The durable value is:

- validated components;
- executable protocols;
- reproducible runs;
- containerized environments;
- scientific test evidence;
- stable provenance;
- structured reports;
- links to literature;
- institutional memory.
