"""Validation findings and the report shape consumed by `lab validate --json`.

The JSON payload follows AGENTS.md section 13.3, with one additive key: each
finding carries the manifest ``file`` it came from, because a workspace holds
``lab.yaml`` plus any number of experiment manifests.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class FindingCode(StrEnum):
    """Stable machine-readable codes. Values are part of the CLI contract."""

    # Errors: structural
    MANIFEST_NOT_FOUND = "MANIFEST_NOT_FOUND"
    YAML_PARSE_ERROR = "YAML_PARSE_ERROR"
    UNKNOWN_SCHEMA_VERSION = "UNKNOWN_SCHEMA_VERSION"
    UNKNOWN_KIND = "UNKNOWN_KIND"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    TYPE_ERROR = "TYPE_ERROR"
    MALFORMED_ID = "MALFORMED_ID"
    # Errors: semantic (AGENTS.md section 7.3)
    MISSING_DATASET_VERSION = "MISSING_DATASET_VERSION"
    UNBOUNDED_RESOURCES = "UNBOUNDED_RESOURCES"
    MISSING_OUTPUT_LOCATION = "MISSING_OUTPUT_LOCATION"
    SECRET_DETECTED = "SECRET_DETECTED"
    PROJECT_MISMATCH = "PROJECT_MISMATCH"
    UNKNOWN_TEST_PROFILE = "UNKNOWN_TEST_PROFILE"
    # Warnings
    MISSING_REFERENCES = "MISSING_REFERENCES"
    MISSING_SCIENTIFIC_VALIDATION = "MISSING_SCIENTIFIC_VALIDATION"
    MISSING_SEED_POLICY = "MISSING_SEED_POLICY"
    MISSING_MAINTAINER = "MISSING_MAINTAINER"


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    severity: Severity
    code: FindingCode
    path: str
    message: str
    file: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """Serialize for the CLI contract; severity is implied by its list."""
        return {
            "code": self.code.value,
            "path": self.path,
            "message": self.message,
            "file": self.file,
        }


class ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    findings: tuple[Finding, ...] = ()

    @classmethod
    def from_findings(cls, findings: list[Finding]) -> ValidationReport:
        ordered = sorted(findings, key=lambda f: (f.file or "", f.path, f.code.value))
        return cls(findings=tuple(ordered))

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.WARNING)

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_payload(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [f.to_payload() for f in self.errors],
            "warnings": [f.to_payload() for f in self.warnings],
        }


def error(
    code: FindingCode, path: str, message: str, file: str | None = None
) -> Finding:
    return Finding(
        severity=Severity.ERROR, code=code, path=path, message=message, file=file
    )


def warning(
    code: FindingCode, path: str, message: str, file: str | None = None
) -> Finding:
    return Finding(
        severity=Severity.WARNING, code=code, path=path, message=message, file=file
    )
