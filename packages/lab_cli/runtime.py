"""Composition root: where the CLI resolves its infrastructure."""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

from lab_artifacts.filesystem_store import FilesystemArtifactStore
from lab_containers.docker_engine import DockerEngine
from lab_execution.local_backend import LocalExecutionBackend

from lab_domain.errors import StateStoreError
from lab_registry.audit import AuditLog
from lab_registry.local_store import LocalRegistry
from lab_registry.run_store import FileRunStore

DEFAULT_LAB_HOME = "~/.lab"
INSTALLED_TEMPLATES = Path("share") / "lab-platform" / "templates"
PROJECT_TEMPLATE_MARKER = "lab.yaml.j2"
ARTIFACTS_DIRECTORY = "artifacts"
WORK_DIRECTORY = "work"


def lab_home() -> Path:
    """Directory holding platform state, overridable with ``LAB_HOME``."""
    return Path(os.environ.get("LAB_HOME", DEFAULT_LAB_HOME)).expanduser()


def artifacts_root() -> Path:
    """Permanent artifact storage; scratch lives elsewhere (section 8.3)."""
    return lab_home() / ARTIFACTS_DIRECTORY


def scratch_root() -> Path:
    return lab_home() / WORK_DIRECTORY


def actor() -> str:
    """Who is running the command, recorded on runs and in the audit log."""
    return getpass.getuser()


def default_registry() -> LocalRegistry:
    return LocalRegistry(lab_home())


def default_run_store() -> FileRunStore:
    return FileRunStore(lab_home(), default_registry())


def default_artifact_store() -> FilesystemArtifactStore:
    return FilesystemArtifactStore(artifacts_root(), default_registry())


def default_audit_log() -> AuditLog:
    return AuditLog(lab_home())


def default_container_engine() -> DockerEngine:
    return DockerEngine()


def default_execution_backend() -> LocalExecutionBackend:
    return LocalExecutionBackend(engine=default_container_engine())


def templates_root() -> Path:
    """Directory holding the platform templates.

    Looked up in the installed environment first, then in the source tree, so
    the CLI works from a wheel and from a checkout.
    """
    override = os.environ.get("LAB_TEMPLATES_DIR")
    if override:
        # An explicit override is never silently ignored.
        directory = Path(override).expanduser()
        if not (directory / "project" / PROJECT_TEMPLATE_MARKER).is_file():
            raise StateStoreError(
                f"LAB_TEMPLATES_DIR points at {directory}, which holds no "
                f"project/{PROJECT_TEMPLATE_MARKER}."
            )
        return directory

    candidates = [
        Path(sys.prefix) / INSTALLED_TEMPLATES,
        Path(__file__).resolve().parents[2] / "templates",
    ]
    for candidate in candidates:
        if (candidate / "project" / PROJECT_TEMPLATE_MARKER).is_file():
            return candidate

    searched = ", ".join(str(c) for c in candidates)
    raise StateStoreError(
        f"Platform templates not found. Searched: {searched}. "
        "Set LAB_TEMPLATES_DIR to the templates directory."
    )


def project_template_dir() -> Path:
    return templates_root() / "project"


def report_template_dir() -> Path:
    return templates_root() / "report"
