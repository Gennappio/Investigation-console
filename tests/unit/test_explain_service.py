"""What the platform sends to a model, and what it does with the answer."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from lab_artifacts.filesystem_store import FilesystemArtifactStore
from lab_llm.prompts import render_run_explanation

from lab_domain.artifacts import ArtifactKind
from lab_domain.errors import LanguageModelError, NotFoundError
from lab_domain.language import Completion, Message
from lab_domain.runs import RunRecord, RunStatus
from lab_domain.services.explain_service import WARNING, explain_run
from lab_registry.audit import AuditLog
from lab_registry.local_store import LocalRegistry
from lab_registry.run_store import FileRunStore

RunFactory = Callable[..., RunRecord]
PROMPTS = Path(__file__).resolve().parents[2] / "templates" / "prompts"


@dataclass
class FakeModel:
    """A model that records what it was asked and answers with fixed text."""

    text: str = "The run completed and produced two outputs."
    available_: bool = True
    prompts: list[Sequence[Message]] = field(default_factory=list)

    @property
    def provider(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "fake/model-1"

    def available(self) -> bool:
        return self.available_

    def complete(self, messages: Sequence[Message]) -> Completion:
        self.prompts.append(messages)
        return Completion(text=self.text, provider=self.provider, model=self.model)


@pytest.fixture
def platform(tmp_path: Path) -> tuple[FileRunStore, FilesystemArtifactStore, AuditLog]:
    registry = LocalRegistry(tmp_path / "home")
    return (
        FileRunStore(tmp_path / "home", registry),
        FilesystemArtifactStore(tmp_path / "artifacts", registry),
        AuditLog(tmp_path / "home"),
    )


def explain(
    platform: tuple[FileRunStore, FilesystemArtifactStore, AuditLog],
    model: FakeModel,
    tmp_path: Path,
    run_id: str = "RUN-000001",
):  # noqa: ANN201 - returns the service's Explanation
    store, artifacts, audit = platform
    return explain_run(
        run_id,
        store=store,
        artifacts=artifacts,
        model=model,
        render_prompt=lambda document: render_run_explanation(PROMPTS, document),
        scratch_root=tmp_path / "work",
        audit=audit,
        actor="anna.rossi",
    )


def test_the_prompt_carries_only_recorded_facts(
    platform: tuple[FileRunStore, FilesystemArtifactStore, AuditLog],
    make_run: RunFactory,
    tmp_path: Path,
) -> None:
    store, _, _ = platform
    store.save_run(make_run(RunStatus.COMPLETED, exit_code=0))
    model = FakeModel()

    explain(platform, model, tmp_path)

    system, user = model.prompts[0]
    assert "never infer a scientific conclusion" in system.content
    assert "RUN-000001" in user.content
    assert "sha256:deadbeef" in user.content  # the configuration hash
    assert "a91bd29" in user.content  # the recorded commit
    assert "Use only the facts below" in user.content
    assert "not scientific validity" in user.content


def test_the_summary_is_stored_and_labelled_as_generated(
    platform: tuple[FileRunStore, FilesystemArtifactStore, AuditLog],
    make_run: RunFactory,
    tmp_path: Path,
) -> None:
    store, artifacts, _ = platform
    store.save_run(make_run(RunStatus.COMPLETED, exit_code=0))

    explanation = explain(platform, FakeModel(), tmp_path)

    assert explanation.artifact.kind is ArtifactKind.EXPLANATION
    assert explanation.artifact.name == "explanation.md"
    body = artifacts.resolve(explanation.artifact).read_text()
    assert body.startswith("---\nkind: explanation")
    assert "provider: fake" in body
    assert "model: fake/model-1" in body
    assert "prompt_sha256: " in body
    assert WARNING in body
    assert explanation.text in body


def test_the_prompt_is_stored_so_what_was_sent_is_auditable(
    platform: tuple[FileRunStore, FilesystemArtifactStore, AuditLog],
    make_run: RunFactory,
    tmp_path: Path,
) -> None:
    store, artifacts, audit = platform
    store.save_run(make_run(RunStatus.COMPLETED, exit_code=0))

    explanation = explain(platform, FakeModel(), tmp_path)

    stored_prompt = artifacts.resolve(explanation.prompt_artifact).read_text()
    assert "RUN-000001" in stored_prompt
    assert explanation.prompt_artifact.name == "explanation.prompt.txt"
    assert [entry["action"] for entry in audit.entries()] == ["run.explained"]
    assert audit.entries()[0]["model"] == "fake/model-1"


def test_the_run_record_is_left_alone(
    platform: tuple[FileRunStore, FilesystemArtifactStore, AuditLog],
    make_run: RunFactory,
    tmp_path: Path,
) -> None:
    """A generated summary is never part of what the run produced."""
    store, _, _ = platform
    record = make_run(RunStatus.COMPLETED, exit_code=0, artifacts=("ART-000009",))
    store.save_run(record)

    explain(platform, FakeModel(), tmp_path)

    assert store.get_run("RUN-000001") == record


def test_an_unfinished_run_has_nothing_to_summarise(
    platform: tuple[FileRunStore, FilesystemArtifactStore, AuditLog],
    make_run: RunFactory,
    tmp_path: Path,
) -> None:
    store, _, _ = platform
    store.save_run(make_run(RunStatus.RUNNING))
    with pytest.raises(NotFoundError, match="nothing to"):
        explain(platform, FakeModel(), tmp_path)


def test_an_unconfigured_model_says_so_without_failing_anything_else(
    platform: tuple[FileRunStore, FilesystemArtifactStore, AuditLog],
    make_run: RunFactory,
    tmp_path: Path,
) -> None:
    store, _, _ = platform
    store.save_run(make_run(RunStatus.COMPLETED, exit_code=0))
    with pytest.raises(LanguageModelError, match="every other command works"):
        explain(platform, FakeModel(available_=False), tmp_path)


def test_a_failed_run_can_also_be_summarised(
    platform: tuple[FileRunStore, FilesystemArtifactStore, AuditLog],
    make_run: RunFactory,
    tmp_path: Path,
) -> None:
    store, _, _ = platform
    store.save_run(
        make_run(RunStatus.FAILED, exit_code=7, failure_reason="Exit code 7.")
    )
    model = FakeModel()
    explain(platform, model, tmp_path)
    _, user = model.prompts[0]
    assert "failed" in user.content
    assert "Exit code 7." in user.content
