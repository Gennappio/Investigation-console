"""Prompt rendering.

Prompts are content, not code: they live in ``templates/prompts`` so a
laboratory can read and adjust what is asked of a model, and so the exact text
sent can be stored with the run.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from lab_domain.errors import StateStoreError
from lab_domain.services.report_service import ReportDocument

RUN_EXPLANATION_TEMPLATE = "run-explanation.md.j2"


def render_run_explanation(template_dir: Path, document: ReportDocument) -> str:
    template_path = template_dir / RUN_EXPLANATION_TEMPLATE
    if not template_path.is_file():
        raise StateStoreError(f"Prompt template not found at {template_path}.")
    environment = Environment(
        loader=FileSystemLoader(template_dir),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    return environment.get_template(RUN_EXPLANATION_TEMPLATE).render(report=document)
