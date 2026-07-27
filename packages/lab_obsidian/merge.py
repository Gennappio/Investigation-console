"""Merging generated content into a note without touching human text.

The rules are AGENTS.md section 12.3. The platform owns a named set of
frontmatter keys and everything between the LAB MANAGED markers. A human owns
everything between the HUMAN NOTES markers, and any frontmatter key the
platform does not claim.

When a note cannot be parsed with confidence — no markers, duplicated markers,
unreadable frontmatter — nothing is overwritten. The generated note is written
beside it as a sidecar and the conflict is reported, because a researcher's
notes are not something to gamble with.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

MANAGED_BEGIN = "<!-- BEGIN LAB MANAGED -->"
MANAGED_END = "<!-- END LAB MANAGED -->"
HUMAN_BEGIN = "<!-- BEGIN HUMAN NOTES -->"
HUMAN_END = "<!-- END HUMAN NOTES -->"
FRONTMATTER_FENCE = "---"
MANAGED_BY = "lab-platform"
SIDECAR_SUFFIX = ".lab-conflict.md"


class WriteOutcome(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class NoteWrite:
    path: Path
    outcome: WriteOutcome
    # Where the generated note went when the existing one could not be touched.
    sidecar: Path | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ParsedNote:
    frontmatter: dict[str, Any]
    managed: str
    human: str


class ConflictError(Exception):
    """The existing note cannot be updated safely."""


def render_note(
    frontmatter: dict[str, Any], managed: str, human: str, title: str
) -> str:
    """Assemble a note from its three parts."""
    document = [
        FRONTMATTER_FENCE,
        yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip(),
        FRONTMATTER_FENCE,
        "",
        f"# {title}",
        "",
        MANAGED_BEGIN,
        "",
        managed.strip(),
        "",
        MANAGED_END,
        "",
        HUMAN_BEGIN,
        "",
        human.strip("\n"),
        "",
        HUMAN_END,
        "",
    ]
    return "\n".join(document)


def parse_note(text: str) -> ParsedNote:
    """Split an existing note into its parts, or refuse to guess."""
    frontmatter, body = _split_frontmatter(text)
    return ParsedNote(
        frontmatter=frontmatter,
        managed=_section(body, MANAGED_BEGIN, MANAGED_END, "managed"),
        human=_section(body, HUMAN_BEGIN, HUMAN_END, "human"),
    )


def write_note(
    path: Path,
    *,
    frontmatter: dict[str, Any],
    managed: str,
    title: str,
    human_placeholder: str,
) -> NoteWrite:
    """Create or update a note, never overwriting human-authored text."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            render_note(frontmatter, managed, human_placeholder, title),
            encoding="utf-8",
        )
        return NoteWrite(path=path, outcome=WriteOutcome.CREATED)

    existing_text = path.read_text(encoding="utf-8")
    try:
        existing = parse_note(existing_text)
    except ConflictError as exc:
        return _sidecar(path, frontmatter, managed, title, human_placeholder, str(exc))

    merged = render_note(
        {**existing.frontmatter, **frontmatter},
        managed,
        existing.human,
        title,
    )
    if merged == existing_text:
        return NoteWrite(path=path, outcome=WriteOutcome.UNCHANGED)
    path.write_text(merged, encoding="utf-8")
    return NoteWrite(path=path, outcome=WriteOutcome.UPDATED)


def _sidecar(
    path: Path,
    frontmatter: dict[str, Any],
    managed: str,
    title: str,
    human: str,
    reason: str,
) -> NoteWrite:
    sidecar = path.with_suffix("").with_name(path.stem + SIDECAR_SUFFIX)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(
        render_note(frontmatter, managed, human, title), encoding="utf-8"
    )
    return NoteWrite(
        path=path,
        outcome=WriteOutcome.CONFLICT,
        sidecar=sidecar,
        reason=reason,
    )


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        raise ConflictError("The note has no frontmatter block.")
    try:
        closing = next(
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == FRONTMATTER_FENCE
        )
    except StopIteration:
        raise ConflictError("The frontmatter block is not closed.") from None

    try:
        loaded = yaml.safe_load("\n".join(lines[1:closing])) or {}
    except yaml.YAMLError as exc:
        raise ConflictError(f"The frontmatter is not readable: {exc}.") from exc
    if not isinstance(loaded, dict):
        raise ConflictError("The frontmatter is not a mapping.")
    return loaded, "\n".join(lines[closing + 1 :])


def _section(body: str, begin: str, end: str, name: str) -> str:
    """The text between two markers, insisting there is exactly one pair."""
    if body.count(begin) != 1 or body.count(end) != 1:
        raise ConflictError(
            f"The note does not have exactly one {name} section; refusing to "
            "guess which text is whose."
        )
    start = body.index(begin) + len(begin)
    stop = body.index(end)
    if stop < start:
        raise ConflictError(f"The {name} section markers are in the wrong order.")
    return body[start:stop].strip("\n")
