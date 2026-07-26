"""The component registry: publish, search, promote (AGENTS.md sections 6.4, 19).

Publishing states what a component *is* and what the recorded evidence
supports. It never claims more than that: `validated` and `lab_standard` are
granted by a person through :func:`promote_component`, which writes a decision
record (ADR 0009).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from lab_domain.components import (
    REVIEWED_LEVELS,
    ComponentRecord,
    DecisionRecord,
    Maturity,
    ReviewRef,
    SuiteEvidence,
    content_hash,
    evidenced_maturity,
    missing_for_next_level,
)
from lab_domain.errors import (
    ManifestInvalidError,
    NotFoundError,
    PolicyViolationError,
    TargetExistsError,
)
from lab_domain.ids import ComponentId, ProjectId
from lab_domain.manifests.loader import load_manifest
from lab_domain.manifests.models import ComponentManifest, RepositoryManifest
from lab_domain.services.validate_service import validate_workspace
from lab_domain.storage import ComponentStore, RunStore
from lab_domain.suites import SuiteKind, SuiteResult
from lab_domain.workspace import MANIFEST_NAME, component_manifest_paths

MINIMUM_NOTE_LENGTH = 10


class AuditSink(Protocol):
    def record(self, action: str, actor: str, **context: Any) -> None: ...


class PublishResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    component: ComponentRecord
    # What would have to pass for the next evidenced level, so the answer to
    # "why is this only runnable?" is in the output rather than in someone's head.
    missing_for_next: tuple[str, ...]
    already_published: bool


class SearchHit(BaseModel):
    model_config = ConfigDict(frozen=True)

    component: ComponentRecord
    score: int


def publish_component(
    root: Path,
    *,
    name: str | None,
    store: ComponentStore,
    runs: RunStore,
    audit: AuditSink,
    actor: str,
) -> PublishResult:
    """Register a component version from its manifest, with its evidence."""
    report = validate_workspace(root)
    if not report.valid:
        raise ManifestInvalidError(
            f"{len(report.errors)} validation error(s) in {root}. "
            "Run `lab validate` for the details."
        )

    repository, _ = load_manifest(
        RepositoryManifest, root / MANIFEST_NAME, MANIFEST_NAME
    )
    if repository is None:  # pragma: no cover - validation guarantees this
        raise ManifestInvalidError(f"Cannot read {root / MANIFEST_NAME}.")
    manifest = _select_component(root, name)
    project_id = repository.spec.project

    evidence = _gather_evidence(manifest, runs, project_id)
    status = evidenced_maturity(evidence)
    published = _content(manifest)
    digest = content_hash(published)

    existing = [
        record
        for record in store.find_by_name(project_id, manifest.metadata.name)
        if record.version == manifest.spec.version
    ]
    if existing:
        previous = existing[0]
        if previous.content_hash != digest:
            raise TargetExistsError(
                f"{manifest.metadata.name} {manifest.spec.version} is already "
                "published with different content. Publish a new version "
                "instead of changing one that others may depend on."
            )
        # Same content: refresh the evidence, keep the identity and the review.
        record = previous.model_copy(
            update={
                "evidence": evidence,
                "status": (
                    previous.status if previous.status in REVIEWED_LEVELS else status
                ),
            }
        )
        store.save_component(record)
        return PublishResult(
            component=record,
            missing_for_next=missing_for_next_level(evidence),
            already_published=True,
        )

    siblings = store.find_by_name(project_id, manifest.metadata.name)
    component_id = siblings[0].id if siblings else store.allocate_component_id()
    record = ComponentRecord(
        id=component_id,
        project_id=project_id,
        name=manifest.metadata.name,
        version=manifest.spec.version,
        status=status,
        maintainer=manifest.metadata.maintainer,
        description=manifest.metadata.description,
        keywords=manifest.metadata.keywords,
        command=manifest.spec.command,
        inputs={
            key: port.description or port.type
            for key, port in manifest.spec.inputs.items()
        },
        outputs={
            key: port.description or port.type
            for key, port in manifest.spec.outputs.items()
        },
        container=(
            manifest.spec.container.dockerfile if manifest.spec.container else None
        ),
        tests=dict(manifest.spec.tests),
        references=manifest.spec.references,
        evidence=evidence,
        content_hash=digest,
        published_by=actor,
        published_at=datetime.now(UTC),
    )
    store.save_component(record)
    audit.record(
        "component.published",
        actor=actor,
        component=record.id,
        version=record.version,
        status=record.status.value,
    )
    return PublishResult(
        component=record,
        missing_for_next=missing_for_next_level(evidence),
        already_published=False,
    )


def search_components(
    query: str,
    *,
    store: ComponentStore,
    status: Maturity | None = None,
    limit: int = 20,
) -> tuple[SearchHit, ...]:
    """Find components by name, description and keywords.

    Only the newest published version of each component is returned; an empty
    query lists everything, which is how a reviewer sees the whole registry.
    """
    newest: dict[ComponentId, ComponentRecord] = {}
    for record in store.list_components():
        current = newest.get(record.id)
        if current is None or record.published_at >= current.published_at:
            newest[record.id] = record

    terms = [term for term in query.lower().split() if term]
    hits = []
    for record in newest.values():
        if status is not None and record.status is not status:
            continue
        score = _score(record, terms)
        if terms and score == 0:
            continue
        hits.append(SearchHit(component=record, score=score))

    hits.sort(key=lambda hit: (-hit.score, hit.component.name, hit.component.version))
    return tuple(hits[:limit])


def promote_component(
    component_id: ComponentId,
    *,
    to: Maturity,
    reviewer: str,
    note: str,
    store: ComponentStore,
    audit: AuditSink,
    version: str | None = None,
) -> tuple[ComponentRecord, DecisionRecord]:
    """Record a human judgement about a component's maturity.

    Only the levels a person must grant can be set this way; the evidenced
    levels come from test results and are not a matter of opinion.
    """
    if to not in REVIEWED_LEVELS:
        granted = ", ".join(sorted(level.value for level in REVIEWED_LEVELS))
        raise PolicyViolationError(
            f"{to.value} is decided by recorded evidence, not by review. "
            f"A reviewer may grant: {granted}."
        )
    if len(note.strip()) < MINIMUM_NOTE_LENGTH:
        raise PolicyViolationError(
            "A promotion needs a note saying what was reviewed; it becomes the "
            "decision record others will read."
        )

    record = store.get_component(component_id, version)
    if record.status is to:
        raise NotFoundError(f"{record.id} {record.version} is already {to.value}.")

    decision = DecisionRecord(
        id=store.allocate_decision_id(),
        component_id=record.id,
        component_version=record.version,
        from_status=record.status,
        to_status=to,
        reviewer=reviewer,
        note=note.strip(),
        decided_at=datetime.now(UTC),
    )
    promoted = record.model_copy(
        update={
            "status": to,
            "review": ReviewRef(
                decision=decision.id,
                reviewer=reviewer,
                decided_at=decision.decided_at,
            ),
        }
    )
    store.save_decision(decision)
    store.save_component(promoted)
    audit.record(
        "component.promoted",
        actor=reviewer,
        component=record.id,
        version=record.version,
        decision=decision.id,
        status=to.value,
    )
    return promoted, decision


def _select_component(root: Path, name: str | None) -> ComponentManifest:
    manifests = []
    for path in component_manifest_paths(root):
        manifest, _ = load_manifest(
            ComponentManifest, path, path.relative_to(root).as_posix()
        )
        if manifest is not None:
            manifests.append(manifest)

    if not manifests:
        raise NotFoundError(
            f"No component manifest found under {root / 'components'}. A "
            "component is declared in components/<name>.yaml."
        )
    if name is None:
        if len(manifests) > 1:
            names = ", ".join(m.metadata.name for m in manifests)
            raise ManifestInvalidError(
                f"This repository declares several components ({names}). "
                "Choose one with --name."
            )
        return manifests[0]

    for manifest in manifests:
        if manifest.metadata.name == name:
            return manifest
    raise NotFoundError(f"No component named {name!r} in {root}.")


def _gather_evidence(
    manifest: ComponentManifest, runs: RunStore, project_id: ProjectId
) -> tuple[SuiteEvidence, ...]:
    """The latest recorded result for each test profile the component cites."""
    results = runs.list_test_results(project_id)
    evidence = []
    for suite_name, profile in sorted(manifest.spec.tests.items()):
        suite = SuiteKind(suite_name)
        latest = _latest(results, suite, profile)
        if latest is not None:
            evidence.append(
                SuiteEvidence(
                    suite=suite,
                    profile=profile,
                    status=latest.status,
                    completed_at=latest.completed_at,
                )
            )
    return tuple(evidence)


def _latest(
    results: tuple[SuiteResult, ...], suite: SuiteKind, profile: str
) -> SuiteResult | None:
    matching = [r for r in results if r.suite is suite and r.profile == profile]
    return max(matching, key=lambda r: r.completed_at) if matching else None


def _content(manifest: ComponentManifest) -> dict[str, Any]:
    """What a published version claims to be, for change detection."""
    return manifest.model_dump(mode="json", by_alias=True)


def _score(record: ComponentRecord, terms: list[str]) -> int:
    """How well a component answers the query. Name matches count double."""
    name = record.name.lower()
    keywords = " ".join(record.keywords).lower()
    description = (record.description or "").lower()
    score = 0
    for term in terms:
        if term in name:
            score += 2
        if term in keywords:
            score += 2
        if term in description:
            score += 1
    return score
