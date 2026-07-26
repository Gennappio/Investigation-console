"""Composition root: where the CLI resolves its infrastructure."""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

from lab_artifacts.filesystem_store import FilesystemArtifactStore
from lab_containers.apptainer_engine import ApptainerEngine
from lab_containers.docker_engine import DockerEngine
from lab_execution.local_backend import LocalExecutionBackend
from lab_llm.config import load_settings
from lab_llm.openrouter import OpenRouterModel
from lab_slurm.backend import SlurmExecutionBackend, SlurmOptions
from lab_slurm.jobs import JobIndex

from lab_domain.containers import ContainerEngine
from lab_domain.errors import ExecutionFailedError, StateStoreError
from lab_domain.execution import ExecutionBackend
from lab_domain.language import LanguageModel
from lab_domain.policy import ResourcePolicy, load_policy
from lab_registry.audit import AuditLog
from lab_registry.local_store import LocalRegistry
from lab_registry.run_store import FileRunStore

DEFAULT_LAB_HOME = "~/.lab"
INSTALLED_TEMPLATES = Path("share") / "lab-platform" / "templates"
PROJECT_TEMPLATE_MARKER = "lab.yaml.j2"
ARTIFACTS_DIRECTORY = "artifacts"
WORK_DIRECTORY = "work"
LOCAL_BACKEND = "local"
SLURM_BACKEND = "slurm"
BACKENDS = (LOCAL_BACKEND, SLURM_BACKEND)


def lab_home() -> Path:
    """Directory holding platform state, overridable with ``LAB_HOME``."""
    return Path(os.environ.get("LAB_HOME", DEFAULT_LAB_HOME)).expanduser()


def artifacts_root() -> Path:
    """Permanent artifact storage; scratch lives elsewhere (section 8.3)."""
    return lab_home() / ARTIFACTS_DIRECTORY


def scratch_root() -> Path:
    return lab_home() / WORK_DIRECTORY


def actor() -> str:
    """Who is running the command, recorded on runs and in the audit log."""
    return getpass.getuser()


def default_registry() -> LocalRegistry:
    return LocalRegistry(lab_home())


def default_run_store() -> FileRunStore:
    return FileRunStore(lab_home(), default_registry())


def default_artifact_store() -> FilesystemArtifactStore:
    return FilesystemArtifactStore(artifacts_root(), default_registry())


def default_audit_log() -> AuditLog:
    return AuditLog(lab_home())


def default_policy() -> ResourcePolicy:
    return load_policy(lab_home())


def default_language_model(model: str | None = None) -> LanguageModel:
    """The optional model. Unconfigured is a normal state, not an error."""
    settings = load_settings(lab_home())
    if model:
        settings = settings.model_copy(update={"model": model})
    return OpenRouterModel(settings)


def default_container_engine(backend: str = LOCAL_BACKEND) -> ContainerEngine:
    """Docker builds and runs images locally; clusters run them with Apptainer."""
    return ApptainerEngine() if backend == SLURM_BACKEND else DockerEngine()


def slurm_options() -> SlurmOptions:
    """Cluster submission options, from the environment."""
    return SlurmOptions(
        partition=os.environ.get("LAB_SLURM_PARTITION"),
        account=os.environ.get("LAB_SLURM_ACCOUNT"),
        qos=os.environ.get("LAB_SLURM_QOS"),
        cluster=os.environ.get("LAB_SLURM_CLUSTER"),
    )


def execution_backend(name: str = LOCAL_BACKEND) -> ExecutionBackend:
    """The backend a command asked for, wired to its container engine."""
    if name == LOCAL_BACKEND:
        return LocalExecutionBackend(engine=default_container_engine(LOCAL_BACKEND))
    if name == SLURM_BACKEND:
        return SlurmExecutionBackend(
            template_dir=slurm_template_dir(),
            index=JobIndex(lab_home()),
            options=slurm_options(),
            engine=default_container_engine(SLURM_BACKEND),
        )
    raise ExecutionFailedError(
        f"Unknown backend {name!r}. Available: {', '.join(BACKENDS)}."
    )


def templates_root() -> Path:
    """Directory holding the platform templates.

    Looked up in the installed environment first, then in the source tree, so
    the CLI works from a wheel and from a checkout.
    """
    override = os.environ.get("LAB_TEMPLATES_DIR")
    if override:
        # An explicit override is never silently ignored.
        directory = Path(override).expanduser()
        if not (directory / "project" / PROJECT_TEMPLATE_MARKER).is_file():
            raise StateStoreError(
                f"LAB_TEMPLATES_DIR points at {directory}, which holds no "
                f"project/{PROJECT_TEMPLATE_MARKER}."
            )
        return directory

    candidates = [
        Path(sys.prefix) / INSTALLED_TEMPLATES,
        Path(__file__).resolve().parents[2] / "templates",
    ]
    for candidate in candidates:
        if (candidate / "project" / PROJECT_TEMPLATE_MARKER).is_file():
            return candidate

    searched = ", ".join(str(c) for c in candidates)
    raise StateStoreError(
        f"Platform templates not found. Searched: {searched}. "
        "Set LAB_TEMPLATES_DIR to the templates directory."
    )


def project_template_dir() -> Path:
    return templates_root() / "project"


def report_template_dir() -> Path:
    return templates_root() / "report"


def slurm_template_dir() -> Path:
    return templates_root() / "slurm"


def prompt_template_dir() -> Path:
    return templates_root() / "prompts"
