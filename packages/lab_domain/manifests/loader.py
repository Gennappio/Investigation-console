"""Structural loading of manifests: YAML text to typed model or findings."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails

from lab_domain.validation.findings import Finding, FindingCode, error


def render_path(location: tuple[int | str, ...]) -> str:
    """Render a Pydantic error location as a dotted path with list indices."""
    rendered = ""
    for part in location:
        if isinstance(part, int):
            rendered += f"[{part}]"
        else:
            rendered += f".{part}" if rendered else str(part)
    return rendered


def _code_for(pydantic_error: ErrorDetails, path: str) -> FindingCode:
    kind = str(pydantic_error["type"])
    head = str(pydantic_error["loc"][0]) if pydantic_error["loc"] else ""
    if kind == "literal_error" and head == "apiVersion":
        return FindingCode.UNKNOWN_SCHEMA_VERSION
    if kind == "literal_error" and head == "kind":
        return FindingCode.UNKNOWN_KIND
    if kind == "extra_forbidden":
        return FindingCode.UNKNOWN_FIELD
    if "resources" in path:
        return FindingCode.UNBOUNDED_RESOURCES
    if kind == "missing":
        return FindingCode.MISSING_REQUIRED_FIELD
    if kind == "value_error" and "identifier" in str(pydantic_error.get("msg", "")):
        return FindingCode.MALFORMED_ID
    return FindingCode.TYPE_ERROR


def load_manifest[ManifestT: BaseModel](
    model: type[ManifestT], path: Path, file_label: str
) -> tuple[ManifestT | None, list[Finding]]:
    """Parse ``path`` into ``model``.

    Returns the parsed manifest, or ``None`` plus the findings explaining why
    it could not be parsed.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, [
            error(
                FindingCode.MANIFEST_NOT_FOUND,
                "",
                f"Cannot read manifest: {exc.strerror}.",
                file_label,
            )
        ]

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, [
            error(
                FindingCode.YAML_PARSE_ERROR,
                "",
                f"Invalid YAML: {str(exc).strip()}",
                file_label,
            )
        ]

    if not isinstance(document, dict):
        return None, [
            error(
                FindingCode.TYPE_ERROR,
                "",
                "Manifest must be a YAML mapping.",
                file_label,
            )
        ]

    try:
        return model.model_validate(document), []
    except ValidationError as exc:
        findings = []
        for detail in exc.errors():
            path_text = render_path(detail["loc"])
            findings.append(
                error(
                    _code_for(detail, path_text),
                    path_text,
                    f"{detail['msg']}.",
                    file_label,
                )
            )
        return None, findings
