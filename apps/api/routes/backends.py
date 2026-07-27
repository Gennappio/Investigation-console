"""Which execution backends this installation offers."""

from __future__ import annotations

from fastapi import APIRouter

from lab_cli.runtime import BACKENDS

router = APIRouter(prefix="/execution-backends", tags=["execution"])


@router.get("")
def list_backends() -> dict[str, object]:
    return {
        "count": len(BACKENDS),
        "results": [
            {
                "name": name,
                "submits": "immediately" if name == "local" else "through a scheduler",
            }
            for name in BACKENDS
        ],
    }
