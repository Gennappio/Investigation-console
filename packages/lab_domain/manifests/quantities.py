"""Parsing of resource quantities used in experiment manifests.

Shared by validation now and by SLURM script rendering in Milestone 3.
"""

from __future__ import annotations

import re

MEMORY_PATTERN = re.compile(r"^(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[KMGT]i?B?)$")
TIME_LIMIT_PATTERN = re.compile(r"^(?:\d+-)?\d{1,2}:\d{2}:\d{2}$")

_MEGABYTES_PER_UNIT = {
    "KB": 1000**1 / 1000**2,
    "MB": 1,
    "GB": 1000,
    "TB": 1000**2,
    "KiB": 1024**1 / 1000**2,
    "MiB": 1024**2 / 1000**2,
    "GiB": 1024**3 / 1000**2,
    "TiB": 1024**4 / 1000**2,
}


def parse_memory_to_mb(value: str) -> int:
    """Convert a memory string such as ``128GiB`` to whole megabytes.

    Raises ``ValueError`` for unparseable or non-positive quantities.
    """
    match = MEMORY_PATTERN.match(value.strip())
    if match is None:
        raise ValueError(
            f"malformed memory quantity {value!r}: expected a number and a unit "
            "such as 512MB, 1GiB, 128GiB"
        )
    unit = match["unit"]
    if not unit.endswith("B"):
        unit += "B"
    megabytes = float(match["value"]) * _MEGABYTES_PER_UNIT[unit]
    if megabytes < 1:
        raise ValueError(f"memory quantity {value!r} is smaller than one megabyte")
    return round(megabytes)


def validate_time_limit(value: str) -> str:
    """Return ``value`` if it is a ``[days-]HH:MM:SS`` wall-time limit."""
    if TIME_LIMIT_PATTERN.match(value.strip()) is None:
        raise ValueError(
            f"malformed time limit {value!r}: expected HH:MM:SS or D-HH:MM:SS"
        )
    return value
