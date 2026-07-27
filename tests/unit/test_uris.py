from __future__ import annotations

import pytest

from lab_domain.ids import (
    ArtifactId,
    ComponentId,
    DatasetId,
    ExperimentId,
    ProjectId,
    RunId,
)
from lab_domain.uris import artifacts_uri, lab_uri, parse_lab_uri, report_uri


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        (ProjectId("PRJ-000001"), "lab-project://PRJ-000001"),
        (ExperimentId("EXP-000001"), "lab-experiment://EXP-000001"),
        (RunId("RUN-000001"), "lab-run://RUN-000001"),
        (ComponentId("CMP-000001"), "lab-component://CMP-000001"),
        (DatasetId("DATA-000001"), "lab-dataset://DATA-000001"),
        (ArtifactId("ART-000001"), "lab-artifact://ART-000001"),
    ],
)
def test_each_kind_has_a_scheme(identifier: object, expected: str) -> None:
    assert lab_uri(identifier) == expected  # type: ignore[arg-type]


def test_a_uri_can_address_something_within_an_object() -> None:
    assert artifacts_uri(RunId("RUN-000001")) == "lab-run://RUN-000001/artifacts"
    assert report_uri(RunId("RUN-000001")) == "lab-report://RUN-000001"


@pytest.mark.parametrize(
    "uri",
    [
        "lab-run://RUN-000001",
        "lab-run://RUN-000001/artifacts",
        "  lab-run://RUN-000001  ",
    ],
)
def test_parsing_recovers_the_identifier(uri: str) -> None:
    identifier = parse_lab_uri(uri)
    assert identifier == "RUN-000001"
    assert isinstance(identifier, RunId)


@pytest.mark.parametrize(
    "uri",
    [
        "",
        "RUN-000001",
        "https://example/RUN-000001",
        "lab-run:/RUN-000001",
        "lab-run://",
    ],
)
def test_a_malformed_uri_is_refused(uri: str) -> None:
    with pytest.raises(ValueError, match="Malformed"):
        parse_lab_uri(uri)


def test_an_unknown_scheme_is_refused() -> None:
    with pytest.raises(ValueError, match="Unknown URI scheme"):
        parse_lab_uri("lab-nonsense://RUN-000001")


def test_uris_never_contain_a_filesystem_path() -> None:
    """Section 2.4: a path is not an identifier and must not become one."""
    uri = lab_uri(RunId("RUN-000001"))
    assert "/scratch" not in uri
    assert uri.count("//") == 1
