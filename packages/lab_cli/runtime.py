"""Composition root: where the CLI resolves its infrastructure."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from lab_domain.errors import StateStoreError
from lab_registry.local_store import LocalRegistry

DEFAULT_LAB_HOME = "~/.lab"
TEMPLATE_MARKER = "lab.yaml.j2"
INSTALLED_TEMPLATES = Path("share") / "lab-platform" / "templates"


def lab_home() -> Path:
    """Directory holding platform state, overridable with ``LAB_HOME``."""
    return Path(os.environ.get("LAB_HOME", DEFAULT_LAB_HOME)).expanduser()


def default_registry() -> LocalRegistry:
    return LocalRegistry(lab_home())


def template_root() -> Path:
    """Directory of the project template.

    Looked up in the installed environment first, then in the source tree, so
    the CLI works from a wheel and from a checkout.
    """
    override = os.environ.get("LAB_TEMPLATES_DIR")
    if override:
        # An explicit override is never silently ignored.
        directory = Path(override).expanduser()
        if not (directory / TEMPLATE_MARKER).is_file():
            raise StateStoreError(
                f"LAB_TEMPLATES_DIR points at {directory}, which holds no "
                f"{TEMPLATE_MARKER}."
            )
        return directory

    candidates = [
        Path(sys.prefix) / INSTALLED_TEMPLATES / "project",
        Path(__file__).resolve().parents[2] / "templates" / "project",
    ]
    for candidate in candidates:
        if (candidate / TEMPLATE_MARKER).is_file():
            return candidate

    searched = ", ".join(str(c) for c in candidates)
    raise StateStoreError(
        f"Project template not found. Searched: {searched}. "
        "Set LAB_TEMPLATES_DIR to the template directory."
    )
