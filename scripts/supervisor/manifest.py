from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST: dict[str, Any] = {
    "status": "ready",
    "write_phase": "terminal",
    "awaiting_owner_reply": False,
    "pending_packet_id": None,
    "pending_packet_type": None,
    "decision_deadline_at": None,
    "default_option_id": None,
    "default_applied_at": None,
    "next_actions": {},
    "last_action": None,
    "last_rule": None,
    "last_dispatch_id": None,
    "last_evidence_fingerprint": "",
    "post_refresh_fingerprint": "",
    "refresh_generation": 0,
    "last_rebuild_generation": 0,
    "rerun_intent_id": None,
    "result_kind": "",
}


def ensure_state_dir(state_root: Path) -> Path:
    state_root.mkdir(parents=True, exist_ok=True)
    return state_root


def manifest_path(state_root: Path) -> Path:
    return ensure_state_dir(state_root) / "manifest.json"


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def load_manifest(state_root: Path) -> dict[str, Any]:
    path = manifest_path(state_root)
    if not path.exists():
        return dict(DEFAULT_MANIFEST)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return dict(DEFAULT_MANIFEST)
    merged = dict(DEFAULT_MANIFEST)
    merged.update(payload)
    return merged


def write_manifest(state_root: Path, payload: dict[str, Any]) -> Path:
    path = manifest_path(state_root)
    atomic_write_json(path, payload)
    return path
