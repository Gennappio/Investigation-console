"""Artifacts: every relevant output of a run (AGENTS.md section 6.6).

The identifier is the canonical handle; ``uri`` is where the bytes currently
live and may change when storage moves (AGENTS.md section 2.4).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from lab_domain.ids import ArtifactId, RunId


class ArtifactKind(StrEnum):
    RESULT = "result"
    LOG = "log"
    REPORT = "report"
    PROVENANCE = "provenance"
    SNAPSHOT = "snapshot"
    CHECKSUMS = "checksums"
    BUILD_LOG = "build_log"
    JOB_SCRIPT = "job_script"
    # Generated text, never evidence (AGENTS.md section 11).
    EXPLANATION = "explanation"
    TEST_RESULT = "test_result"


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: ArtifactId
    # Build logs and other artifacts produced outside a run have no run.
    run_id: RunId | None
    kind: ArtifactKind
    name: str
    uri: str
    checksum: str
    size_bytes: int
    media_type: str
    created_at: datetime
