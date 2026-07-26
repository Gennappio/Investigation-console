"""A generated summary of a finished run (`lab explain`).

This is the one place a language model is allowed to speak, and it speaks only
about facts the platform already recorded. The output is stored as its own
artifact, labelled as generated, next to the exact prompt that was sent, so
what left the building is auditable. Neither the run record nor the report is
touched: AGENTS.md section 11 keeps execution metadata out of a model's hands.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from lab_domain.artifacts import ArtifactKind, ArtifactRecord
from lab_domain.errors import LanguageModelError, NotFoundError
from lab_domain.ids import RunId
from lab_domain.language import Completion, LanguageModel, Message, Role
from lab_domain.services.report_service import ReportDocument, build_document
from lab_domain.storage import ArtifactStore, RunStore

EXPLANATION_FILENAME = "explanation.md"
PROMPT_FILENAME = "explanation.prompt.txt"

SYSTEM_PROMPT = (
    "You summarise computational experiments for a research laboratory. You "
    "report only what the record states, you never infer a scientific "
    "conclusion, and you say plainly when something was not recorded."
)

WARNING = (
    "Generated text, not evidence. Every fact about this run lives in the run "
    "record and the report; this summary may be wrong and is not part of the "
    "provenance."
)

PromptRenderer = Callable[[ReportDocument], str]


class AuditSink(Protocol):
    def record(self, action: str, actor: str, **context: Any) -> None: ...


class Explanation(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: RunId
    provider: str
    model: str
    text: str
    artifact: ArtifactRecord
    prompt_artifact: ArtifactRecord


def explain_run(
    run_id: RunId,
    *,
    store: RunStore,
    artifacts: ArtifactStore,
    model: LanguageModel,
    render_prompt: PromptRenderer,
    scratch_root: Path,
    audit: AuditSink,
    actor: str,
) -> Explanation:
    """Ask the configured model to describe a finished run."""
    record = store.get_run(run_id)
    if not record.is_terminal:
        raise NotFoundError(
            f"Run {run_id} is {record.status.value}; there is nothing to "
            "summarise until it has finished."
        )
    if not model.available():
        raise LanguageModelError(
            "No language model is configured. Set OPENROUTER_API_KEY and "
            "LAB_LLM_MODEL, or leave them unset: every other command works "
            "without a model."
        )

    document = build_document(
        record, store, artifacts.list_artifacts(run_id), artifacts
    )
    prompt = render_prompt(document)
    completion = model.complete(
        [
            Message(role=Role.SYSTEM, content=SYSTEM_PROMPT),
            Message(role=Role.USER, content=prompt),
        ]
    )

    scratch = scratch_root / str(run_id) / "explanation"
    scratch.mkdir(parents=True, exist_ok=True)
    prompt_path = scratch / PROMPT_FILENAME
    prompt_path.write_text(prompt, encoding="utf-8")
    explanation_path = scratch / EXPLANATION_FILENAME
    explanation_path.write_text(
        _render_document(record.id, completion, prompt), encoding="utf-8"
    )

    stored = artifacts.store(
        explanation_path, kind=ArtifactKind.EXPLANATION, run_id=run_id
    )
    stored_prompt = artifacts.store(
        prompt_path, kind=ArtifactKind.PROVENANCE, run_id=run_id
    )
    audit.record(
        "run.explained",
        actor=actor,
        run_id=run_id,
        provider=completion.provider,
        model=completion.model,
    )
    return Explanation(
        run_id=run_id,
        provider=completion.provider,
        model=completion.model,
        text=completion.text,
        artifact=stored,
        prompt_artifact=stored_prompt,
    )


def _render_document(run_id: RunId, completion: Completion, prompt: str) -> str:
    """The stored summary, with its origin attached to it."""
    prompt_digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    header = [
        "---",
        "kind: explanation",
        f"run: {run_id}",
        f"generated_at: {datetime.now(UTC).isoformat()}",
        f"provider: {completion.provider}",
        f"model: {completion.model}",
        f"prompt_sha256: {prompt_digest}",
        f"prompt_artifact: {PROMPT_FILENAME}",
        f"warning: {WARNING}",
        "---",
        "",
        f"# {run_id}: generated summary",
        "",
        f"> {WARNING}",
        "",
    ]
    return "\n".join(header) + completion.text.strip() + "\n"
