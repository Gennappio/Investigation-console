"""Generate the JSON Schema files in ``schemas/`` from the manifest models.

The models are the single source of truth; the schema files are a generated
artifact for editors and external agents (see ADR 0004). Output is byte-stable
so a contract test can detect drift.

    python -m lab_domain.schema_export schemas/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from lab_domain.manifests.models import ExperimentManifest, RepositoryManifest
from lab_domain.runs import RunRecord

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

EXPORTS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("lab.schema.json", RepositoryManifest),
    ("experiment.schema.json", ExperimentManifest),
    ("run.schema.json", RunRecord),
)


def build_schema(filename: str, model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema(by_alias=True)
    return {"$schema": JSON_SCHEMA_DIALECT, "$id": filename, **schema}


def render(filename: str, model: type[BaseModel]) -> str:
    return json.dumps(build_schema(filename, model), indent=2, sort_keys=True) + "\n"


def write_schemas(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, model in EXPORTS:
        target = directory / filename
        target.write_text(render(filename, model), encoding="utf-8")
        written.append(target)
    return written


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m lab_domain.schema_export <directory>", file=sys.stderr)
        return 2
    for path in write_schemas(Path(argv[0])):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
