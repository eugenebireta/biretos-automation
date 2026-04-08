"""family_price_inference.py — Infer prices from sibling SKUs with suffix variants.

Honeywell PN conventions:
- PEHA: last 2 digits = color (11=white, 21=anthracite, 70=stainless)
- Security: .10/.20 = variant/color after dot
- Regional: -RU = Russian market (same base product)
- Kit: -L3 = configuration level
- Update: N/U = new/updated replacement

If PN-123-A has a price and PN-123-B is the same base product with different
suffix, we can infer the price. Result is "family_inferred" with low confidence.

Usage:
    python scripts/family_price_inference.py [--checkpoint PATH] [--apply]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

_DEFAULT_CHECKPOINT = Path(__file__).parent.parent / "downloads" / "checkpoint.json"
_EVIDENCE_DIR = Path(__file__).parent.parent / "downloads" / "evidence"

# Suffix patterns to strip for family grouping
_SUFFIX_PATTERNS = [
    # PEHA color suffixes (last 2 digits when base is 4+ chars)
    (r'^(\d{4,})(\d{2})$', 'peha_color'),
    # Honeywell Security dot-suffix: 010130.10 → 010130
    (r'^(.+?)\.(\d{1,2})$', 'dot_variant'),
    # Regional: -RU suffix
    (r'^(.+?)-RU$', 'regional_ru'),
    # Kit/config: -L3, -L2, etc.
    (r'^(.+?)-L\d$', 'kit_level'),
    # N/U replacement
    (r'^(.+?)N/U$', 'replacement_nu'),
    # Color suffix after dash: -WH, -BK, etc.
    (r'^(.+?)-(?:WH|BK|GR|BL|RD|SL)$', 'color_dash'),
]


def _extract_base_pn(pn: str) -> tuple[str, str]:
    """Extract base PN by stripping known suffixes.

    Returns (base_pn, suffix_type). If no suffix matched, returns (pn, "").
    """
    for pattern, suffix_type in _SUFFIX_PATTERNS:
        m = re.match(pattern, pn, re.IGNORECASE)
        if m:
            return m.group(1), suffix_type
    return pn, ""


def infer_family_prices(
    checkpoint_path: Path = _DEFAULT_CHECKPOINT,
    apply: bool = False,
) -> dict:
    """Infer prices from sibling SKUs.

    Returns stats dict.
    """
    cp = json.loads(checkpoint_path.read_text("utf-8"))

    # Build family groups
    families: dict[str, list[str]] = defaultdict(list)
    pn_data: dict[str, dict] = {}

    for pn, bundle in cp.items():
        base, suffix_type = _extract_base_pn(pn)
        families[base].append(pn)
        price = bundle.get("price", {})
        pn_data[pn] = {
            "base": base,
            "suffix_type": suffix_type,
            "has_ext_price": price.get("price_status") in ("public_price", "rfq_only"),
            "has_owner_price": price.get("price_status") == "owner_price",
            "price_usd": price.get("price_usd"),
            "currency": price.get("currency", ""),
            "price_status": price.get("price_status", "no_price_found"),
            "source_url": price.get("source_url", ""),
        }

    stats = Counter()
    inferred = []
    multi_member_families = 0

    for base, members in families.items():
        if len(members) < 2:
            continue
        multi_member_families += 1

        # Find members with external prices
        priced = [pn for pn in members if pn_data[pn]["has_ext_price"]]
        unpriced = [
            pn for pn in members
            if not pn_data[pn]["has_ext_price"] and not pn_data[pn]["has_owner_price"]
        ]

        if not priced or not unpriced:
            continue

        # Use first priced sibling as donor
        donor_pn = priced[0]
        donor = pn_data[donor_pn]

        for recipient_pn in unpriced:
            stats["inferred"] += 1
            inferred.append({
                "pn": recipient_pn,
                "donor_pn": donor_pn,
                "base_pn": base,
                "price_usd": donor["price_usd"],
                "currency": donor["currency"],
                "suffix_type": pn_data[recipient_pn]["suffix_type"],
            })

            if apply:
                bundle = cp[recipient_pn]
                price = bundle.get("price", {})
                price["price_status"] = "family_inferred"
                price["price_inferred_from"] = donor_pn
                price["price_usd_inferred"] = donor["price_usd"]
                price["currency_inferred"] = donor["currency"]
                price["price_confidence_note"] = (
                    f"Inferred from sibling {donor_pn} (same base PN '{base}')"
                )
                bundle["price"] = price

                # Update evidence
                safe_pn = re.sub(r'[\\/:*?"<>|]', '_', recipient_pn)
                ev_path = _EVIDENCE_DIR / f"evidence_{safe_pn}.json"
                if ev_path.exists():
                    try:
                        ev = json.loads(ev_path.read_text("utf-8"))
                        ev_price = ev.get("price", {})
                        ev_price["price_status"] = "family_inferred"
                        ev_price["price_inferred_from"] = donor_pn
                        ev_price["price_usd_inferred"] = donor["price_usd"]
                        ev_price["currency_inferred"] = donor["currency"]
                        ev["price"] = ev_price
                        ev_path.write_text(
                            json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                    except Exception:
                        pass

    # Count unpriced SKUs that are NOT in any family
    total_unpriced = sum(
        1 for pn in cp
        if not pn_data[pn]["has_ext_price"] and not pn_data[pn]["has_owner_price"]
    )
    stats["total_unpriced"] = total_unpriced

    if apply:
        checkpoint_path.write_text(
            json.dumps(cp, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {
        "total_skus": len(cp),
        "multi_member_families": multi_member_families,
        "total_unpriced_no_owner": total_unpriced,
        "inferred": stats["inferred"],
        "sample": inferred[:20],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Infer prices from sibling SKUs")
    parser.add_argument("--checkpoint", default=str(_DEFAULT_CHECKPOINT))
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    args = parser.parse_args()

    result = infer_family_prices(Path(args.checkpoint), apply=args.apply)

    print(f"\n=== Family Price Inference ===")
    print(f"  Total SKUs:           {result['total_skus']}")
    print(f"  Multi-member families:{result['multi_member_families']}")
    print(f"  Unpriced (no owner):  {result['total_unpriced_no_owner']}")
    print(f"  Inferred from sibling:{result['inferred']}")

    if result["sample"]:
        print(f"\n  Sample inferences (up to 20):")
        for s in result["sample"]:
            price_str = f"{s['currency']} {s['price_usd']}" if s['price_usd'] else "n/a"
            print(f"    {s['pn']:20s} <- {s['donor_pn']:20s} (base={s['base_pn']}, {price_str})")

    if not args.apply:
        print("\n  [DRY RUN] Use --apply to write changes.")
    else:
        print("\n  [APPLIED] Checkpoint and evidence bundles updated.")
