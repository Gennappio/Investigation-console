"""Where the API resolves its infrastructure.

The same stores the CLI builds, from the same ``LAB_HOME``: the API is another
caller of the platform, not a second implementation of it.
"""

from __future__ import annotations

from lab_artifacts.filesystem_store import FilesystemArtifactStore

from lab_cli.runtime import (
    artifacts_root,
    default_registry,
    lab_home,
    report_template_dir,
    scratch_root,
)
from lab_registry.component_store import FileComponentStore
from lab_registry.local_store import LocalRegistry
from lab_registry.run_store import FileRunStore


def registry() -> LocalRegistry:
    return default_registry()


def run_store() -> FileRunStore:
    return FileRunStore(lab_home(), registry())


def artifact_store() -> FilesystemArtifactStore:
    return FilesystemArtifactStore(artifacts_root(), registry())


def component_store() -> FileComponentStore:
    return FileComponentStore(lab_home(), registry())


__all__ = [
    "artifact_store",
    "component_store",
    "registry",
    "report_template_dir",
    "run_store",
    "scratch_root",
]
