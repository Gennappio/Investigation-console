from __future__ import annotations

from pathlib import Path

import pytest

from lab_domain.errors import InvalidNameError, StateStoreError, TargetExistsError
from lab_domain.services.init_service import init_project
from lab_domain.services.validate_service import validate_workspace
from lab_registry.local_store import LocalRegistry

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates" / "project"


def _init(tmp_path: Path, name: str = "demo") -> tuple[Path, LocalRegistry]:
    registry = LocalRegistry(tmp_path / "lab-home")
    result = init_project(
        name=name,
        parent=tmp_path,
        registry=registry,
        template_dir=TEMPLATE_DIR,
        owner="anna.rossi",
    )
    assert result.root == str(tmp_path / name)
    return tmp_path / name, registry


def test_scaffold_contains_the_expected_files(tmp_path: Path) -> None:
    root, _ = _init(tmp_path)
    present = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    assert present == {
        ".gitignore",
        "README.md",
        "configs/smoke.yaml",
        "containers/Dockerfile",
        "experiments/EXP-000001.yaml",
        "lab.yaml",
        "src/demo/__init__.py",
        "src/demo/run.py",
        "tests/test_smoke.py",
    }
    assert (root / "results").is_dir()


def test_generated_project_validates_without_findings(tmp_path: Path) -> None:
    root, _ = _init(tmp_path)
    report = validate_workspace(root)
    assert report.errors == ()
    assert report.warnings == ()


def test_identifiers_are_allocated_and_substituted(tmp_path: Path) -> None:
    root, registry = _init(tmp_path)
    manifest = (root / "lab.yaml").read_text()
    experiment = (root / "experiments" / "EXP-000001.yaml").read_text()
    assert "project: PRJ-000001" in manifest
    assert "owners:\n    - anna.rossi" in manifest
    assert "id: EXP-000001" in experiment
    assert [record.id for record in registry.list_projects()] == ["PRJ-000001"]
    assert registry.list_projects()[0].path == str(root)


def test_hyphenated_name_becomes_a_python_package(tmp_path: Path) -> None:
    root, _ = _init(tmp_path, "tcell-calibration")
    assert (root / "src" / "tcell_calibration" / "run.py").is_file()
    assert "tcell_calibration.run" in (root / "lab.yaml").read_text()
    assert (
        "from tcell_calibration.run import main"
        in (root / "tests" / "test_smoke.py").read_text()
    )


def test_result_lists_every_created_file(tmp_path: Path) -> None:
    registry = LocalRegistry(tmp_path / "lab-home")
    result = init_project(
        name="demo",
        parent=tmp_path,
        registry=registry,
        template_dir=TEMPLATE_DIR,
        owner="anna.rossi",
    )
    assert "lab.yaml" in result.files
    assert "experiments/EXP-000001.yaml" in result.files
    assert all((tmp_path / "demo" / name).is_file() for name in result.files)


@pytest.mark.parametrize("name", ["Demo", "demo project", "-demo", "démo", ""])
def test_rejects_invalid_names(tmp_path: Path, name: str) -> None:
    with pytest.raises(InvalidNameError):
        _init(tmp_path, name)


def test_rejects_an_existing_target(tmp_path: Path) -> None:
    _init(tmp_path)
    with pytest.raises(TargetExistsError, match="already exists"):
        _init(tmp_path)


def test_reports_a_missing_template(tmp_path: Path) -> None:
    with pytest.raises(StateStoreError, match="template"):
        init_project(
            name="demo",
            parent=tmp_path,
            registry=LocalRegistry(tmp_path / "lab-home"),
            template_dir=tmp_path / "absent",
            owner="anna.rossi",
        )


def test_generated_smoke_model_runs(tmp_path: Path) -> None:
    import subprocess
    import sys

    root, _ = _init(tmp_path)
    completed = subprocess.run(
        [sys.executable, "-m", "demo.run", "--config", "configs/smoke.yaml"],
        cwd=root,
        env={"PYTHONPATH": "src", "PATH": ""},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert (root / "results" / "summary.json").is_file()
