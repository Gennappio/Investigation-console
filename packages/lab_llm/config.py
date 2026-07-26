"""Where the optional language model is configured.

The key never lives in the repository: it comes from the environment, like any
other credential (AGENTS.md section 15.1). Everything else may sit in
``$LAB_HOME/llm.json`` so a laboratory settles on one model.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from lab_domain.errors import StateStoreError

SETTINGS_FILENAME = "llm.json"
API_KEY_VARIABLE = "OPENROUTER_API_KEY"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class LanguageModelSettings(BaseModel):
    """How to reach the model. Deliberately without a default model name.

    Which model to use is a laboratory's decision with cost and data-handling
    consequences, so the platform asks rather than picking one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = "openrouter"
    model: str | None = None
    base_url: str = DEFAULT_BASE_URL
    max_tokens: int = Field(default=800, ge=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    timeout_seconds: int = Field(default=60, ge=1)

    @property
    def configured(self) -> bool:
        return bool(self.model) and bool(api_key())


def api_key() -> str | None:
    """The credential, from the environment only."""
    key = os.environ.get(API_KEY_VARIABLE, "").strip()
    return key or None


def load_settings(home: Path) -> LanguageModelSettings:
    """Read ``$LAB_HOME/llm.json``; environment variables win over the file."""
    path = home / SETTINGS_FILENAME
    settings = LanguageModelSettings()
    if path.is_file():
        try:
            settings = LanguageModelSettings.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, ValidationError) as exc:
            raise StateStoreError(
                f"Model settings {path} are unusable: {exc}."
            ) from exc

    overrides: dict[str, object] = {}
    if model := os.environ.get("LAB_LLM_MODEL", "").strip():
        overrides["model"] = model
    if base_url := os.environ.get("LAB_LLM_BASE_URL", "").strip():
        overrides["base_url"] = base_url
    return settings.model_copy(update=overrides) if overrides else settings
