"""
InSales bundle migration — Stage 2: dry-run plan generator.

READ-ONLY. Reads the Stage 1 audit (audit_full.json) and a pilot pid list,
produces a JSON migration plan that says EXACTLY what will be created/modified
in InSales when Stage 3 (the API applier) runs. No API calls.

Pricing rule (owner-confirmed):
    bundle_mp_price = (Цена_per_piece × 1.75 × lot_size) + 250

Site visibility (owner-confirmed):
    Bundles are NOT sold via the website (customers use +/- on the base SKU).
    Bundles are published only to the Ozon feed via "Тип цен: маркетплейс".
    -> set published=false on bundle products.

Output:
    downloads/insales_audit/<date>/migration_plan_pilot.json
    downloads/insales_audit/<date>/migration_plan_pilot.csv  (human-readable)

Usage:
    python scripts/insales_bundle_migration_plan.py
    python scripts/insales_bundle_migration_plan.py --pids 287629100,291119233
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Owner-confirmed pricing formula: (Цена × 1.75 × lot_size) + 250
PRICE_MULTIPLIER = 1.75
PRICE_FIXED_SURCHARGE = 250.0

# Default pilot set: 5 SKUs across 3 vendors, 2 lot patterns, price 15-1290р
DEFAULT_PILOT_PIDS = [
    "287629100",  # ABB CR-PH (8 lots, 50р, 194 units) — owner's reference example
    "287631239",  # BETTERMANN RLVL 85 FS (8 lots, 1290р, 636 units) — expensive
    "306153040",  # Honeywell 023318 (8 lots, 476р, 323 units) — different vendor
    "291119233",  # ABB MCB-01 (6 lots, 600р, 26 units) — different lot pattern
    "424401468",  # Лисма СМН 6.3-20 (8 lots, 15р, 101294 units) — high volume
]


def compute_bundle_price(base_per_piece_price: float, lot_size: int) -> float:
    """Owner's bundle pricing formula for the Ozon marketplace price column."""
    return round(base_per_piece_price * PRICE_MULTIPLIER * lot_size + PRICE_FIXED_SURCHARGE, 2)


