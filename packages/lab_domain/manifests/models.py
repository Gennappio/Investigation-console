"""Typed models for ``lab.yaml`` and experiment manifests (AGENTS.md section 7).

Models are frozen because a manifest is snapshotted into immutable run records
from Milestone 2 onwards, and forbid unknown fields so typos are caught rather
than ignored.

Field strictness follows one rule: a field is required when its absence is
structural (names, identifiers, schema version), and optional when its absence
is a named validation rule in AGENTS.md section 7.3 (dataset version, outputs,
resources, seeds, references). The rule engine can then report the documented
finding code and path instead of a generic type error.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lab_domain.ids import ComponentId, DatasetId, ExperimentId, ProjectId
from lab_domain.manifests.quantities import parse_memory_to_mb, validate_time_limit

API_VERSION = "lab/v1"

# The four test categories of AGENTS.md section 10, as manifest keys.
SuiteName = Literal[
    "software_tests",
    "integration_tests",
    "reproducibility_tests",
    "scientific_validation",
]


class ManifestModel(BaseModel):
    """Common configuration for every manifest node."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )


class RuntimeSpec(ManifestModel):
    type: str
    version: str


class ContainerSpec(ManifestModel):
    dockerfile: str
    context: str = "."


class OutputsSpec(ManifestModel):
    directory: str = Field(min_length=1)


class ReportingSpec(ManifestModel):
    template: str = "default"


class ObsidianSpec(ManifestModel):
    project_note: str


class RepositoryMetadata(ManifestModel):
    name: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$")]
    description: str | None = None
    owners: tuple[str, ...] = ()


class RepositorySpec(ManifestModel):
    project: ProjectId
    runtime: RuntimeSpec
    container: ContainerSpec | None = None
    commands: dict[str, tuple[str, ...]] = {}
    outputs: OutputsSpec | None = None
    reporting: ReportingSpec | None = None
    obsidian: ObsidianSpec | None = None


class RepositoryManifest(ManifestModel):
    """Root-level ``lab.yaml`` of a managed repository."""

    api_version: Literal["lab/v1"] = Field(alias="apiVersion")
    kind: Literal["Repository"]
    metadata: RepositoryMetadata
    spec: RepositorySpec


class ComponentMetadata(ManifestModel):
    name: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$")]
    description: str | None = None
    maintainer: str | None = None
    keywords: tuple[str, ...] = ()


class PortSpec(ManifestModel):
    """One input or output of a component."""

    type: str
    description: str | None = None


class ComponentSpec(ManifestModel):
    # Semantic versioning: a registry entry is addressed by name and version.
    version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    command: Annotated[tuple[str, ...], Field(min_length=1)]
    inputs: dict[str, PortSpec] = {}
    outputs: dict[str, PortSpec] = {}
    container: ContainerSpec | None = None
    # Which command profile proves each test category (AGENTS.md section 10).
    tests: dict[SuiteName, str] = {}
    references: tuple[str, ...] = ()


class ComponentManifest(ManifestModel):
    """A reusable executable asset, declared in ``components/*.yaml``."""

    api_version: Literal["lab/v1"] = Field(alias="apiVersion")
    kind: Literal["Component"]
    metadata: ComponentMetadata
    spec: ComponentSpec


class ExperimentMetadata(ManifestModel):
    id: ExperimentId
    title: str
    project: ProjectId
    owner: str


class ScientificSpec(ManifestModel):
    question: str
    hypothesis: str
    references: tuple[str, ...] = ()


class DatasetRef(ManifestModel):
    id: DatasetId
    version: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_bare_identifier(cls, value: Any) -> Any:
        """Allow ``DATA-000001`` as shorthand so the missing version is
        reported as MISSING_DATASET_VERSION rather than a type error."""
        if isinstance(value, str):
            return {"id": value, "version": None}
        return value


class SeedSpec(ManifestModel):
    strategy: Literal["explicit", "derived"]
    values: tuple[int, ...] = ()

    @model_validator(mode="after")
    def _explicit_seeds_are_listed(self) -> SeedSpec:
        if self.strategy == "explicit" and not self.values:
            raise ValueError("seed strategy 'explicit' requires at least one value")
        return self


class ResourceSpec(ManifestModel):
    cpus: Annotated[int, Field(ge=1)]
    memory: str
    time_limit: str
    gpus: Annotated[int, Field(ge=0)] = 0

    @field_validator("memory")
    @classmethod
    def _memory_is_parseable(cls, value: str) -> str:
        parse_memory_to_mb(value)
        return value

    @field_validator("time_limit")
    @classmethod
    def _time_limit_is_parseable(cls, value: str) -> str:
        return validate_time_limit(value)

    @property
    def memory_mb(self) -> int:
        return parse_memory_to_mb(self.memory)


class ExecutionSpec(ManifestModel):
    component: ComponentId | None = None
    dataset_refs: tuple[DatasetRef, ...] = ()
    parameters: dict[str, Any] = {}
    seeds: SeedSpec | None = None
    resources: ResourceSpec | None = None


class ValidationRequirements(ManifestModel):
    software_tests: Literal["required", "optional"] = "required"
    integration_tests: Literal["required", "optional"] = "required"
    reproducibility_tests: Literal["required", "optional"] = "required"
    scientific_validation: Literal["required", "optional"] = "optional"


class ExperimentManifest(ManifestModel):
    """Version-controlled specification of one experiment."""

    api_version: Literal["lab/v1"] = Field(alias="apiVersion")
    kind: Literal["Experiment"]
    metadata: ExperimentMetadata
    scientific: ScientificSpec
    execution: ExecutionSpec
    validation: ValidationRequirements | None = None
