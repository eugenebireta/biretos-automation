"""price_unit_judge_llm_pass.py — Knowledge-based judge for 42 triggered SKUs.

Instead of calling Haiku API (no key available), applies domain knowledge
from the 30-SKU benchmark and evidence analysis to resolve each triggered
SKU's unit_basis.

Each judgment has:
- unit_basis: per_unit / per_pack
- confidence: high / medium / low
- pack_qty: integer or None
- reason: human-readable explanation

Usage:
    python scripts/price_unit_judge_llm_pass.py --dry-run
    python scripts/price_unit_judge_llm_pass.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EVIDENCE_DIR = Path("downloads/evidence")

# ── Knowledge-based judgments for 42 triggered SKUs ──────────────────────────
# Built from evidence analysis: key_findings, product type, PEHA pack trap
# knowledge, and 30-SKU benchmark results.
#
# Format: pn → (unit_basis, confidence, pack_qty, reason)

JUDGMENTS: dict[str, tuple[str, str, int | None, str]] = {
    # ── PER_PACK (10 SKUs) ───────────────────────────────────────────────────
    # Evidence clearly shows multi-item packaging
    "1006186": (
        "per_pack", "high", 200,
        "kf: 'Bag of 200 pairs' — earplug refill pack",
    ),
    "1006187": (
        "per_pack", "high", None,
        "kf: 'foam earplug refill pack' — multi-pack product",
    ),
    "183791": (
        "per_pack", "high", 10,
        "PEHA NOVA frame, qty=10 detected in context. Known pack trap.",
    ),
    "189291": (
        "per_pack", "medium", None,
        "PEHA NOVA 3-gang frame, CHF 443.95 — known pack trap, "
        "unit price should be ~€40-60 range",
    ),
    "189791": (
        "per_pack", "high", 5,
        "PEHA NOVA 3-gang frame, qty=5 detected in context",
    ),
    "190991": (
        "per_pack", "medium", None,
        "PEHA NOVA 4-gang frame, CZK 18596 (~€750) — known pack trap, "
        "unit price should be ~€80-100",
    ),
    "191791": (
        "per_pack", "medium", None,
        "PEHA NOVA 4-gang frame, €425 — known pack trap, "
        "unit price should be ~€80-100",
    ),
    "704960": (
        "per_pack", "high", 10,
        "kf: 'VE=10 pcs' and 'упаковка 10 шт' — explicitly pack of 10",
    ),
    "805577": (
        "per_pack", "high", 10,
        "kf: 'pack of 10' explicitly stated in description",
    ),
    "CR-M024DC2": (
        "per_pack", "high", 10,
        "kf: 'упаковка 10 pcs' — relay pack of 10",
    ),

    # ── PER_UNIT (32 SKUs) ───────────────────────────────────────────────────
    # False positive triggers from various sources

    # Headphones / PPE — sold individually
    "1011994": (
        "per_unit", "medium", None,
        "headphones (Leightning L1N), discontinued — no pack evidence",
    ),
    "1015021": (
        "per_unit", "medium", None,
        "headphones (Leightning L1HHV), preorder — no pack evidence",
    ),

    # Industrial equipment — sold per unit, false triggers
    "121679-L3": (
        "per_unit", "medium", None,
        "aspirator MC-AS01, AUD price — trigger on quantity in context, "
        "not actual pack",
    ),
    "129464N/U": (
        "per_unit", "medium", None,
        "tube/probe, 'Open Box' triggered pack_marker — false positive",
    ),
    "129625-L3": (
        "per_unit", "medium", None,
        "kit product (title 'Набор'), not multi-pack. No distributor matches.",
    ),
    "50017460-001/U": (
        "per_unit", "medium", None,
        "Modutrol IV transformer, individual unit",
    ),
    "DPTE1000S": (
        "per_unit", "medium", None,
        "differential pressure sensor, 'Duct Kit' triggered pack_marker — "
        "kit = product type not multi-pack",
    ),
    "FX808332": (
        "per_unit", "medium", None,
        "Esser fire alarm card, 'open box' on eBay triggered 'box' — "
        "false positive",
    ),
    "MZ-PCWS77": (
        "per_unit", "high", None,
        "Experion PKS workstation (Dell Precision R7920XL), $5670 is correct "
        "per-unit price for industrial workstation",
    ),
    "PIP-003": (
        "per_unit", "medium", None,
        "pipe connector, individual unit",
    ),
    "SF00-B54": (
        "per_unit", "medium", None,
        "Honeywell Switch sensor, individual unit",
    ),
    "TRAY-3": (
        "per_unit", "medium", None,
        "splice box, individual unit — 'набор' triggered on unrelated text",
    ),

    # Cable channels — individual items
    "3240197-RU": (
        "per_unit", "medium", None,
        "cable channel, quantity in specs text is dimensions not pack",
    ),
    "3240197": (
        "per_unit", "low", None,
        "cable channel, CNY price from Chinese supplier — exotic currency, "
        "not pack",
    ),
    "3240199": (
        "per_unit", "medium", None,
        "cable channel, quantity pattern in specs is dimensions",
    ),
    "3240348": (
        "per_unit", "medium", None,
        "cable channel, quantity pattern in specs is dimensions",
    ),

    # Items where qty= is stock availability, not pack size
    "400-ATII": (
        "per_unit", "high", None,
        "HDD (Dell 400-ATII), kf: 'наличие (3 шт)' — qty=3 is stock count, "
        "not pack size",
    ),
    "EDA61K-HB-2": (
        "per_unit", "high", None,
        "Honeywell scanner charger, kf: 'доступность 9 шт' — qty=9 is stock, "
        "not pack size",
    ),

    # Exotic currency — price is per-unit on foreign sites
    "2CDG110177R0011": (
        "per_unit", "low", None,
        "ABB interface module, ARS (Argentine Peso) from local supplier",
    ),
    "788600": (
        "per_unit", "low", None,
        "ESSER housing, SAR (Saudi Riyal) from local supplier",
    ),
    "BF-HWC4-PN16-0125": (
        "per_unit", "low", None,
        "butterfly valve, KZT (Kazakh Tenge) from local supplier",
    ),
    "KD-050": (
        "per_unit", "low", None,
        "UV lamp, JPY (Japanese Yen) — exotic currency, not pack",
    ),

    # PEHA box / fuses / terminals — per_unit despite trigger
    "604411": (
        "per_unit", "medium", None,
        "PEHA Compacta junction box, €2.68 — 'коробка' in title is product "
        "type (junction box), not packaging",
    ),
    "91940-RU": (
        "per_unit", "medium", None,
        "DKC pipe, kf: 'пог.м, бухта 20 м' — price is per meter, "
        "roll is delivery format not pricing unit",
    ),
    "7910180000": (
        "per_unit", "medium", None,
        "Weidmüller terminal, kf: '$3.73/ea' confirms per-unit pricing",
    ),
    "805576": (
        "per_unit", "medium", None,
        "label/sign plate, £9.70 — 'box' triggered from unrelated text",
    ),

    # Fuses — "5X20" is physical size (5mm × 20mm), not quantity
    "FUSE-0.5A-5X20": (
        "per_unit", "high", None,
        "fuse 0.5A, '5X20' is physical size 5mm×20mm, not pack quantity",
    ),
    "FUSE-20A-5X20": (
        "per_unit", "high", None,
        "fuse 20A, '5X20' is physical size 5mm×20mm, not pack quantity",
    ),
    "FUSE-2A-5X20-RU": (
        "per_unit", "high", None,
        "fuse 2A, '5X20' is physical size 5mm×20mm, not pack quantity",
    ),
    "FUSE-6.3A-5X20": (
        "per_unit", "high", None,
        "fuse 6.3A, '5X20' is physical size 5mm×20mm, not pack quantity",
    ),

    # Mounting kits — "Комплект" is product type, not multi-pack
    "RMK400AP-IV": (
        "per_unit", "medium", None,
        "mounting kit, 'Комплект' in title is product type not multi-pack",
    ),
    "ROL15-2761-04": (
        "per_unit", "medium", None,
        "mounting kit, 'Комплект' in title is product type not multi-pack",
    ),
}


def run(dry_run: bool = False) -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    evidence_files = sorted(EVIDENCE_DIR.glob("evidence_*.json"))
    print(f"{'[DRY RUN] ' if dry_run else ''}Applying knowledge-based judgments...")
    print()

    applied = 0
    per_unit_count = 0
    per_pack_count = 0
    not_found = 0
    skipped_already = 0
    pack_details: list[dict] = []

    for fpath in evidence_files:
        evidence = json.loads(fpath.read_text(encoding="utf-8"))
        pn = evidence.get("pn", fpath.stem.replace("evidence_", ""))
        pc = evidence.get("price_contract")
        if not pc:
            continue

        # Only process triggered unknowns
        if pc.get("unit_basis") != "unknown":
            continue

        if pc.get("judge_status") == "judged_knowledge":
            skipped_already += 1
            continue

        judgment = JUDGMENTS.get(pn)
        if not judgment:
            not_found += 1
            print(f"  [WARN] No judgment for PN={pn}")
            continue

        unit_basis, confidence, pack_qty, reason = judgment

        pc["judge_status"] = "judged_knowledge"
        pc["unit_basis"] = unit_basis
        pc["judge_confidence"] = confidence
        pc["pack_qty"] = pack_qty
        pc["judge_reason"] = reason

        if unit_basis == "per_pack":
            per_pack_count += 1
            pack_details.append({
                "pn": pn,
                "dr_value": pc.get("dr_value"),
                "dr_currency": pc.get("dr_currency"),
                "pack_qty": pack_qty,
                "reason": reason,
            })
        else:
            per_unit_count += 1

        applied += 1

        if not dry_run:
            fpath.write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    print("=" * 60)
    print("KNOWLEDGE-BASED JUDGE PASS — RESULTS")
    print("=" * 60)
    print()
    print(f"  Applied:         {applied}")
    print(f"  → per_unit:      {per_unit_count}")
    print(f"  → per_pack:      {per_pack_count}")
    print(f"  Not found:       {not_found}")
    print(f"  Already judged:  {skipped_already}")
    print()
    if pack_details:
        print("CONFIRMED PACK PRICES (need unit price derivation):")
        for det in pack_details:
            qty_str = f"÷{det['pack_qty']}" if det["pack_qty"] else "qty unknown"
            print(f"  PN={det['pn']}: {det['dr_value']} {det['dr_currency']} "
                  f"({qty_str}) — {det['reason'][:60]}")
    print()

    # Final summary across ALL evidence
    total_per_unit = 0
    total_per_pack = 0
    total_unknown = 0
    total_pending = 0
    for fpath in evidence_files:
        evidence = json.loads(fpath.read_text(encoding="utf-8") if not dry_run
                              else fpath.read_text(encoding="utf-8"))
        pc = evidence.get("price_contract")
        if not pc or not pc.get("dr_value"):
            continue
        ub = pc.get("unit_basis")
        if ub == "per_unit":
            total_per_unit += 1
        elif ub == "per_pack":
            total_per_pack += 1
        elif ub == "unknown":
            total_unknown += 1
        else:
            total_pending += 1

    print("FINAL PRICE CONTRACT STATUS (all 275 priced SKUs):")
    print(f"  per_unit:   {total_per_unit}")
    print(f"  per_pack:   {total_per_pack}")
    print(f"  unknown:    {total_unknown}")
    print(f"  pending:    {total_pending}")

    if dry_run:
        print()
        print("[DRY RUN] No files were written.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Knowledge-based judge for triggered SKUs")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
