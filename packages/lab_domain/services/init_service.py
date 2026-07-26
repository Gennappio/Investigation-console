"""Project scaffolding (`lab init`)."""

from __future__ import annotations

import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, ConfigDict

from lab_domain.errors import InvalidNameError, StateStoreError, TargetExistsError
from lab_domain.ids import ExperimentId, ProjectId
from lab_domain.registry import ProjectRecord, ProjectRegistry

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TEMPLATE_SUFFIX = ".j2"
# Template paths carry placeholders because a filename cannot be templated by
# Jinja2, and files whose names would otherwise take effect in this repository
# (a .gitignore inside templates/) are stored under a neutral name.
PATH_PLACEHOLDERS = {"__pkg__": "package", "__exp__": "experiment_id"}
RENAMED_FILES = {"gitignore": ".gitignore"}


class InitResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: ProjectId
    experiment_id: ExperimentId
    root: str
    files: tuple[str, ...]


def validate_project_name(name: str) -> str:
    if NAME_PATTERN.match(name) is None:
        raise InvalidNameError(
            f"Invalid project name {name!r}: use lowercase letters, digits and "
            "hyphens, starting with a letter or digit."
        )
    return name


def init_project(
    name: str,
    parent: Path,
    registry: ProjectRegistry,
    template_dir: Path,
    owner: str,
) -> InitResult:
    """Create a managed repository named ``name`` under ``parent``."""
    validate_project_name(name)
    if not (template_dir / "lab.yaml.j2").is_file():
        raise StateStoreError(
            f"Project template is missing or incomplete at {template_dir}. "
            "Reinstall the platform or set LAB_TEMPLATES_DIR."
        )

    root = parent / name
    if root.exists():
        raise TargetExistsError(f"{root} already exists.")

    project_id = registry.allocate_project_id()
    experiment_id = registry.allocate_experiment_id()
    context = {
        "name": name,
        "package": name.replace("-", "_"),
        "project_id": str(project_id),
        "experiment_id": str(experiment_id),
        "owner": owner,
        "created": datetime.now(UTC).date().isoformat(),
    }

    try:
        files = _render_tree(template_dir, root, context)
        (root / "results").mkdir(exist_ok=True)
    except OSError as exc:
        shutil.rmtree(root, ignore_errors=True)
        message = f"Cannot create project at {root}: {exc.strerror}."
        raise StateStoreError(message) from exc

    registry.register_project(
        ProjectRecord(
            id=project_id,
            name=name,
            path=str(root),
            created_at=datetime.now(UTC),
        )
    )
    return InitResult(
        project_id=project_id,
        experiment_id=experiment_id,
        root=str(root),
        files=tuple(files),
    )


def _render_tree(template_dir: Path, root: Path, context: dict[str, str]) -> list[str]:
    """Copy the template tree to ``root``, rendering ``.j2`` files."""
    environment = Environment(undefined=StrictUndefined, keep_trailing_newline=True)
    created: list[str] = []

    for source in sorted(template_dir.rglob("*")):
        if source.is_dir():
            continue
        target = root / _target_path(source.relative_to(template_dir), context)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == TEMPLATE_SUFFIX:
            rendered = environment.from_string(
                source.read_text(encoding="utf-8")
            ).render(context)
            target.write_text(rendered, encoding="utf-8")
        else:
            shutil.copyfile(source, target)
        created.append(target.relative_to(root).as_posix())

    return created


def _target_path(relative: Path, context: dict[str, str]) -> Path:
    parts = []
    for part in relative.parts:
        for placeholder, key in PATH_PLACEHOLDERS.items():
            part = part.replace(placeholder, context[key])
        parts.append(part)
    filename = parts[-1]
    if filename.endswith(TEMPLATE_SUFFIX):
        filename = filename[: -len(TEMPLATE_SUFFIX)]
    parts[-1] = RENAMED_FILES.get(filename, filename)
    return Path(*parts)
