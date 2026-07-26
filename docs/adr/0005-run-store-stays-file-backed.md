# ADR 0005: Run records stay file-backed in Milestone 2

Date: 2026-07-26
Status: accepted

## Context

Milestone 2 introduces run records, artifacts and test evidence. AGENTS.md
section 4 names PostgreSQL as the operational database for deployment, and
section 16.2 asks for migrations, indexes and transactions around state
transitions.

Milestone 2 delivers a single-researcher local vertical slice: build, test,
run, collect, report. Its queries are "get this run", "list runs of this
experiment" and "list test results of this project", over tens of records
written by one process at a time. There is no API, no concurrent writer and no
cross-machine access yet; those arrive with the API and the registry.

## Decision

Runs, test evidence and the artifact index remain file-backed under `LAB_HOME`,
extending ADR 0003:

- `runs/RUN-000001.json` — one document per run;
- `tests/<PRJ-id>/<suite>-<timestamp>.json` — one document per suite execution;
- `artifacts/<RUN-id>/artifacts.json` — the artifact index of a run;
- `audit.jsonl` — the append-only audit log (AGENTS.md section 15.4).

All writes go through `lab_registry.files.write_atomically`. Immutability is
enforced in the domain, not by the storage: `lab_domain.runs.ensure_amendable`
refuses any save that would change a provenance field or reopen a finished run,
so the guarantee holds whichever store is used.

Services depend on the `RunStore` and `ArtifactStore` protocols in
`lab_domain.storage`, never on the file layout.

## Alternatives considered

- PostgreSQL with SQLAlchemy and Alembic now: rejected for this milestone. It
  makes running one local experiment depend on a database server, and none of
  the properties it provides (concurrent writers, indexed queries over many
  runs, transactional multi-row updates) is exercised by a single-process local
  runner. It also could not be verified end to end on the development machine
  used for this milestone.
- SQLite as the development store: rejected because AGENTS.md section 4 permits
  SQLite only for isolated tests, and it would add a schema and migrations
  without providing the concurrency the file store lacks.

## Consequences

The whole vertical slice runs offline with no services. Two commands sharing a
`LAB_HOME` can still race: identifier allocation is a read-modify-write on one
JSON file, and a run saved concurrently by two processes is last-write-wins.
This is acceptable for a workstation and unacceptable for the API. Listing runs
reads every record, which is fine for hundreds and not for millions.

## Migration implications

The database implementation replaces `FileRunStore` and
`FilesystemArtifactStore` behind the same protocols. The migration walks
`LAB_HOME`, inserts each run, artifact and suite result as a row, and seeds the
identifier sequences from `registry.json`. Records already carry every field
the schema needs, so no data is reconstructed. `lab_domain` and `lab_cli` do not
change.