def build_plan_for_product(audit_entry: dict) -> dict:
    """
    Convert one audit entry into a concrete migration plan.

    Picks the variant with the smallest lot_size as the BASE (which holds
    real stock in piece units after migration). All other variants become
    BUNDLES that consume from the base.
    """
    pid = audit_entry["pid"]
    name = audit_entry["name"]
    variants = audit_entry["variants"]

    # Sort variants by lot_size ascending; smallest lot becomes base
    sorted_variants = sorted(variants, key=lambda v: v["lot_size"] or 99999)
    base_v = sorted_variants[0]
    bundle_variants = sorted_variants[1:]

    # Per-piece price = "Цена" of the base variant (owner: "берешь цену за 1 шт из Цена")
    base_per_piece_price = base_v["price"]

    # Total stock in pieces = Σ stock × lot_size across ALL original variants
    # (interpretation A: each variant is a physical slot on the shelf)
    total_units = sum((v["stock"] or 0) * (v["lot_size"] or 0) for v in variants)

    plan = {
        "pid": pid,
        "name": name,
        "audit_classification": audit_entry["classification"],
        "audit_mp_linearity": audit_entry["mp_linearity"],
        "base": {
            "source_variant_id": base_v["variant_id"],
            "source_article": base_v["article"],
            "source_lot_size": base_v["lot_size"],
            "base_per_piece_price": base_per_piece_price,
            "new_stock_in_pieces": total_units,
            "stock_calculation": " + ".join(f"{v['stock'] or 0}×{v['lot_size']}" for v in variants),
            "action": "update_variant: set stock = total_units; keep variant; remove all other variants from this product",  # noqa: E501
        },
        "bundles_to_create": [],
        "variants_to_destroy_after_bundles": [v["variant_id"] for v in bundle_variants],
    }

    for v in bundle_variants:
        bundle_mp = compute_bundle_price(base_per_piece_price, v["lot_size"])
        old_mp = v.get("mp_price")
        plan["bundles_to_create"].append(
            {
                "lot_size": v["lot_size"],
                "consumes_from_base_variant_id": base_v["variant_id"],
                "consumes_quantity": v["lot_size"],
                "old_variant_id": v["variant_id"],
                "old_article": v["article"],
                "old_external_id": v["external_id"],
                "new_bundle_sku": v["article"],  # preserve old SKU for external references
                "new_bundle_name": f"{name} (комплект {v['lot_size']} шт)",
                "new_mp_price_formula": bundle_mp,
                "old_mp_price": old_mp,
                "mp_price_delta": round(bundle_mp - old_mp, 2) if old_mp else None,
                "stock_to_initialize": 0,  # bundle has no own stock — drains from base
                "published_on_site": False,  # owner: site uses +/- on base SKU only
            }
        )

    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--audit",
        default="downloads/insales_audit",
        help="Path to insales_audit dir (uses latest dated subfolder)",
    )
    ap.add_argument(
        "--pids",
        default=",".join(DEFAULT_PILOT_PIDS),
        help="Comma-separated pid list to plan for (default: pilot 5)",
    )
    ap.add_argument(
        "--all-ready",
        action="store_true",
        help="Plan for ALL audit entries that are migration-ready "
        "(uniform_price_lots × linear_discount/flat × has_stock). Overrides --pids.",
    )
    ap.add_argument(
        "--out",
        default="migration_plan_pilot.json",
        help="Output filename (default: migration_plan_pilot.json)",
    )
    args = ap.parse_args()

    audit_root = Path(args.audit)
    if not audit_root.exists():
        print(f"ERROR: audit dir not found: {audit_root}", file=sys.stderr)
        return 2

    # Pick latest dated subfolder
    dated = sorted(d for d in audit_root.iterdir() if d.is_dir())
    if not dated:
        print(f"ERROR: no dated subfolders in {audit_root}", file=sys.stderr)
        return 2
    audit_dir = dated[-1]
    audit_full = audit_dir / "audit_full.json"
    if not audit_full.exists():
        print(f"ERROR: {audit_full} not found — run insales_lot_audit.py first", file=sys.stderr)
        return 2

    print(f"Reading {audit_full}")
    audit_data = json.loads(audit_full.read_text(encoding="utf-8"))
    by_pid = {c["pid"]: c for c in audit_data}

    if args.all_ready:
        pids = [
            c["pid"]
            for c in audit_data
            if c["classification"] == "uniform_price_lots"
            and c["mp_linearity"] in ("linear_discount", "flat")
            and c.get("has_stock")
        ]
        print(f"--all-ready: planning for {len(pids)} migration-ready pids")
    else:
        pids = [p.strip() for p in args.pids.split(",") if p.strip()]
        print(f"Planning for {len(pids)} pid(s)")

    plans = []
    skipped = []
    for pid in pids:
        if pid not in by_pid:
            skipped.append((pid, "not in audit (single-variant or absent)"))
            continue
        entry = by_pid[pid]
        if entry["classification"] != "uniform_price_lots":
            skipped.append((pid, f"classification={entry['classification']} — not in pilot scope"))
            continue
        if entry["mp_linearity"] not in ("linear_discount", "flat"):
            skipped.append((pid, f"mp_linearity={entry['mp_linearity']} — needs review first"))
            continue
        plans.append(build_plan_for_product(entry))

    if skipped:
        print("\nSKIPPED:")
        for pid, reason in skipped:
            print(f"  {pid}: {reason}")

    # Write JSON plan
    plan_json = audit_dir / args.out
    plan_json.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(),
                "pricing_formula": f"bundle_mp_price = (base_per_piece_price × {PRICE_MULTIPLIER} × lot_size) + {PRICE_FIXED_SURCHARGE}",  # noqa: E501
                "site_visibility": "bundles published=false (Ozon feed only; site uses +/- on base SKU)",
                "stock_interpretation": "A: stock × lot_size = pieces, then sum -> base.new_stock_in_pieces",
                "plans": plans,
                "skipped": skipped,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n  JSON plan: {plan_json}")

    # Write human-readable CSV (one row per action)
    plan_csv = audit_dir / (args.out.replace(".json", ".csv"))
    with plan_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "pid",
                "name",
                "action",
                "lot_size",
                "stock_after",
                "mp_price_after",
                "mp_price_before",
                "mp_price_delta",
                "source_variant_id",
                "sku",
                "published_on_site",
            ]
        )
        for p in plans:
            base = p["base"]
            w.writerow(
                [
                    p["pid"],
                    p["name"][:60],
                    "BASE: keep+update_stock",
                    base["source_lot_size"],
                    base["new_stock_in_pieces"],
                    "",
                    "",
                    "",
                    base["source_variant_id"],
                    base["source_article"],
                    "true",
                ]
            )
            for b in p["bundles_to_create"]:
                w.writerow(
                    [
                        p["pid"],
                        p["name"][:60],
                        "BUNDLE: create",
                        b["lot_size"],
                        0,
                        b["new_mp_price_formula"],
                        b["old_mp_price"],
                        b["mp_price_delta"],
                        b["consumes_from_base_variant_id"],
                        b["new_bundle_sku"],
                        "false",
                    ]
                )
            for vid in p["variants_to_destroy_after_bundles"]:
                w.writerow(
                    [
                        p["pid"],
                        p["name"][:60],
                        "DESTROY: old_variant",
                        "",
                        "",
                        "",
                        "",
                        "",
                        vid,
                        "",
                        "",
                    ]
                )
    print(f"  CSV plan:  {plan_csv}")

    # Print summary
    print(f"\nDone. {len(plans)} migration plan(s), {len(skipped)} skipped.")
    print("\nSummary per pid:")
    for p in plans:
        n_bundles = len(p["bundles_to_create"])
        print(f"  {p['pid']}  base_stock={p['base']['new_stock_in_pieces']:>6}  bundles={n_bundles}  {p['name'][:55]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
