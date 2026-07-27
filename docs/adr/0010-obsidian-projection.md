# ADR 0010: The vault is a projection, and human text is never overwritten

Date: 2026-07-27
Status: accepted

## Context

AGENTS.md section 12 makes the Obsidian vault a navigable projection of
laboratory knowledge: links and summaries, not heavy artifacts, and never the
source of truth (section 2.5). Section 12.3 sets the rules for keeping a
generated note and a researcher's own writing in the same file, and section
12.4 says which side owns which fact.

Writing into someone's notes is the most destructive thing this platform does.
A wrong artifact can be regenerated; a paragraph of thinking that a program
overwrote is gone.

## Decision

**Three ownerships in one file.** The platform owns a named set of frontmatter
keys and everything between `<!-- BEGIN LAB MANAGED -->` and its end marker. A
human owns everything between the HUMAN NOTES markers and every frontmatter key
the platform does not claim. Regeneration rewrites the managed part and copies
the human part through untouched.

**When in doubt, do not write.** If an existing note has no frontmatter, an
unclosed or unreadable frontmatter, or anything other than exactly one pair of
each marker, the platform refuses to modify it. The generated note is written
beside it as `<name>.lab-conflict.md` and the conflict is reported by the
command. This is section 12.3's "fail safely and create a sidecar" taken
literally: the platform never guesses which text is whose.

**The vault holds links, not contents.** A run note names its artifacts and
links to them by stable URI (`lab-run://RUN-000001/artifacts`,
`lab-report://RUN-000001`); it never contains artifact contents, logs, or
filesystem paths. This is also where the `lab-*://` scheme reserved by ADR 0002
is implemented, now that there are runs, reports and artifacts to address.

**Projection is off until a vault is configured** (`LAB_OBSIDIAN_VAULT` or
`vault` in `$LAB_HOME/obsidian.json`). The platform does not guess a path into
someone's notes.

**Projection never decides whether a command succeeded.** Notes are written
after a run reaches a terminal state and its artifacts are stored. A vault that
is unreachable produces a reported failure, not a failed run: what happened,
happened.

**Nothing secret leaves.** Generated content is scanned with the same patterns
the manifest validator uses, and a note that trips them is not written.

## Alternatives considered

- Separate generated and human files (`RUN-000001.generated.md` beside
  `RUN-000001.md`): rejected. It is safer but splits one thought across two
  files, and section 12.2 shows both sections in a single note.
- Three-way merge against the previously generated content: rejected as
  unnecessary. The platform owns its section outright, so there is nothing to
  merge; the only question is whether the human section can be identified, and
  when it cannot, the answer is to stop.
- Writing the vault from inside the run service: rejected. Execution must not
  depend on a notes directory, and a projection failure must not be able to
  fail a run.

## Consequences

A researcher can write freely in the human section and keep it across any
number of runs. A note that predates the platform, or that someone reformatted
by hand, is preserved and flagged rather than silently replaced.

Frontmatter is round-tripped through YAML, so comments and flow style in
frontmatter are not preserved — `tags: [a, b]` comes back as a block list.
Values survive; formatting does not. Prose belongs in the human section, where
it is copied verbatim.

The vault reflects what has been projected, not what exists: a run finished on
a cluster gets its note when `lab status` collects it, and `lab sync`
backfills a vault configured after the fact. Notes for components and decisions
are not written yet, though the registry holds both; they are the obvious next
addition and need no new machinery.

## Migration implications

Adding a note kind is a template plus a writer function. If the managed-section
format ever changes, existing notes still parse, because the markers are the
contract rather than the content between them.
