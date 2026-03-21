from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.lot_scoring.category_engine import VALID_CATEGORIES
from scripts.lot_scoring.pipeline.helpers import normalize_category_key, to_float, to_str


_DEFAULT_QUARANTINE_PATH = Path("data/quarantine/quarantine_candidates.json")
_DEFAULT_SKU_LOOKUP_PATH = Path("scripts/lot_scoring/data/sku_lookup.json")
_DEFAULT_REPORT_PATH = Path("audits/quarantine_merge_report.json")
_LOOKUP_ALLOWED_CATEGORIES: frozenset[str] = frozenset(VALID_CATEGORIES - {"toxic_fake", "unknown"})


def _normalize_pn(value: object) -> str:
    text = to_str(value).upper().replace(" ", "").replace("-", "")
    return "".join(ch for ch in text if ch.isalnum())


def _load_quarantine_candidates(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Quarantine file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw: list[Any] = []
    if isinstance(payload, dict):
        raw = payload.get("candidates", [])
    elif isinstance(payload, list):
        raw = payload
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for row in raw:
        if isinstance(row, dict):
            result.append(dict(row))
    return result


def _load_sku_lookup(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"sku_lookup must be a JSON object: {path}")
    result: dict[str, str] = {}
    for key, value in payload.items():
        pn = _normalize_pn(key)
        category = normalize_category_key(value)
        if pn and category in _LOOKUP_ALLOWED_CATEGORIES:
            result[pn] = category
    return result


def merge_quarantine(
    *,
    quarantine_path: Path,
    sku_lookup_path: Path,
    report_path: Path,
    overwrite_existing: bool,
) -> dict[str, Any]:
    candidates = _load_quarantine_candidates(quarantine_path)
    lookup_before = _load_sku_lookup(sku_lookup_path)
    lookup_after = dict(lookup_before)

    stats = {
        "total_candidates": len(candidates),
        "approved_candidates": 0,
        "added": 0,
        "updated": 0,
        "skipped_status": 0,
        "skipped_invalid": 0,
        "skipped_same": 0,
        "skipped_conflict": 0,
    }
    changes: list[dict[str, Any]] = []

    ordered = sorted(
        candidates,
        key=lambda row: (
            -to_float(row.get("usd"), 0.0),
            _normalize_pn(row.get("pn")),
        ),
    )
    for row in ordered:
        status = to_str(row.get("status"))
        if status != "APPROVED":
            stats["skipped_status"] += 1
            continue
        stats["approved_candidates"] += 1
        pn = _normalize_pn(row.get("pn"))
        category = normalize_category_key(row.get("proposed_category"))
        if not pn or category not in _LOOKUP_ALLOWED_CATEGORIES:
            stats["skipped_invalid"] += 1
            continue

        current = lookup_after.get(pn)
        if current is None:
            lookup_after[pn] = category
            stats["added"] += 1
            changes.append({"pn": pn, "action": "added", "old_category": "", "new_category": category})
            continue
        if current == category:
            stats["skipped_same"] += 1
            continue
        if overwrite_existing:
            lookup_after[pn] = category
            stats["updated"] += 1
            changes.append({"pn": pn, "action": "updated", "old_category": current, "new_category": category})
        else:
            stats["skipped_conflict"] += 1

    wrote_lookup = stats["added"] > 0 or stats["updated"] > 0
    if wrote_lookup:
        sku_lookup_path.parent.mkdir(parents=True, exist_ok=True)
        ordered_lookup = {pn: lookup_after[pn] for pn in sorted(lookup_after.keys())}
        sku_lookup_path.write_text(json.dumps(ordered_lookup, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "quarantine_path": str(quarantine_path),
        "sku_lookup_path": str(sku_lookup_path),
        "overwrite_existing": bool(overwrite_existing),
        "stats": stats,
        "wrote_sku_lookup": wrote_lookup,
        "changes": sorted(changes, key=lambda row: row["pn"]),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge APPROVED quarantine candidates into sku_lookup.json.")
    parser.add_argument(
        "--quarantine",
        default=str(_DEFAULT_QUARANTINE_PATH),
        help="Path to quarantine_candidates.json.",
    )
    parser.add_argument(
        "--sku-lookup",
        default=str(_DEFAULT_SKU_LOOKUP_PATH),
        help="Path to sku_lookup.json.",
    )
    parser.add_argument(
        "--report",
        default=str(_DEFAULT_REPORT_PATH),
        help="Path to merge report json.",
    )
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Allow overwriting existing sku_lookup category with approved quarantine value.",
    )
    args = parser.parse_args()

    report = merge_quarantine(
        quarantine_path=Path(args.quarantine),
        sku_lookup_path=Path(args.sku_lookup),
        report_path=Path(args.report),
        overwrite_existing=bool(args.overwrite_existing),
    )
    print("===QUARANTINE_MERGE_SUMMARY_START===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("===QUARANTINE_MERGE_SUMMARY_END===")


if __name__ == "__main__":
    main()
