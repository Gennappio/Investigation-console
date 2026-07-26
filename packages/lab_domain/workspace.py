"""Discovery of the managed repository a command is operating on."""

from __future__ import annotations

from pathlib import Path

from lab_domain.errors import WorkspaceNotFoundError

MANIFEST_NAME = "lab.yaml"
EXPERIMENTS_DIRECTORY = "experiments"
COMPONENTS_DIRECTORY = "components"


def find_workspace_root(start: Path) -> Path:
    """Return the closest ancestor of ``start`` containing ``lab.yaml``."""
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / MANIFEST_NAME).is_file():
            return candidate
    raise WorkspaceNotFoundError(
        f"No {MANIFEST_NAME} found in {start} or any parent directory. "
        "Run this command inside a managed repository, or create one with "
        "`lab init <name>`."
    )


def experiment_manifest_paths(root: Path) -> list[Path]:
    """Experiment manifests of a workspace, in a stable order."""
    return _manifest_paths(root / EXPERIMENTS_DIRECTORY)


def component_manifest_paths(root: Path) -> list[Path]:
    """Component manifests of a workspace, in a stable order."""
    return _manifest_paths(root / COMPONENTS_DIRECTORY)


def _manifest_paths(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix in {".yaml", ".yml"}
    )
