"""Crash-safe writes shared by the file-backed stores."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from lab_domain.errors import StateStoreError


def write_atomically(path: Path, payload: str) -> None:
    """Write ``payload`` to ``path`` so a crash never leaves it half-written."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            handle.write(payload)
            temporary = Path(handle.name)
        os.replace(temporary, path)
    except OSError as exc:
        raise StateStoreError(f"Cannot write {path}: {exc.strerror}.") from exc
