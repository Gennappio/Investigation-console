"""Semantic validation rules over parsed manifests (AGENTS.md section 7.3).

Structural problems (unknown schema version, missing required fields, malformed
identifiers) are reported by the loader. These rules cover what only becomes
visible once a manifest parses.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

from lab_domain.manifests.models import (
    ComponentManifest,
    ExperimentManifest,
    RepositoryManifest,
)
from lab_domain.validation.findings import Finding, FindingCode, error, warning

LAB_MANIFEST = "lab.yaml"

_SECRET_VALUE_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
)
_SECRET_KEY_PATTERN = re.compile(
    r"^\s*[\"']?(?P<key>[\w.-]*(?:password|passwd|secret|api_key|apikey|token"
    r"|private_key|access_key))[\"']?\s*:\s*(?P<value>\S.*)$",
    re.IGNORECASE,
)
_PLACEHOLDER_PATTERN = re.compile(r"^[\"']?\$\{[^}]+\}[\"']?$|^[\"']?\$\w+[\"']?$")


@dataclass(frozen=True)
class ManifestDoc:
    """One parsed experiment manifest and the file it came from."""

    file: str
    manifest: ExperimentManifest


@dataclass(frozen=True)
class ComponentDoc:
    """One parsed component manifest and the file it came from."""

    file: str
    manifest: ComponentManifest


@dataclass(frozen=True)
class WorkspaceDocs:
    """Everything the rules need about a workspace."""

    repository: RepositoryManifest | None = None
    experiments: tuple[ManifestDoc, ...] = ()
    components: tuple[ComponentDoc, ...] = ()
    raw_texts: dict[str, str] = field(default_factory=dict)


Rule = Callable[[WorkspaceDocs], Iterable[Finding]]


def rule_output_location(docs: WorkspaceDocs) -> Iterator[Finding]:
    """Every repository must declare where run outputs are written."""
    if docs.repository is not None and docs.repository.spec.outputs is None:
        yield error(
            FindingCode.MISSING_OUTPUT_LOCATION,
            "spec.outputs",
            "Repository must declare an output directory.",
            LAB_MANIFEST,
        )


def rule_maintainer(docs: WorkspaceDocs) -> Iterator[Finding]:
    if docs.repository is not None and not docs.repository.metadata.owners:
        yield warning(
            FindingCode.MISSING_MAINTAINER,
            "metadata.owners",
            "Repository has no maintainer.",
            LAB_MANIFEST,
        )


def rule_dataset_versions(docs: WorkspaceDocs) -> Iterator[Finding]:
    """Dataset references are only reproducible with an explicit version."""
    for doc in docs.experiments:
        for index, ref in enumerate(doc.manifest.execution.dataset_refs):
            if ref.version is None:
                yield error(
                    FindingCode.MISSING_DATASET_VERSION,
                    f"execution.dataset_refs[{index}]",
                    f"Dataset {ref.id} requires an explicit version.",
                    doc.file,
                )


def rule_bounded_resources(docs: WorkspaceDocs) -> Iterator[Finding]:
    for doc in docs.experiments:
        if doc.manifest.execution.resources is None:
            yield error(
                FindingCode.UNBOUNDED_RESOURCES,
                "execution.resources",
                "Experiment must request bounded cpus, memory and time_limit.",
                doc.file,
            )


def rule_project_consistency(docs: WorkspaceDocs) -> Iterator[Finding]:
    """An experiment in this repository belongs to the repository's project."""
    if docs.repository is None:
        return
    expected = docs.repository.spec.project
    for doc in docs.experiments:
        if doc.manifest.metadata.project != expected:
            yield error(
                FindingCode.PROJECT_MISMATCH,
                "metadata.project",
                f"Experiment declares project {doc.manifest.metadata.project} "
                f"but the repository belongs to {expected}.",
                doc.file,
            )


def rule_seed_policy(docs: WorkspaceDocs) -> Iterator[Finding]:
    for doc in docs.experiments:
        if doc.manifest.execution.seeds is None:
            yield warning(
                FindingCode.MISSING_SEED_POLICY,
                "execution.seeds",
                "Experiment does not declare a seed policy.",
                doc.file,
            )


def rule_references(docs: WorkspaceDocs) -> Iterator[Finding]:
    for doc in docs.experiments:
        if not doc.manifest.scientific.references:
            yield warning(
                FindingCode.MISSING_REFERENCES,
                "scientific.references",
                "Experiment cites no literature references.",
                doc.file,
            )


def rule_scientific_validation(docs: WorkspaceDocs) -> Iterator[Finding]:
    for doc in docs.experiments:
        if doc.manifest.validation is None:
            yield warning(
                FindingCode.MISSING_SCIENTIFIC_VALIDATION,
                "validation",
                "Experiment does not state which test suites are required.",
                doc.file,
            )


def rule_no_secrets(docs: WorkspaceDocs) -> Iterator[Finding]:
    """Tripwire for credentials committed into a manifest (section 15.1).

    Deliberately high-precision: known token shapes plus assignments to
    secret-looking keys. Environment placeholders such as ``${LAB_TOKEN}`` are
    the supported way to reference a secret and are not reported.
    """
    for file_label, text in sorted(docs.raw_texts.items()):
        for number, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            hit = any(pattern.search(line) for pattern in _SECRET_VALUE_PATTERNS)
            if not hit:
                match = _SECRET_KEY_PATTERN.match(line)
                hit = match is not None and not _PLACEHOLDER_PATTERN.match(
                    match["value"].split("#", 1)[0].strip()
                )
            if hit:
                yield error(
                    FindingCode.SECRET_DETECTED,
                    f"line {number}",
                    "Manifest appears to contain a secret. Reference secrets "
                    "through environment variables instead.",
                    file_label,
                )


def rule_component_test_profiles(docs: WorkspaceDocs) -> Iterator[Finding]:
    """A component may only cite test profiles the repository defines."""
    if docs.repository is None:
        return
    available = set(docs.repository.spec.commands)
    for doc in docs.components:
        for suite, profile in sorted(doc.manifest.spec.tests.items()):
            if profile not in available:
                known = ", ".join(sorted(available)) or "none"
                yield error(
                    FindingCode.UNKNOWN_TEST_PROFILE,
                    f"spec.tests.{suite}",
                    f"Command profile {profile!r} is not defined in lab.yaml. "
                    f"Available: {known}.",
                    doc.file,
                )


def rule_component_project(docs: WorkspaceDocs) -> Iterator[Finding]:
    """Components without a maintainer cannot be reviewed by anyone."""
    for doc in docs.components:
        if doc.manifest.metadata.maintainer is None:
            yield warning(
                FindingCode.MISSING_MAINTAINER,
                "metadata.maintainer",
                "Component has no maintainer.",
                doc.file,
            )
        if not doc.manifest.spec.references:
            yield warning(
                FindingCode.MISSING_REFERENCES,
                "spec.references",
                "Component cites no literature references.",
                doc.file,
            )


ALL_RULES: tuple[Rule, ...] = (
    rule_component_test_profiles,
    rule_component_project,
    rule_output_location,
    rule_maintainer,
    rule_dataset_versions,
    rule_bounded_resources,
    rule_project_consistency,
    rule_seed_policy,
    rule_references,
    rule_scientific_validation,
    rule_no_secrets,
)


def run_rules(docs: WorkspaceDocs) -> list[Finding]:
    return [finding for rule in ALL_RULES for finding in rule(docs)]
