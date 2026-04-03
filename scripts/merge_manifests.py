"""Deterministic merge of first-pass and second-pass price scout manifests.

Merge rule: for each (part_number, source_domain) pair, second-pass wins if:
  - second-pass has lineage_confirmed=True AND first-pass does not
  - OR second-pass has price AND first-pass does not
  - OR second-pass has higher price_confidence

If both have same lineage/price status, first-pass is kept (conservative).

New second-pass records (URLs not in first-pass) are always appended.

Committed merged output strips run-scoped Browser Vision/CDP metadata so the
versioned artifact stays deterministic. Raw runtime provenance remains in the
runtime second-pass manifest/evidence layer.

Usage:
    python merge_manifests.py \
        --first-pass downloads/scout_cache/price_manual_manifest_target20.jsonl \
        --second-pass downloads/scout_cache/bvs_25sku_manifest.jsonl \
        --output downloads/scout_cache/merged_manifest.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


VOLATILE_OUTPUT_FIELDS = {
    "blocked_ui_detected",
    "browser_channel",
    "browser_mode",
    "browser_vision_source",
    "escalated_to_opus",
    "final_url",
    "idempotency_key",
    "page_title",
    "screenshot_path",
    "screenshot_taken",
    "trace_id",
    "vision_confidence",
    "vision_model",
}


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except json.JSONDecodeError:
            continue
    return rows


def _row_key(row: dict[str, Any]) -> str:
    """Composite key: part_number + source_domain."""
    pn = str(row.get("part_number", "")).strip()
    domain = str(row.get("source_domain", "")).strip()
    return f"{pn}::{domain}"


def _second_pass_wins(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """Return True if second-pass record should replace first-pass."""
    f_lineage = bool(first.get("price_source_exact_product_lineage_confirmed"))
    s_lineage = bool(second.get("price_source_exact_product_lineage_confirmed"))

    # Second-pass has lineage, first doesn't → win
    if s_lineage and not f_lineage:
        return True

    # Second-pass has price, first doesn't → win
    f_price = first.get("price_per_unit")
    s_price = second.get("price_per_unit")
    if s_price is not None and f_price is None:
        return True

    # Both have lineage, second has higher confidence → win
    if s_lineage and f_lineage:
        s_conf = int(second.get("price_confidence") or 0)
        f_conf = int(first.get("price_confidence") or 0)
        if s_conf > f_conf:
            return True

    return False


def _sanitize_output_row(row: dict[str, Any]) -> dict[str, Any]:
    """Drop run-scoped Browser Vision/CDP metadata from committed output."""
    sanitized = dict(row)
    for field in VOLATILE_OUTPUT_FIELDS:
        sanitized.pop(field, None)
    return sanitized


def merge(
    first_pass: list[dict[str, Any]],
    second_pass: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge first-pass and second-pass manifests.

    Returns merged list. Order: first-pass rows (possibly replaced), then
    any second-pass rows with new keys appended at end.
    """
    # Index first-pass by key
    first_by_key: dict[str, dict[str, Any]] = {}
    first_order: list[str] = []
    for row in first_pass:
        key = _row_key(row)
        first_by_key[key] = row
        first_order.append(key)

    # Process second-pass
    replacements: dict[str, dict[str, Any]] = {}
    new_rows: list[dict[str, Any]] = []
    stats = {"replaced": 0, "kept_first": 0, "appended": 0, "second_blocked": 0}

    for row in second_pass:
        key = _row_key(row)

        # Skip second-pass blocked_ui records that have no useful data
        if (
            row.get("blocked_ui_detected")
            and not row.get("price_source_exact_product_lineage_confirmed")
        ):
            stats["second_blocked"] += 1
            continue

        if key in first_by_key:
            if _second_pass_wins(first_by_key[key], row):
                replacement = _sanitize_output_row(row)
                replacement["merge_source"] = "second_pass_replaced"
                replacements[key] = replacement
                stats["replaced"] += 1
            else:
                stats["kept_first"] += 1
        else:
            new_row = _sanitize_output_row(row)
            new_row["merge_source"] = "second_pass_new"
            new_rows.append(new_row)
            stats["appended"] += 1

    # Build merged result
    merged: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for key in first_order:
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if key in replacements:
            merged.append(replacements[key])
        else:
            row = _sanitize_output_row(first_by_key[key])
            row["merge_source"] = "first_pass"
            merged.append(row)

    for row in new_rows:
        key = _row_key(row)
        if key not in seen_keys:
            seen_keys.add(key)
            merged.append(row)

    return merged, stats


def run(
    first_pass_path: Path,
    second_pass_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    first_pass = _load_manifest(first_pass_path)
    second_pass = _load_manifest(second_pass_path)

    merged, stats = merge(first_pass, second_pass)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        for row in merged:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    stats["first_pass_count"] = len(first_pass)
    stats["second_pass_count"] = len(second_pass)
    stats["merged_count"] = len(merged)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic merge of first-pass and second-pass manifests.",
    )
    parser.add_argument("--first-pass", required=True, help="First-pass manifest JSONL")
    parser.add_argument("--second-pass", required=True, help="Second-pass manifest JSONL")
    parser.add_argument("--output", required=True, help="Output merged manifest JSONL")
    args = parser.parse_args()

    stats = run(Path(args.first_pass), Path(args.second_pass), Path(args.output))

    print(f"first_pass={stats['first_pass_count']} "
          f"second_pass={stats['second_pass_count']} "
          f"merged={stats['merged_count']}")
    print(f"replaced={stats['replaced']} "
          f"kept_first={stats['kept_first']} "
          f"appended={stats['appended']} "
          f"second_blocked={stats['second_blocked']}")


if __name__ == "__main__":
    main()
