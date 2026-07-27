# ADR 0011: One contract, three ways in, and the API does not write

Date: 2026-07-27
Status: accepted

## Context

AGENTS.md section 2.6 is explicit: researchers choose their own coding agent,
and the platform must be usable by any of them without special integration.
Section 19 asks Milestone 6 for documented CLI JSON contracts, a Python client,
an optional MCP adapter and example agent instructions, and adds that "the
adapter must not duplicate business logic".

The temptation with an agent-facing layer is to make it convenient by making it
a second implementation: an MCP tool that calls services directly, an HTTP API
that grows its own idea of what publishing means. Then there are three
definitions of "run an experiment", and the one an agent uses is the one nobody
tests.

## Decision

**The CLI JSON contract is the interface.** It is documented in
`docs/protocols/cli.md`, pinned by the tests in `tests/contract/`, and everything
else is built on it.

**The Python client drives the CLI, in a subprocess.** `LabClient` runs
`lab … --json` and parses the documented payload. That costs a process per call
and buys three things: the client cannot drift from the contract, it works
against any installed version, and there is one implementation of what each
command means. It adds one behaviour of its own, and only in how it reports:
exit codes become `LabCommandError`, except for the two that are results rather
than failures — a failing test suite (6) and a failed run (8) are returned,
because both recorded everything they promised.

**The MCP adapter registers the client's operations and returns their payloads
unchanged.** Tool signatures come from the operations themselves, so an agent
sees real parameter names rather than an opaque bag of arguments, and a platform
error is returned as data an agent can act on rather than raised as a crash.

**Writing is opt-in everywhere an agent is involved.** The MCP server offers
only read operations until started with `--allow-writes`. An agent that
connects can look at a laboratory's record; spending its cluster time is a
separate decision.

**The HTTP API is read-only.** Section 14 designs write endpoints, and they are
deliberately not implemented yet: submitting a run spends compute, publishing
and promoting change a laboratory's record, and the platform has no
authorization model (section 15 describes one; nothing implements it). An
unauthenticated POST that executes a repository's commands is the wrong kind of
convenient. The API reports; the CLI acts. Its routes are thin reads over the
same stores and services, they publish stable `lab-*://` URIs, and they never
expose filesystem paths.

## Alternatives considered

- A client that imports the services directly: rejected. It would be faster and
  would duplicate the CLI's composition and error mapping, which is exactly the
  drift this ADR exists to prevent. The process cost is irrelevant next to
  running an experiment.
- Write endpoints behind a shared token: rejected for now. A token is not an
  authorization model — it cannot say who submitted a run, which section 15.3
  requires recorded, and the audit log would name the API rather than a person.
- Skipping the API because Milestone 6 does not list it: rejected. Section 4
  names the CLI plus a minimal API as the first interface, and read access is
  useful immediately for a principal investigator's dashboard.
- A general-purpose coding agent in the platform: forbidden by section 3.2, and
  not attempted.

## Consequences

An agent integrates by reading one document. A change to a payload breaks a
contract test before it reaches anyone's tooling.

The client pays a process launch per call, so it is unsuitable for a hot loop;
nothing in this platform is a hot loop. The API cannot start a run, so a
dashboard can show what happened but not make something happen — deliberate
until authorization exists. `apps/api` is not shipped in the wheel: it is run
from a checkout, and the optional extras (`--extra api`, `--extra mcp`) keep
FastAPI and the MCP SDK out of a default install.

## Migration implications

Write endpoints arrive with the authorization model, not before, and will reuse
the same services the CLI calls, with the run record's `submitted_by` naming a
person rather than a service. Adding an operation means adding it once, in
`lab_api_client.operations`; the MCP adapter picks it up with no further work.
