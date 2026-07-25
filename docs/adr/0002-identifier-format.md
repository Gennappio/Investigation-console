# ADR 0002: Identifier format and the lab URI scheme

Date: 2026-07-25
Status: accepted

## Context

AGENTS.md shows two identifier widths: section 2.4 uses `PRJ-0001` while
section 6 uses `PRJ-000001`. Implementation needs exactly one canonical form,
because the width is baked into validation regexes, generated JSON Schemas, and
every stored identifier.

Section 2.4 also defines a URI scheme (`lab-project://PRJ-0001`,
`lab-run://RUN-0001`, ...) for resolving identifiers to storage locations.

## Decision

1. Canonical identifiers are a prefix plus **six** zero-padded digits:
   `PRJ-000001`, `EXP-000001`, `RUN-000001`, `CMP-000001`, `WF-000001`,
   `DATA-000001`, `ART-000001`, `REF-000001`, `DEC-000001`. Validation is
   strict: `^PRJ-[0-9]{6}$`. Four-digit forms are rejected.
2. Identifiers are distinct Python types (`lab_domain.ids.TypedId` subclasses),
   not interchangeable strings, per AGENTS.md section 6.
3. The `lab-*://` URI scheme is reserved but **not implemented in Milestone 1**.
   No M1 manifest field carries a lab URI; artifacts, runs, and reports (the
   first real consumers) arrive in Milestone 2, which will add the resolver and
   the `MALFORMED_URI` finding code.

## Alternatives considered

- Four digits per section 2.4: rejected, 9999 objects is a plausible ceiling for
  runs in a busy lab, and section 6 is the normative domain-model section.
- Variable width (`PRJ-1`, `PRJ-000001` both valid): rejected, it makes
  identifiers non-canonical, so string comparison and sorting stop working.
- `NewType` instead of `str` subclasses: rejected, `NewType` gives no runtime
  validation and no Pydantic/JSON Schema integration.

## Consequences

Every identifier is self-describing, fixed-width, and sortable. Malformed
identifiers fail at parse time with a `MALFORMED_ID` finding rather than
propagating into records. The 999999 ceiling per prefix is accepted.

## Migration implications

Widening beyond six digits later would be a manifest schema change requiring a
new `apiVersion` and a data migration of stored identifiers. Adding URI support
in Milestone 2 is additive: identifiers keep their format and gain a resolvable
`lab-<kind>://<id>` projection.
