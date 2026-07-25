from __future__ import annotations

import pytest

from lab_domain.manifests.quantities import parse_memory_to_mb, validate_time_limit


@pytest.mark.parametrize(
    ("value", "expected_mb"),
    [
        ("1MB", 1),
        ("512MB", 512),
        ("1GB", 1000),
        ("1GiB", 1074),
        ("128GiB", 137439),
        ("2TiB", 2199023),
        ("1024KiB", 1),
        (" 4 GiB ", 4295),
    ],
)
def test_parses_memory(value: str, expected_mb: int) -> None:
    assert parse_memory_to_mb(value) == expected_mb


@pytest.mark.parametrize("value", ["", "128", "GiB", "-1GiB", "128 gigs", "1KB"])
def test_rejects_bad_memory(value: str) -> None:
    with pytest.raises(ValueError, match="memory"):
        parse_memory_to_mb(value)


@pytest.mark.parametrize("value", ["00:10:00", "06:00:00", "1-00:00:00", "12-23:59:59"])
def test_accepts_time_limits(value: str) -> None:
    assert validate_time_limit(value) == value


@pytest.mark.parametrize("value", ["", "6:00", "600", "1:2:3:4", "06:00", "abc"])
def test_rejects_bad_time_limits(value: str) -> None:
    with pytest.raises(ValueError, match="time limit"):
        validate_time_limit(value)
