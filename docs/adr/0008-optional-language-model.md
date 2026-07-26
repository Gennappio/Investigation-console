# ADR 0008: The language model is optional and speaks outside the record

Date: 2026-07-26
Status: accepted

## Context

AGENTS.md section 2.1 permits a language model to assist with documentation,
report summarisation, literature linking and run comparison, while requiring
that the platform work without one and that validation, building, testing,
submission, collection, reporting and provenance stay deterministic. Section 11
is stricter still: execution metadata comes from the run record, never from a
model. Section 17.4 forbids introducing model calls into deterministic paths.

A laboratory nonetheless wants prose: a colleague opening `RUN-000123` a month
later benefits from a paragraph explaining what it was and what to be careful
about.

## Decision

One command, `lab explain <RUN-id>`, may call a model. It obeys four rules.

**It is a port, not a dependency.** `lab_domain.language.LanguageModel` is a
protocol; `lab_llm.OpenRouterModel` implements it against OpenRouter's
OpenAI-compatible endpoint using the standard library, and is injected at
`lab_cli.runtime`. No other service imports it, and swapping providers is one
adapter.

**Unconfigured is a normal state.** With no `OPENROUTER_API_KEY` the command
reports that plainly (exit code 4) and every other command is unaffected. There
is no default model: which model to use has cost and data-handling
consequences, so the platform asks rather than choosing.

**Its output is never evidence.** The summary is stored as its own artifact of
kind `explanation`, carrying the provider, the model that actually served the
request, the SHA-256 of the prompt, and a warning that it is generated text.
The run record is not amended, the report is not rewritten, and no factual
field anywhere is produced by a model.

**What leaves the building is recorded.** The exact prompt is stored next to
the summary as a provenance artifact, and the call is written to the audit log
with the provider and model. Anyone can read afterwards what was sent to a
third party. The prompt is rendered from a template in `templates/prompts/`, so
it can be reviewed and changed without touching code.

## Alternatives considered

- Summaries inside `report.html`: rejected. It would put generated prose in the
  same document as recorded fact, which is precisely what section 11 forbids,
  and a reader would have no way to tell them apart.
- A provider SDK dependency: rejected. One POST does not justify a dependency,
  and a thin client keeps the wire format visible in the repository.
- Shipping a default model: rejected. It would silently spend a laboratory's
  money on a model nobody chose, and model identifiers change.
- An `OPENROUTER_API_KEY` entry in a config file: rejected outright by section
  15.1. The key comes from the environment; a settings file containing one is
  refused, which the tests assert.

## Consequences

The platform still runs, validates, executes and reports with no model, no key
and no network. A laboratory that configures one gains prose that is clearly
marked as prose. Every call has a cost and sends run metadata to a third party;
the audit log and the stored prompt make both visible.

Datasets are not classified in the run record today (section 15.2 defines the
classifications), so `lab explain` cannot yet refuse to describe a run over
restricted or clinical data. Until it can, the stored prompt is what lets a
laboratory audit what was disclosed. Wiring classification into the refusal is
the obvious next step for anyone handling patient-derived data.

Tests never reach a provider: the transport is injected, and a session-wide
fixture fails any test that opens a socket.

## Migration implications

Adding a second provider means a second adapter behind the same protocol.
Additional model-assisted features (run comparison, literature linking) follow
the same four rules; anything that would put generated text into a factual
field needs a new ADR superseding this one.
