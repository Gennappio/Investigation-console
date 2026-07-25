from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from lab_domain.ids import (
    ComponentId,
    DatasetId,
    ExperimentId,
    ProjectId,
    RunId,
    TypedId,
)


def test_accepts_canonical_form() -> None:
    assert ProjectId("PRJ-000001") == "PRJ-000001"
    assert DatasetId("DATA-000042").prefix == "DATA"


@pytest.mark.parametrize(
    "value",
    ["PRJ-1", "PRJ-0001", "PRJ-0000001", "prj-000001", "PRJ000001", "", "PRJ-00000a"],
)
def test_rejects_non_canonical_form(value: str) -> None:
    with pytest.raises(ValueError, match="malformed PRJ identifier"):
        ProjectId(value)


def test_prefixes_are_not_interchangeable() -> None:
    with pytest.raises(ValueError, match="malformed PRJ identifier"):
        ProjectId("EXP-000001")


def test_from_int_pads_to_six_digits() -> None:
    assert ExperimentId.from_int(1) == "EXP-000001"
    assert RunId.from_int(999999) == "RUN-999999"


@pytest.mark.parametrize("number", [0, -1, 1000000])
def test_from_int_rejects_out_of_range(number: int) -> None:
    with pytest.raises(ValueError, match="outside 1"):
        ComponentId.from_int(number)


def test_repr_names_the_type() -> None:
    assert repr(ProjectId("PRJ-000007")) == "ProjectId('PRJ-000007')"


class _Model(BaseModel):
    project: ProjectId


def test_pydantic_validates_and_types_the_value() -> None:
    assert isinstance(_Model(project=ProjectId("PRJ-000001")).project, ProjectId)
    assert isinstance(_Model.model_validate({"project": "PRJ-000002"}).project, TypedId)
    with pytest.raises(ValidationError):
        _Model.model_validate({"project": "nope"})


def test_json_schema_exposes_the_pattern() -> None:
    schema = _Model.model_json_schema()["properties"]["project"]
    assert schema["type"] == "string"
    assert schema["pattern"] == "^PRJ-[0-9]{6}$"
