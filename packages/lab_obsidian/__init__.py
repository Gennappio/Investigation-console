"""Projection of laboratory knowledge into an Obsidian vault.

The vault is a navigable view, never the source of truth (AGENTS.md 2.5, 12).
"""

from lab_obsidian.merge import NoteWrite, WriteOutcome, write_note
from lab_obsidian.vault import VaultSettings, load_vault_settings

__all__ = [
    "NoteWrite",
    "VaultSettings",
    "WriteOutcome",
    "load_vault_settings",
    "write_note",
]
