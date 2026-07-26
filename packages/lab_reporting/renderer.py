"""HTML rendering of a report document (AGENTS.md section 11).

The template only lays out values that the report document already contains:
no field is computed, summarised or worded here.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from lab_domain.errors import StateStoreError
from lab_domain.services.report_service import ReportDocument

TEMPLATE_NAME = "report.html.j2"


def render_html(template_dir: Path, document: ReportDocument) -> str:
    template_path = template_dir / TEMPLATE_NAME
    if not template_path.is_file():
        raise StateStoreError(f"Report template not found at {template_path}.")
    environment = Environment(
        loader=FileSystemLoader(template_dir),
        undefined=StrictUndefined,
        autoescape=select_autoescape(["html"]),
        keep_trailing_newline=True,
    )
    return environment.get_template(TEMPLATE_NAME).render(
        report=document,
        run=document.run,
    )
