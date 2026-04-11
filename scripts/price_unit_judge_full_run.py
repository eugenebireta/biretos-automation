"""price_unit_judge_full_run.py — Run price_unit_judge on all evidence with price_contract.

Deterministic pass: no LLM calls, uses text triggers only.
Updates price_contract in evidence files with judge results.

Usage:
    python scripts/price_unit_judge_full_run.py --dry-run
    python scripts/price_unit_judge_full_run.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_scripts_dir = Path(__file__).parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from price_unit_judge import judge_price_unit_basis  # noqa: E402

EVIDENCE_DIR = Path("downloads/evidence")


def build_context_text(evidence: dict) -> str:
    """Build context text for price_unit_judge from available evidence fields.

    Sources (in order):
      1. deep_research.key_findings (list of text fragments about the product)
      2. deep_research.description_ru (full description)
      3. assembled_title (product title)
      4. dr_price_source (URL — may contain pack/lot/set in path)
      5. product_category (product type)
    """
    parts = []

    dr = evidence.get("deep_research", {})

    # key_findings — richest context
    kf = dr.get("key_findings", [])
    if isinstance(kf, list):
        parts.extend(str(item) for item in kf)
    elif kf:
        parts.append(str(kf))

    # description_ru
    desc = dr.get("description_ru", "")
    if desc:
        parts.append(desc)

    # assembled_title
    title = evidence.get("assembled_title", "")
    if title:
        parts.append(title)

    # dr_price_source URL
    source = evidence.get("dr_price_source", "")
    if source:
        parts.append(source)

    # product_category
    cat = evidence.get("product_category", "")
    if cat:
        parts.append(cat)

    return " ".join(parts)[:2000]  # cap at 2000 chars


def run(dry_run: bool = False) -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    evidence_files = sorted(EVIDENCE_DIR.glob("evidence_*.json"))
    print(f"{'[DRY RUN] ' if dry_run else ''}Scanning {len(evidence_files)} evidence files...")
    print()

    stats = {
        "total_with_price": 0,
        "no_price_contract": 0,
        "no_dr_value": 0,
        "judged_per_unit": 0,
        "judged_per_pack": 0,
        "judged_unknown": 0,
        "triggered": 0,
        "trigger_reasons": {},
        "files_modified": 0,
        "already_judged": 0,
    }
    triggered_details: list[dict] = []

    for fpath in evidence_files:
        evidence = json.loads(fpath.read_text(encoding="utf-8"))
        pn = evidence.get("pn", fpath.stem.replace("evidence_", ""))

        pc = evidence.get("price_contract")
        if not pc:
            stats["no_price_contract"] += 1
            continue

        dr_value = pc.get("dr_value")
        if dr_value is None:
            stats["no_dr_value"] += 1
            continue

        stats["total_with_price"] += 1

        # Skip already judged (idempotent)
        if pc.get("judge_status") not in ("pending", None):
            stats["already_judged"] += 1
            continue

        # Build context and judge
        context = build_context_text(evidence)
        currency = pc.get("dr_currency", "")
        brand = evidence.get("brand", "")

        result = judge_price_unit_basis(
            price=float(dr_value),
            currency=currency,
            context_text=context,
            pn=pn,
            brand=brand,
            use_llm=False,  # deterministic only
        )

        # Update price_contract
        pc["judge_status"] = "judged_deterministic"
        pc["unit_basis"] = result.unit_basis
        pc["judge_confidence"] = result.confidence
        pc["judge_triggered"] = result.triggered
        pc["judge_trigger_reason"] = result.trigger_reason or None
        pc["pack_qty"] = result.pack_qty

        # Stats
        if result.unit_basis == "per_unit":
            stats["judged_per_unit"] += 1
        elif result.unit_basis == "per_pack":
            stats["judged_per_pack"] += 1
        else:
            stats["judged_unknown"] += 1

        if result.triggered:
            stats["triggered"] += 1
            reason = result.trigger_reason
            stats["trigger_reasons"][reason] = stats["trigger_reasons"].get(reason, 0) + 1
            triggered_details.append({
                "pn": pn,
                "price": dr_value,
                "currency": currency,
                "unit_basis": result.unit_basis,
                "reason": reason,
                "pack_qty": result.pack_qty,
                "context_snippet": context[:100],
            })

        stats["files_modified"] += 1
        if not dry_run:
            fpath.write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # ── Report ──────────────────────────────────────────────────────────────
    print("=" * 60)
    print("PRICE UNIT JUDGE FULL RUN — RESULTS")
    print("=" * 60)
    print()
    print("OVERVIEW:")
    print(f"  SKUs with dr_value:     {stats['total_with_price']}")
    print(f"  Already judged:         {stats['already_judged']}")
    print(f"  No price_contract:      {stats['no_price_contract']}")
    print(f"  No dr_value:            {stats['no_dr_value']}")
    print()
    print("JUDGE RESULTS:")
    print(f"  per_unit (no trigger):  {stats['judged_per_unit']}")
    print(f"  unknown (triggered):    {stats['judged_unknown']}")
    print(f"  per_pack (triggered):   {stats['judged_per_pack']}")
    print(f"  total triggered:        {stats['triggered']}")
    print()
    if stats["trigger_reasons"]:
        print("TRIGGER BREAKDOWN:")
        for reason, cnt in sorted(stats["trigger_reasons"].items(), key=lambda x: -x[1]):
            print(f"  {reason}: {cnt}")
        print()
    if triggered_details:
        print("TRIGGERED SKUs (need review):")
        for det in triggered_details:
            print(f"  PN={det['pn']}: {det['price']} {det['currency']} "
                  f"→ {det['unit_basis']}/{det['reason']} "
                  f"pack_qty={det['pack_qty']}")
        print()
    print("FILES:")
    print(f"  modified:  {stats['files_modified']}")
    if dry_run:
        print()
        print("[DRY RUN] No files were written. Remove --dry-run to apply.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Price Unit Judge — full evidence run")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
