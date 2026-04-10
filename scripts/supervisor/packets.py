from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from supervisor.manifest import ensure_state_dir


def packets_path(state_root: Path) -> Path:
    return ensure_state_dir(state_root) / "packets.jsonl"


def load_packet_events(state_root: Path) -> list[dict[str, Any]]:
    path = packets_path(state_root)
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


def append_packet_event(state_root: Path, event: dict[str, Any]) -> Path:
    path = packets_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return path


def reduce_packet_state(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for event in events:
        packet_id = str(event.get("packet_id") or "").strip()
        if not packet_id:
            continue
        current = dict(state.get(packet_id) or {})
        current.update(event)
        state[packet_id] = current
    return state


def load_packet_states(state_root: Path) -> dict[str, dict[str, Any]]:
    return reduce_packet_state(load_packet_events(state_root))


def find_packet_by_idempotency_key(
    packet_states: dict[str, dict[str, Any]],
    idempotency_key: str,
) -> dict[str, Any] | None:
    for packet in packet_states.values():
        if str(packet.get("idempotency_key") or "").strip() == idempotency_key:
            return packet
    return None
