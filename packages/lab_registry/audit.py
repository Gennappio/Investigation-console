"""Append-only audit log of significant actions (AGENTS.md section 15.4)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AUDIT_FILENAME = "audit.jsonl"


class AuditLog:
    """One JSON object per line, appended, never rewritten."""

    def __init__(self, home: Path) -> None:
        self._path = home / AUDIT_FILENAME

    @property
    def path(self) -> Path:
        return self._path

    def record(self, action: str, actor: str, **context: Any) -> None:
        entry = {
            "at": datetime.now(UTC).isoformat(),
            "action": action,
            "actor": actor,
            **{key: str(value) for key, value in context.items() if value is not None},
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def entries(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]
