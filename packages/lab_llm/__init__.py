"""Optional language-model adapters. Nothing deterministic depends on these."""

from lab_llm.config import LanguageModelSettings, load_settings
from lab_llm.openrouter import OpenRouterModel

__all__ = ["LanguageModelSettings", "OpenRouterModel", "load_settings"]
