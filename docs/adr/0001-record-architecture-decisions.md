# ADR 0001: Record architecture decisions

Date: 2026-07-25
Status: accepted

## Context

AGENTS.md §18 requires significant decisions to be captured as architectural
decision records so that future contributors (human or coding agent) can
understand why the platform is shaped the way it is.

## Decision

We record architecture decisions as numbered Markdown files in `docs/adr/`,
following the sequence `NNNN-short-title.md`. Each ADR contains: context,
decision, alternatives considered, consequences, and migration implications.

## Alternatives considered

- No records (rejected: violates AGENTS.md §18 and loses institutional memory).
- A wiki or external tool (rejected: decisions must live with the code and be
  reviewable in the same pull request that implements them).

## Consequences

Every later ADR in this directory is authoritative over informal notes.
Superseded ADRs are marked `Status: superseded by NNNN`, never deleted.

## Migration implications

None. This ADR bootstraps the process.
