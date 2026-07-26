"""Platform policy: resource ceilings and what happens to scratch.

Cluster safety requires bounded resource requests (AGENTS.md section 15.3), and
scratch is temporary storage that must not be mistaken for the artifact store
(section 8.3).
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from lab_domain.errors import PolicyViolationError, StateStoreError
from lab_domain.manifests.quantities import time_limit_to_seconds
from lab_domain.runs import ResourceRequest

POLICY_FILENAME = "policy.json"


class ScratchPolicy(StrEnum):
    """What to do with a run's scratch directory once artifacts are stored."""

    KEEP = "keep"
    KEEP_ON_FAILURE = "keep_on_failure"
    DELETE = "delete"


class ResourcePolicy(BaseModel):
    """Ceilings a run request may not exceed.

    The defaults are deliberately generous: their job is to stop a typo from
    reserving a whole cluster, not to ration it. A laboratory tightens them in
    ``$LAB_HOME/policy.json``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_cpus: int = Field(default=128, ge=1)
    max_memory_mb: int = Field(default=1024 * 1024, ge=1)
    max_gpus: int = Field(default=8, ge=0)
    max_time_seconds: int = Field(default=7 * 24 * 3600, ge=1)
    scratch: ScratchPolicy = ScratchPolicy.KEEP_ON_FAILURE

    def enforce(self, request: ResourceRequest) -> None:
        """Raise if the request exceeds a ceiling, naming the one it broke."""
        if request.cpus > self.max_cpus:
            raise PolicyViolationError(
                f"Requested {request.cpus} cpus, above the limit of {self.max_cpus}."
            )
        if request.memory_mb > self.max_memory_mb:
            raise PolicyViolationError(
                f"Requested {request.memory_mb} MB of memory, above the limit of "
                f"{self.max_memory_mb} MB."
            )
        if request.gpus > self.max_gpus:
            raise PolicyViolationError(
                f"Requested {request.gpus} gpus, above the limit of {self.max_gpus}."
            )
        if request.time_limit is None:
            raise PolicyViolationError(
                "The experiment requests no wall-time limit; an unbounded job "
                "cannot be scheduled."
            )
        seconds = time_limit_to_seconds(request.time_limit)
        if seconds > self.max_time_seconds:
            raise PolicyViolationError(
                f"Requested a wall time of {request.time_limit}, above the limit "
                f"of {self.max_time_seconds} seconds."
            )


def load_policy(home: Path) -> ResourcePolicy:
    """Read ``$LAB_HOME/policy.json``, or fall back to the defaults."""
    path = home / POLICY_FILENAME
    if not path.is_file():
        return ResourcePolicy()
    try:
        return ResourcePolicy.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError) as exc:
        raise StateStoreError(f"Policy file {path} is unusable: {exc}.") from exc


def write_policy(home: Path, policy: ResourcePolicy) -> Path:
    """Persist a policy; used by tests and by laboratory setup."""
    path = home / POLICY_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy.model_dump(mode="json"), indent=2) + "\n")
    return path
