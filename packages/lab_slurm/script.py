"""Rendering of the sbatch script from a typed request (AGENTS.md section 8.2).

Every value that reaches the script is shell-quoted, and the template never
concatenates user text into a command line: manifest content is data, not code
(AGENTS.md section 15.3).
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from lab_execution.process import expand_placeholders
from pydantic import BaseModel, ConfigDict

from lab_domain.containers import ContainerEngine
from lab_domain.errors import StateStoreError
from lab_domain.execution import RunRequest

TEMPLATE_NAME = "job.sbatch.j2"
SCRIPT_FILENAME = "job.sbatch"
UNSAFE_IN_NAME = re.compile(r"[^A-Za-z0-9._-]+")
NAME_LIMIT = 64


class SlurmJobOptions(BaseModel):
    """Cluster-specific submission options."""

    model_config = ConfigDict(frozen=True)

    partition: str | None = None
    account: str | None = None
    qos: str | None = None


def job_name(run_id: str) -> str:
    """A job name safe to place in a script and in scheduler output."""
    return UNSAFE_IN_NAME.sub("-", f"lab-{run_id}")[:NAME_LIMIT]


def render_script(
    template_dir: Path,
    request: RunRequest,
    options: SlurmJobOptions,
    engine: ContainerEngine | None = None,
) -> str:
    """Render the sbatch script that runs ``request`` on the cluster."""
    template_path = template_dir / TEMPLATE_NAME
    if not template_path.is_file():
        raise StateStoreError(f"SLURM job template not found at {template_path}.")

    # Placeholders are resolved here, not by the shell that runs the script:
    # the script must record exactly what was executed (ADR 0006).
    argv = list(expand_placeholders(request.argv, request.environment))
    if request.container is not None:
        if engine is None:
            raise StateStoreError(
                "This run requires a container but no container engine is "
                "configured for the SLURM backend."
            )
        argv = list(engine.wrap(request.container, argv))

    environment = Environment(
        loader=FileSystemLoader(template_dir),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    environment.filters["sh"] = shlex.quote
    return environment.get_template(TEMPLATE_NAME).render(
        request=request,
        options=options,
        resources=request.resources,
        labels=request.labels,
        job_name=job_name(str(request.run_id)),
        command=argv,
        stdout_path=request.log_directory / "stdout.log",
        stderr_path=request.log_directory / "stderr.log",
        environment=sorted(request.environment.items()),
    )


def write_script(scratch: Path, contents: str) -> Path:
    """Write the script next to the run's other scratch files."""
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / SCRIPT_FILENAME
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o700)
    return path
