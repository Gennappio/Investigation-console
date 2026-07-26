# ADR 0009: Component maturity is evidenced up to a point, then reviewed

Date: 2026-07-26
Status: accepted

## Context

AGENTS.md section 6.4 gives components a maturity ladder — `draft`,
`runnable`, `tested`, `reproducible`, `validated`, `lab_standard`,
`deprecated` — and says that promotion to `validated` or `lab_standard`
requires explicit human review. Section 2.7 insists that test status is never
collapsed into one green check, and that a component which executes
successfully is not thereby scientifically valid.

The question this milestone had to answer is who decides the level. If the
manifest declares it, every component is as mature as its author claims. If
the platform derives all of it, software tests end up implying scientific
validity, which is the failure section 2.7 exists to prevent.

## Decision

Maturity is split at the point where evidence stops being enough.

**Evidenced levels** — `draft`, `runnable`, `tested`, `reproducible` — are
computed by the platform from test results it recorded itself, never declared
in the manifest:

| Level | Requires |
|---|---|
| `draft` | nothing |
| `runnable` | `integration_tests` passed |
| `tested` | `software_tests` and `integration_tests` passed |
| `reproducible` | the above plus `reproducibility_tests` passed |

A component manifest says which command profile proves each category
(`tests: {software_tests: test, integration_tests: smoke}`), and `lab publish`
reads the latest recorded result for each. `evidenced_maturity` cannot return
a reviewed level however much passes.

**Reviewed levels** — `validated`, `lab_standard`, `deprecated` — are granted
only by `lab promote`, which requires a reviewer and a note, and writes a
`DecisionRecord` (`DEC-…`) plus an audit entry. Attempting to promote to an
evidenced level is refused: those are not a matter of opinion. A review
survives republishing of unchanged content, so a routine `lab publish` cannot
quietly undo a principal investigator's judgement.

`lab publish` also reports **what is missing for the next level**, so the
answer to "why is this only runnable?" is in the output rather than in
someone's head.

**A published version is immutable.** Publishing the same name and version
with different content is refused with exit code 12; the fix is a new version.
Republishing identical content is a no-op that refreshes the evidence, which is
what makes `lab test && lab publish` a sensible habit.

## Alternatives considered

- Maturity declared in the manifest: rejected. It records an intention, not a
  fact, and nothing would stop a component from calling itself `validated`.
- Deriving `validated` from a passing scientific-validation suite: rejected.
  Section 6.4 requires human review, and a passing threshold check is evidence
  a reviewer weighs, not the review itself.
- One record per component with a version list inside: rejected. One document
  per published version keeps each version immutable on its own terms and
  matches how the run store already works.

## Consequences

A search result states what a component is proven to do and who, if anyone,
vouched for it. A principal investigator can list what is awaiting review
(`lab search components --status tested`) and record the judgement with a note
that others will read.

Evidence is a snapshot: it reflects the results recorded at publish time, and
a later failing test does not retroactively demote a published version.
Republishing refreshes it. Evidence is also gathered per project, so two
components in the same repository sharing a test profile share its evidence —
acceptable while a repository holds a handful of components, and something to
revisit if components need their own test runs.

## Migration implications

`scientific_validation` is recorded as evidence when a project runs that suite,
but it does not advance the ladder by itself; if a laboratory later wants it to
gate promotion, that is a change to `EVIDENCE_REQUIREMENTS` plus an ADR. Moving
the registry into the operational database keeps the same `ComponentStore`
protocol, as with runs (ADR 0005).
