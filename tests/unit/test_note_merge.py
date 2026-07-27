"""The merge rules of AGENTS.md section 12.3, which protect human text."""

from __future__ import annotations

from pathlib import Path

import pytest
from lab_obsidian.merge import (
    HUMAN_BEGIN,
    MANAGED_BEGIN,
    ConflictError,
    WriteOutcome,
    parse_note,
    render_note,
    write_note,
)

FRONTMATTER = {"type": "run", "run_id": "RUN-000001", "managed_by": "lab-platform"}
MANAGED = "## Execution summary\n\n- Status: completed"
HUMAN = "## Interpretation\n\n## Limitations\n"


def note(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, managed: str = MANAGED, **changes: object):  # noqa: ANN201
    return write_note(
        path,
        frontmatter={**FRONTMATTER, **changes},
        managed=managed,
        title="RUN-000001",
        human_placeholder=HUMAN,
    )


def test_a_new_note_has_both_sections(tmp_path: Path) -> None:
    result = write(tmp_path / "Runs" / "RUN-000001.md")

    assert result.outcome is WriteOutcome.CREATED
    body = note(result.path)
    assert body.startswith("---\ntype: run")
    assert MANAGED_BEGIN in body and HUMAN_BEGIN in body
    assert "## Execution summary" in body
    assert "## Interpretation" in body


def test_regeneration_preserves_human_text(tmp_path: Path) -> None:
    path = tmp_path / "RUN-000001.md"
    write(path)
    edited = note(path).replace(
        "## Interpretation\n", "## Interpretation\n\nThe seeds look wrong.\n"
    )
    path.write_text(edited)

    result = write(path, managed="## Execution summary\n\n- Status: failed")

    assert result.outcome is WriteOutcome.UPDATED
    body = note(path)
    assert "The seeds look wrong." in body
    assert "- Status: failed" in body
    assert "- Status: completed" not in body


def test_frontmatter_keys_the_platform_does_not_own_survive(tmp_path: Path) -> None:
    path = tmp_path / "RUN-000001.md"
    write(path)
    path.write_text(note(path).replace("type: run", "type: run\nreviewed_by: pi.rossi"))

    write(path, managed="## Execution summary\n\n- Status: failed")

    parsed = parse_note(note(path))
    assert parsed.frontmatter["reviewed_by"] == "pi.rossi"
    assert parsed.frontmatter["managed_by"] == "lab-platform"


def test_an_unchanged_note_is_not_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "RUN-000001.md"
    write(path)
    before = path.stat().st_mtime_ns

    assert write(path).outcome is WriteOutcome.UNCHANGED
    assert path.stat().st_mtime_ns == before


@pytest.mark.parametrize(
    ("existing", "reason"),
    [
        ("# Just my notes\n\nNo frontmatter here.\n", "no frontmatter"),
        ("---\ntype: run\n\n# Unclosed frontmatter\n", "not closed"),
        ("---\ntype: run\n---\n\nNo markers at all.\n", "exactly one managed"),
        (
            "---\ntype: run\n---\n\n"
            f"{MANAGED_BEGIN}\na\n<!-- END LAB MANAGED -->\n"
            f"{MANAGED_BEGIN}\nb\n<!-- END LAB MANAGED -->\n"
            f"{HUMAN_BEGIN}\n\n<!-- END HUMAN NOTES -->\n",
            "exactly one managed",
        ),
        ("---\n- not\n- a mapping\n---\n\nbody\n", "not a mapping"),
        ("---\ntype: [unclosed\n---\n\nbody\n", "not readable"),
    ],
)
def test_an_unparseable_note_is_never_overwritten(
    tmp_path: Path, existing: str, reason: str
) -> None:
    path = tmp_path / "RUN-000001.md"
    path.write_text(existing)

    result = write(path)

    assert result.outcome is WriteOutcome.CONFLICT
    assert note(path) == existing, "the existing note must be left exactly as it was"
    assert result.sidecar is not None
    assert result.sidecar.name == "RUN-000001.lab-conflict.md"
    assert "## Execution summary" in note(result.sidecar)
    assert result.reason is not None and reason in result.reason


def test_a_note_written_by_the_platform_round_trips() -> None:
    text = render_note(FRONTMATTER, MANAGED, HUMAN, "RUN-000001")
    parsed = parse_note(text)
    assert parsed.frontmatter == FRONTMATTER
    assert parsed.managed == MANAGED
    assert parsed.human == HUMAN.strip("\n")


def test_parsing_refuses_a_note_without_markers() -> None:
    with pytest.raises(ConflictError):
        parse_note("---\ntype: run\n---\n\nnothing else\n")
