"""`lab build`: build the container image this repository declares."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lab_cli.exit_codes import ExitCode
from lab_cli.identifiers import parse_optional_id
from lab_cli.options import EXPERIMENT_OPTION, JSON_OPTION
from lab_cli.output import emit, run_or_fail
from lab_cli.runtime import (
    default_artifact_store,
    default_container_engine,
)
from lab_domain.ids import ExperimentId
from lab_domain.services import BuildSummary, build_image, load_validated_workspace
from lab_domain.workspace import find_workspace_root


def build(
    json_output: Annotated[bool, JSON_OPTION] = False,
    experiment: Annotated[str | None, EXPERIMENT_OPTION] = None,
    tag: Annotated[
        str | None, typer.Option("--tag", help="Image tag to build.")
    ] = None,
) -> None:
    """Validate the manifests, build the image, and record its digest."""

    def action() -> BuildSummary:
        chosen = parse_optional_id(ExperimentId, experiment)
        context = load_validated_workspace(find_workspace_root(Path.cwd()), chosen)
        return build_image(
            context,
            engine=default_container_engine(),
            artifacts=default_artifact_store(),
            tag=tag,
        )

    summary = run_or_fail(json_output, action)
    emit(
        {
            "status": summary.status,
            "image": summary.image,
            "digest": summary.digest,
            "build_log_artifact": f"lab-artifact://{summary.build_log_artifact}",
        },
        "\n".join(
            [
                f"Built {summary.image}",
                f"  digest:    {summary.digest or 'not reported by the engine'}",
                f"  build log: {summary.build_log_artifact}",
            ]
        ),
        json_output,
    )
    raise typer.Exit(int(ExitCode.OK))
