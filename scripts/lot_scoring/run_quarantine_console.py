from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.lot_scoring.pipeline.helpers import to_float, to_str


_DEFAULT_QUARANTINE_PATH = Path("data/quarantine/quarantine_candidates.json")
_PENDING_STATUSES = {"AUTO", "REQUIRES_REVIEW", "CRITICAL_REVIEW"}


def _load_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Quarantine file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"candidates": payload}
    if not isinstance(payload, dict):
        raise ValueError(f"Quarantine payload must be JSON object or list: {path}")
    if "candidates" not in payload:
        raise ValueError(f"Quarantine payload missing 'candidates' array: {path}")
    if not isinstance(payload["candidates"], list):
        raise ValueError(f"Quarantine payload field 'candidates' must be list: {path}")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _trim_reasoning(text: str, limit: int = 500) -> str:
    raw = to_str(text)
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 3)] + "..."


def _pending_sorted_indices(candidates: list[dict[str, Any]]) -> list[int]:
    indexed = []
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            continue
        status = to_str(item.get("status"))
        if status not in _PENDING_STATUSES:
            continue
        indexed.append((index, item))
    indexed.sort(
        key=lambda row: (
            -max(0.0, to_float(row[1].get("usd"), 0.0)),
            to_str(row[1].get("pn")),
        )
    )
    return [idx for idx, _ in indexed]


def _print_candidate(candidate: dict[str, Any]) -> None:
    print("---------------------------------")
    print(f"PN: {to_str(candidate.get('pn'))}")
    print(f"USD: {max(0.0, to_float(candidate.get('usd'), 0.0)):.6f}")
    print(f"Tier: {to_str(candidate.get('tier'))}")
    print(f"Model: {to_str(candidate.get('model_used'))}")
    print(f"Proposed category: {to_str(candidate.get('proposed_category'))}")
    print(f"Confidence: {max(0.0, min(1.0, to_float(candidate.get('confidence'), 0.0))):.6f}")
    print(f"Sanity pass: {str(bool(candidate.get('sanity_pass'))).lower()}")
    print(f"Reasoning: {_trim_reasoning(to_str(candidate.get('reasoning')))}")
    print("---------------------------------")
    print("Type:")
    print("  A = APPROVE")
    print("  R = REJECT")
    print("  S = SKIP")
    print("  Q = QUIT")


def run_quarantine_console(quarantine_path: Path) -> dict[str, int]:
    payload = _load_payload(quarantine_path)
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("Quarantine payload has invalid candidates list.")

    pending_indices = _pending_sorted_indices(candidates)
    if not pending_indices:
        summary = {"approved_count": 0, "rejected_count": 0, "remaining_pending": 0}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return summary

    for idx in pending_indices:
        candidate = candidates[idx]
        if not isinstance(candidate, dict):
            continue

        _print_candidate(candidate)
        while True:
            action = to_str(input("> ")).strip().upper()
            if action in {"A", "R", "S", "Q"}:
                break
            print("Invalid input. Use A / R / S / Q.")

        if action == "Q":
            break
        if action == "A":
            candidate["status"] = "APPROVED"
            _atomic_write_json(quarantine_path, payload)
        elif action == "R":
            candidate["status"] = "REJECTED"
            _atomic_write_json(quarantine_path, payload)
        else:
            # SKIP leaves status unchanged.
            _atomic_write_json(quarantine_path, payload)

    approved_count = 0
    rejected_count = 0
    remaining_pending = 0
    for item in candidates:
        if not isinstance(item, dict):
            continue
        status = to_str(item.get("status"))
        if status == "APPROVED":
            approved_count += 1
        elif status == "REJECTED":
            rejected_count += 1
        elif status in _PENDING_STATUSES:
            remaining_pending += 1

    summary = {
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "remaining_pending": remaining_pending,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive quarantine approval console (A/R/S/Q).")
    parser.add_argument(
        "--quarantine",
        default=str(_DEFAULT_QUARANTINE_PATH),
        help="Path to quarantine_candidates.json",
    )
    args = parser.parse_args()
    run_quarantine_console(Path(args.quarantine))


if __name__ == "__main__":
    main()
