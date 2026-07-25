# ADR 0004: JSON Schemas are generated from the Pydantic models

Date: 2026-07-25
Status: accepted

## Context

AGENTS.md section 5 requires `schemas/lab.schema.json` and
`schemas/experiment.schema.json`, and section 17.2 requires schemas to be
updated whenever manifest behavior changes. The same manifest structure is also
expressed by the Pydantic models the platform validates with. Two hand-
maintained descriptions of one structure drift, and the drift is invisible
until a manifest is accepted by one and rejected by the other.

## Decision

The Pydantic models in `lab_domain.manifests.models` are the source of truth.
`lab_domain.schema_export` renders the schema files:

```bash
uv run python -m lab_domain.schema_export schemas/
```

Output is deterministic (`indent=2`, `sort_keys=True`, trailing newline) and the
generated files are committed, so editors and external agents can consume them
without running Python. `tests/contract/test_schema_sync.py` regenerates the
schemas in memory and fails if the committed files differ.

## Alternatives considered

- Hand-written schemas as the source of truth, with models derived from them:
  rejected, code generation from JSON Schema produces models that are harder to
  read than the ones people maintain, and validation behavior would still live
  in Python.
- Generating the schemas at build time without committing them: rejected,
  section 5 lists them as repository contents and agents should be able to read
  them from a checkout.

## Consequences

Schemas cannot silently drift from validation behavior. Changing a model
without regenerating fails the contract test with the regeneration command in
the failure message. Schema comments and hand-tuned descriptions are not
possible; documentation belongs in model docstrings and `Field(description=...)`.

## Migration implications

`component.schema.json` (Milestone 4) and `run.schema.json` (Milestone 2) are
added to the `EXPORTS` table in the same module when those models exist. No
migration is required for existing manifests.
