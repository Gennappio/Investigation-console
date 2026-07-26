"""Language model port: the platform's only opening for optional intelligence.

Nothing in the deterministic path may depend on this (AGENTS.md sections 2.1
and 17.4). A model can draft prose about what a run recorded; it can never
produce a fact, and every command keeps working with no model configured.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"


class LanguageModel_(BaseModel):
    model_config = ConfigDict(frozen=True)


class Message(LanguageModel_):
    role: Role
    content: str


class Completion(LanguageModel_):
    """What a model returned, with enough provenance to attribute it."""

    text: str
    provider: str
    model: str
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LanguageModel(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    def available(self) -> bool:
        """Whether a model is configured. Unconfigured is a normal state."""
        ...

    def complete(self, messages: Sequence[Message]) -> Completion: ...
