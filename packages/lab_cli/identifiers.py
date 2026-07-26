"""Parsing of identifiers supplied on the command line.

Identifiers arrive as text and become typed values here, at the boundary, so a
malformed one is reported as invalid input rather than failing deeper down.
"""

from __future__ import annotations

from lab_domain.errors import InvalidNameError
from lab_domain.ids import TypedId


def parse_id[IdT: TypedId](id_type: type[IdT], value: str) -> IdT:
    try:
        return id_type(value)
    except ValueError as exc:
        raise InvalidNameError(str(exc)) from exc


def parse_optional_id[IdT: TypedId](
    id_type: type[IdT], value: str | None
) -> IdT | None:
    return None if value is None else parse_id(id_type, value)
