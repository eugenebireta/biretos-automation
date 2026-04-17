"""
Collect bundle migration decisions as training data for local AI.

For each multi-variant product analyzed in insales_lot_audit, write a JSONL
record that captures:
  - input: the raw variants (lot_size, stock, price, mp_price)
  - decision: classification + bucket + chosen base + bundle prices
  - rationale: why each decision was made (from rules in audit script)

Local AI can then learn to:
  - classify new multi-variant products into uniform/scaled/mixed buckets
  - detect mp_price typos (irregular linearity)
  - propose bundle prices via the (price × 1.75 × lot + 250) formula
  - suggest base SKU = smallest lot_size

Output:
  downloads/training/bundle_classification.jsonl

Each row is one product. Idempotent — overwrites on each run.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

AUDIT_FULL = Path("downloads/insales_audit/2026-04-16/audit_full.json")
PLAN = Path("downloads/insales_audit/2026-04-16/migration_plan_pilot.json")
OUT = Path("downloads/training/bundle_classification.jsonl")

PRICE_FORMULA = "(base_per_piece_price * 1.75 * lot_size) + 250"


def main() -> int:
    if not AUDIT_FULL.exists():
        print(f"ERROR: {AUDIT_FULL} not found", file=sys.stderr)
        return 2

    audit = json.loads(AUDIT_FULL.read_text(encoding="utf-8"))
    plan_doc = json.loads(PLAN.read_text(encoding="utf-8")) if PLAN.exists() else {"plans": []}
    plan_by_pid = {p["pid"]: p for p in plan_doc.get("plans", [])}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with OUT.open("w", encoding="utf-8") as f:
        for entry in audit:
            row = {
                "task": "multi_variant_bundle_classification",
                "version": "v1",
                "collected_at": datetime.now().isoformat(),
                "source": "insales_shop_data_csv_2026_04_16",
                "input": {
                    "pid": entry["pid"],
                    "name": entry["name"],
                    "variant_count": entry["variant_count"],
                    "variants": [
                        {
                            "lot_size": v["lot_size"],
                            "stock": v["stock"],
                            "price_main": v["price"],
                            "price_marketplace": v.get("mp_price"),
                        }
                        for v in entry["variants"]
                    ],
                },
                "labels": {
                    "classification": entry["classification"],
                    "mp_linearity": entry["mp_linearity"],
                    "has_stock": entry.get("has_stock"),
                    "total_units_pieces": entry.get("total_units"),
                    "uniform_price": entry.get("uniform_price"),
                    "per_unit_price_min": entry.get("per_unit_price_min"),
                    "per_unit_price_max": entry.get("per_unit_price_max"),
                    "per_unit_price_spread": entry.get("per_unit_price_spread"),
                    "mp_per_unit_ratio": entry.get("mp_per_unit_ratio"),
                },
                "rationale": {
                    "classification_rule": _classification_rule(entry["classification"]),
                    "mp_linearity_rule": _mp_linearity_rule(entry["mp_linearity"]),
                    "stock_interpretation": "A: stock x lot_size = pieces, then sum",
                    "pricing_formula": PRICE_FORMULA,
                    "owner_confirmed": [
                        "Q1=A (stock as physical slots)",
                        "Q2=formula (price x 1.75 x lot + 250)",
                        "Q3=zero-stock migrate as is",
                        "Q7=all to Ozon",
                    ],
                },
            }
            # Attach migration_plan if owner approved this pid for pilot
            if entry["pid"] in plan_by_pid:
                p = plan_by_pid[entry["pid"]]
                row["migration_plan"] = {
                    "base_source_variant_id": p["base"]["source_variant_id"],
                    "base_per_piece_price": p["base"]["base_per_piece_price"],
                    "base_new_stock_in_pieces": p["base"]["new_stock_in_pieces"],
                    "stock_calculation": p["base"]["stock_calculation"],
                    "bundles": [
                        {
                            "lot_size": b["lot_size"],
                            "old_mp_price": b["old_mp_price"],
                            "new_mp_price_formula": b["new_mp_price_formula"],
                            "delta": b["mp_price_delta"],
                        }
                        for b in p["bundles_to_create"]
                    ],
                }
                row["migration_outcome"] = "executed_2026_04_16"
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1

    print(f"Wrote {written} training rows to {OUT}")
    print(
        f"Of which {sum(1 for r in [json.loads(line) for line in OUT.read_text(encoding='utf-8').splitlines()] if 'migration_plan' in r)} have full migration_plan/outcome"  # noqa: E501
    )
    return 0


def _classification_rule(label: str) -> str:
    return {
        "uniform_price_lots": "All variants share the same Цена. Owner's bulk-template pattern. Bundle prices derived from formula.",  # noqa: E501
        "scaled_price_lots": "Цена scales linearly with lot_size (per-unit constant ±10%). Cleanest case.",
        "truly_mixed_prices": "Per-unit price varies >10%. Variants likely encode different physical SKUs.",
        "duplicate_lot_sizes": "Two+ variants share same lot_size. Not pure lot encoding.",
        "no_lot_size": "At least one variant missing 'Единиц в одном товаре'. Cannot infer.",
        "other_mixed": "Edge case.",
    }.get(label, label)


def _mp_linearity_rule(label: str) -> str:
    return {
        "linear_discount": "Per-unit mp_price decreases as lot grows. Migration-ready.",
        "flat": "mp_price proportional to lot_size (no discount, but valid).",
        "irregular": "Per-unit mp_price increases somewhere = data-entry typo. Needs manual review.",
        "missing_mp": "One+ variants lack mp_price.",
    }.get(label, label)


if __name__ == "__main__":
    raise SystemExit(main())
