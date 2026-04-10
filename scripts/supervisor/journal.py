from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from supervisor.manifest import ensure_state_dir


def journal_path(state_root: Path) -> Path:
    return ensure_state_dir(state_root) / "runs.jsonl"


def load_run_events(state_root: Path) -> list[dict[str, Any]]:
    path = journal_path(state_root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def append_run_event(state_root: Path, event: dict[str, Any]) -> Path:
    path = journal_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return path
