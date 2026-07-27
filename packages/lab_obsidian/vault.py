"""Where the vault is, and where each kind of note lives inside it.

Projection is off until a laboratory says where its vault is: the platform
never writes into someone's notes by guessing a path.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from lab_domain.errors import StateStoreError
from lab_domain.ids import ExperimentId, ProjectId, RunId

SETTINGS_FILENAME = "obsidian.json"
VAULT_VARIABLE = "LAB_OBSIDIAN_VAULT"

PROJECTS_DIRECTORY = "Projects"
EXPERIMENTS_DIRECTORY = "Experiments"
RUNS_DIRECTORY = "Runs"


class VaultSettings(BaseModel):
    """Where notes go. ``vault`` unset means projection is disabled."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vault: Path | None = None
    projects_directory: str = PROJECTS_DIRECTORY
    experiments_directory: str = EXPERIMENTS_DIRECTORY
    runs_directory: str = RUNS_DIRECTORY

    @property
    def enabled(self) -> bool:
        return self.vault is not None

    def project_note(self, project_id: ProjectId, override: str | None = None) -> Path:
        """A repository may name its own project note in ``lab.yaml``."""
        root = self._root()
        if override:
            return root / override
        return root / self.projects_directory / f"{project_id}.md"

    def experiment_note(self, experiment_id: ExperimentId) -> Path:
        return self._root() / self.experiments_directory / f"{experiment_id}.md"

    def run_note(self, run_id: RunId) -> Path:
        return self._root() / self.runs_directory / f"{run_id}.md"

    def _root(self) -> Path:
        if self.vault is None:
            raise StateStoreError(
                "No Obsidian vault is configured. Set LAB_OBSIDIAN_VAULT, or "
                f"`vault` in $LAB_HOME/{SETTINGS_FILENAME}."
            )
        return self.vault.expanduser()


def load_vault_settings(home: Path) -> VaultSettings:
    """Read ``$LAB_HOME/obsidian.json``; the environment wins over the file."""
    path = home / SETTINGS_FILENAME
    settings = VaultSettings()
    if path.is_file():
        try:
            settings = VaultSettings.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, ValidationError) as exc:
            raise StateStoreError(
                f"Vault settings {path} are unusable: {exc}."
            ) from exc

    if vault := os.environ.get(VAULT_VARIABLE, "").strip():
        settings = settings.model_copy(update={"vault": Path(vault)})
    return settings
