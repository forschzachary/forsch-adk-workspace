"""JSONLStore — append-only JSONL storage with env-var path resolution.

---
keywords: [storage, log, append, history, audit, jsonl, file-store, persist, record, ledger]
intention: "Saves you from re-writing the same append-then-read JSONL helper in every agent. One env-var-resolved data dir, one durable file, atomic writes."
function: "Append-only JSONL store with env-var path resolution and atomic writes."
depends_on: []
used_by: [household, email_groceries, wow_tools]
example: "store = JSONLStore('groceries.jsonl'); store.append([{'name': 'milk', 'qty': 1}])"
---
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable


class JSONLStore:
    """Append-only JSONL store.

    Path resolution:
      $FORSCH_PATTERNS_DATA_DIR / <basename_dir>  / <filename>   (if set)
      $FORSCH_ADK_WORKSPACE / data / <basename_dir> / <filename> (if set)
      ~/.local/share/forsch-patterns / <basename_dir>  / <filename> (fallback)

    Atomic writes via tmp+rename so concurrent readers never see partial lines.
    """

    def __init__(self, filename: str, *, basename_dir: str | None = None):
        self.filename = filename
        self.basename_dir = basename_dir or self._default_basename_dir()
        self.path = self._resolve_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _default_basename_dir(self) -> str:
        stem = Path(self.filename).stem
        return stem.replace(".", "_")

    def _resolve_path(self) -> Path:
        override = os.environ.get("FORSCH_PATTERNS_DATA_DIR")
        if override:
            base = Path(override).expanduser() / self.basename_dir
        else:
            workspace = os.environ.get("FORSCH_ADK_WORKSPACE")
            if workspace:
                base = Path(workspace).expanduser() / "data" / self.basename_dir
            else:
                base = Path.home() / ".local" / "share" / "forsch-patterns" / self.basename_dir
        return (base / self.filename).resolve()

    def append(self, records: Iterable[dict[str, Any]]) -> int:
        count = 0
        with self.path.open("a", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
        return count

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def write_atomic(self, records: Iterable[dict[str, Any]]) -> int:
        materialised = list(records)
        payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in materialised)
        if payload:
            payload += "\n"
        tmp_dir = self.path.parent
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=tmp_dir, delete=False, suffix=".tmp") as tmp:
            tmp.write(payload)
            tmp_path = Path(tmp.name)
        tmp_path.replace(self.path)
        return len(materialised)

    def __repr__(self) -> str:
        return f"JSONLStore(path={self.path!r}, records={len(self.read())})"
