from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from build_catalog_followup_queues import compute_source_evidence_fingerprint

from supervisor import QUEUE_SCHEMA_VERSION


REQUIRED_SUMMARY_KEYS = {
    "snapshot_generated_at",
    "snapshot_id",
    "queue_schema_version",
    "source_evidence_fingerprint",
    "photo_recovery_queue_path",
    "price_followup_queue_path",
    "photo_recovery_count",
    "price_followup_count",
}


@dataclass(frozen=True)
class WorkspaceSnapshot:
    summary_path: Path
    snapshot_generated_at: str
    snapshot_id: str
    queue_schema_version: str
    source_evidence_fingerprint: str
    photo_queue_path: Path
    price_queue_path: Path
    photo_recovery_count: int
    price_followup_count: int
    source_bundle_count: int
    price_action_counts: dict[str, int] = field(default_factory=dict)

    @property
    def scout_price_count(self) -> int:
        return int(self.price_action_counts.get("scout_price", 0))

    @property
    def non_executable_price_count(self) -> int:
        return max(int(self.price_followup_count) - self.scout_price_count, 0)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        return payload
    return None


def _count_action_codes(queue_path: Path) -> dict[str, int]:
    if not queue_path.exists():
        return {}
    counts: dict[str, int] = {}
    for raw_line in queue_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            continue
        action_code = str(payload.get("action_code") or "").strip()
        if not action_code:
            continue
        counts[action_code] = counts.get(action_code, 0) + 1
    return counts


def select_latest_snapshot(
    scout_cache_dir: Path,
    *,
    required_schema_version: str = QUEUE_SCHEMA_VERSION,
) -> WorkspaceSnapshot | None:
    candidates = sorted(scout_cache_dir.glob("*followup_summary_*.json"), reverse=True)
    for path in candidates:
        payload = _load_json(path)
        if payload is None:
            continue
        if not REQUIRED_SUMMARY_KEYS.issubset(payload):
            continue
        if str(payload.get("queue_schema_version") or "").strip() != required_schema_version:
            continue
        price_queue_path = Path(str(payload["price_followup_queue_path"]))
        photo_queue_path = Path(str(payload["photo_recovery_queue_path"]))
        return WorkspaceSnapshot(
            summary_path=path,
            snapshot_generated_at=str(payload["snapshot_generated_at"]),
            snapshot_id=str(payload["snapshot_id"]),
            queue_schema_version=str(payload["queue_schema_version"]),
            source_evidence_fingerprint=str(payload["source_evidence_fingerprint"]),
            photo_queue_path=photo_queue_path,
            price_queue_path=price_queue_path,
            photo_recovery_count=int(payload["photo_recovery_count"]),
            price_followup_count=int(payload["price_followup_count"]),
            source_bundle_count=int(payload.get("source_bundle_count", 0)),
            price_action_counts=_count_action_codes(price_queue_path),
        )
    return None


def compute_active_evidence_fingerprint(evidence_dir: Path) -> str:
    return compute_source_evidence_fingerprint(evidence_dir)
