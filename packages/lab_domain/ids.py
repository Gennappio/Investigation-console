"""Typed identifiers for domain objects (AGENTS.md section 6).

Identifiers are strings at the boundary but distinct types inside the domain,
so a type checker rejects passing an ``ExperimentId`` where a ``ProjectId`` is
expected. Canonical format is a prefix and six zero-padded digits, e.g.
``PRJ-000001`` (see ADR 0002).
"""

from __future__ import annotations

import re
from typing import Any, ClassVar, Self

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema

DIGITS = 6


class TypedId(str):
    """Base class for prefixed identifiers. Subclasses set ``prefix``."""

    prefix: ClassVar[str]
    pattern: ClassVar[re.Pattern[str]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.pattern = re.compile(rf"^{cls.prefix}-[0-9]{{{DIGITS}}}$")

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or not cls.pattern.match(value):
            raise ValueError(
                f"malformed {cls.prefix} identifier {value!r}: "
                f"expected {cls.prefix}-{'0' * DIGITS}"
            )
        return super().__new__(cls, value)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self)!r})"

    @classmethod
    def from_int(cls, number: int) -> Self:
        """Build an identifier from a counter value."""
        if number < 1 or number >= 10**DIGITS:
            raise ValueError(
                f"{cls.prefix} counter {number} outside 1..{10**DIGITS - 1}"
            )
        return cls(f"{cls.prefix}-{number:0{DIGITS}d}")

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls, core_schema.str_schema()
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {"type": "string", "pattern": cls.pattern.pattern}


class ProjectId(TypedId):
    prefix = "PRJ"


class ExperimentId(TypedId):
    prefix = "EXP"


class RunId(TypedId):
    prefix = "RUN"


class ComponentId(TypedId):
    prefix = "CMP"


class WorkflowId(TypedId):
    prefix = "WF"


class DatasetId(TypedId):
    prefix = "DATA"


class ArtifactId(TypedId):
    prefix = "ART"


class ReferenceId(TypedId):
    prefix = "REF"


class DecisionId(TypedId):
    prefix = "DEC"
