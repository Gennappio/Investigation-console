"""Rendering of note bodies from records.

Only the managed part of a note is rendered here. Every value comes from a
record the platform holds; nothing is summarised, inferred or worded on the
platform's behalf, and no artifact contents are copied into the vault
(AGENTS.md section 2.5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from lab_domain.errors import StateStoreError

PROJECT_TEMPLATE = "project.md.j2"
EXPERIMENT_TEMPLATE = "experiment.md.j2"
RUN_TEMPLATE = "run.md.j2"


def render(template_dir: Path, template: str, context: dict[str, Any]) -> str:
    path = template_dir / template
    if not path.is_file():
        raise StateStoreError(f"Obsidian template not found at {path}.")
    environment = Environment(
        loader=FileSystemLoader(template_dir),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    return environment.get_template(template).render(**context)
