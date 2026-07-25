# ADR 0003: Local registry state under LAB_HOME

Date: 2026-07-25
Status: accepted

## Context

`lab init` must allocate stable identifiers (`PRJ-000001`, `EXP-000001`) before
any operational database exists. AGENTS.md section 4 specifies PostgreSQL for
deployment, but Milestone 1 delivers only the manifest foundation; requiring a
database to scaffold a project would make the first command unusable on a
laptop and would pull SQLAlchemy and Alembic into a milestone that stores no
run records.

## Decision

Milestone 1 allocates identifiers through `lab_registry.LocalRegistry`, a
file-backed store:

- state lives in `$LAB_HOME/registry.json` (`LAB_HOME` defaults to `~/.lab`);
- the document holds `schema_version`, per-prefix `counters`, and a list of
  `ProjectRecord` entries;
- writes go to a temporary file in the same directory and are moved into place
  with `os.replace`, so a crash never leaves a partially written state file;
- an unreadable or malformed state file raises `StateStoreError`, surfaced as
  exit code 4, rather than silently resetting counters.

Services depend on the `lab_domain.registry.ProjectRegistry` protocol and
receive the implementation by injection, so the store is replaceable.

## Alternatives considered

- SQLite: rejected for Milestone 1. AGENTS.md section 4 permits SQLite only for
  isolated tests, and a single JSON document needs no schema migration tooling
  for two counters and a small index.
- Deriving identifiers from a hash of the project name: rejected, identifiers
  would not be sequential or human-orderable, and collisions would be silent.
- Requiring PostgreSQL immediately: rejected, it blocks Milestone 1 on
  infrastructure that stores nothing yet.

## Consequences

`lab init` works offline with no services running. The store assumes a single
writer: two concurrent `lab init` runs sharing one `LAB_HOME` could allocate the
same counter, because the read-modify-write cycle is not locked. This is
accepted for a single-researcher workstation and disappears with database
sequences in Milestone 2. Identifiers are unique per `LAB_HOME`, not globally;
projects created on two machines can collide until they are registered
centrally.

## Migration implications

Milestone 2 adds a PostgreSQL-backed implementation of the same protocol. The
migration reads `registry.json`, seeds each database sequence from the stored
counter, and inserts each `ProjectRecord` as a row; `schema_version` identifies
the format being migrated. Nothing in the domain or CLI changes.
