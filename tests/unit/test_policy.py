from __future__ import annotations

import json
from pathlib import Path

import pytest

from lab_domain.errors import PolicyViolationError, StateStoreError
from lab_domain.policy import ResourcePolicy, ScratchPolicy, load_policy, write_policy
from lab_domain.runs import ResourceRequest

WITHIN = ResourceRequest(cpus=8, memory_mb=16384, gpus=1, time_limit="06:00:00")


def test_a_request_within_the_ceilings_is_accepted() -> None:
    ResourcePolicy().enforce(WITHIN)


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        (ResourcePolicy(max_cpus=4), "cpus"),
        (ResourcePolicy(max_memory_mb=1024), "memory"),
        (ResourcePolicy(max_gpus=0), "gpus"),
        (ResourcePolicy(max_time_seconds=60), "wall time"),
    ],
)
def test_each_ceiling_is_enforced(policy: ResourcePolicy, expected: str) -> None:
    with pytest.raises(PolicyViolationError, match=expected):
        policy.enforce(WITHIN)


def test_an_unbounded_request_is_refused() -> None:
    with pytest.raises(PolicyViolationError, match="no wall-time limit"):
        ResourcePolicy().enforce(ResourceRequest(cpus=1, memory_mb=1024))


def test_defaults_apply_without_a_policy_file(tmp_path: Path) -> None:
    policy = load_policy(tmp_path)
    assert policy == ResourcePolicy()
    assert policy.scratch is ScratchPolicy.KEEP_ON_FAILURE


def test_a_laboratory_policy_is_read_back(tmp_path: Path) -> None:
    write_policy(tmp_path, ResourcePolicy(max_cpus=16, scratch=ScratchPolicy.DELETE))
    policy = load_policy(tmp_path)
    assert policy.max_cpus == 16
    assert policy.scratch is ScratchPolicy.DELETE


def test_a_partial_policy_keeps_the_other_defaults(tmp_path: Path) -> None:
    (tmp_path / "policy.json").write_text(json.dumps({"max_gpus": 2}))
    policy = load_policy(tmp_path)
    assert policy.max_gpus == 2
    assert policy.max_cpus == ResourcePolicy().max_cpus


def test_an_unusable_policy_is_reported(tmp_path: Path) -> None:
    (tmp_path / "policy.json").write_text("{not json")
    with pytest.raises(StateStoreError, match="unusable"):
        load_policy(tmp_path)


def test_an_unknown_policy_key_is_refused(tmp_path: Path) -> None:
    """A typo in a limit must not silently leave the cluster unprotected."""
    (tmp_path / "policy.json").write_text(json.dumps({"max_cpu": 4}))
    with pytest.raises(StateStoreError, match="unusable"):
        load_policy(tmp_path)
