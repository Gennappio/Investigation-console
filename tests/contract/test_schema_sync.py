"""The committed schemas must match what the models generate (ADR 0004)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lab_domain.schema_export import EXPORTS, render

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


@pytest.mark.parametrize(("filename", "model"), EXPORTS, ids=[e[0] for e in EXPORTS])
def test_committed_schema_matches_the_models(filename: str, model: type) -> None:
    committed = (SCHEMAS / filename).read_text(encoding="utf-8")
    assert committed == render(filename, model), (
        f"{filename} is stale. Regenerate with: "
        "uv run python -m lab_domain.schema_export schemas/"
    )


def test_export_is_deterministic() -> None:
    filename, model = EXPORTS[0]
    assert render(filename, model) == render(filename, model)


def test_identifier_patterns_reach_the_schema() -> None:
    schema = json.loads((SCHEMAS / "lab.schema.json").read_text())
    project = schema["$defs"]["RepositorySpec"]["properties"]["project"]
    assert project["pattern"] == "^PRJ-[0-9]{6}$"
    assert schema["$defs"]["RepositorySpec"]["additionalProperties"] is False
