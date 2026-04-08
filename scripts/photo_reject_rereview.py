"""photo_reject_rereview.py — Re-review REJECT photos for strong identity SKUs.

For SKUs with identity=strong/confirmed + photo=REJECT:
- If structured PN match exists on the source page → mark photo_reconsider=True
- Does NOT auto-accept — only flags for reconsideration
- Updates evidence bundles with reconsider flag

Usage:
    python scripts/photo_reject_rereview.py [--checkpoint PATH] [--apply]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

_DEFAULT_CHECKPOINT = Path(__file__).parent.parent / "downloads" / "checkpoint.json"
_EVIDENCE_DIR = Path(__file__).parent.parent / "downloads" / "evidence"


def rereview_rejected_photos(
    checkpoint_path: Path = _DEFAULT_CHECKPOINT,
    apply: bool = False,
) -> dict:
    """Re-review REJECT photos for strong identity SKUs.

    Returns stats dict.
    """
    cp = json.loads(checkpoint_path.read_text("utf-8"))

    stats = Counter()
    reconsidered = []

    for pn, bundle in cp.items():
        photo = bundle.get("photo", {})
        pdv2 = bundle.get("policy_decision_v2", {})
        verdict = photo.get("verdict", "NO_PHOTO")
        identity = pdv2.get("identity_level", "weak")

        if verdict != "REJECT":
            stats["not_reject"] += 1
            continue

        stats["total_reject"] += 1

        # Check if strong identity with structured PN evidence
        has_structured = bool(
            bundle.get("structured_identity", {}).get("exact_structured_pn_match")
            or photo.get("exact_structured_pn_match")
        )
        struct_loc = (
            bundle.get("structured_identity", {}).get("structured_pn_match_location", "")
            or photo.get("structured_pn_match_location", "")
        )

        if identity in ("strong", "confirmed") and has_structured:
            stats["reconsidered"] += 1
            reconsidered.append({
                "pn": pn,
                "identity": identity,
                "structured_location": struct_loc,
                "reject_reason": photo.get("reason", ""),
            })

            if apply:
                photo["photo_reconsider"] = True
                photo["photo_reconsider_reason"] = (
                    f"strong identity ({struct_loc}) + structured PN match"
                )
                bundle["photo"] = photo

                # Also update evidence file
                safe_pn = re.sub(r'[\\/:*?"<>|]', '_', pn)
                ev_path = _EVIDENCE_DIR / f"evidence_{safe_pn}.json"
                if ev_path.exists():
                    try:
                        ev = json.loads(ev_path.read_text("utf-8"))
                        ev_photo = ev.get("photo", {})
                        ev_photo["photo_reconsider"] = True
                        ev_photo["photo_reconsider_reason"] = photo["photo_reconsider_reason"]
                        ev["photo"] = ev_photo
                        ev_path.write_text(
                            json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                    except Exception:
                        pass
        else:
            stats["kept_reject"] += 1

    if apply:
        checkpoint_path.write_text(
            json.dumps(cp, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {
        "total_reject": stats["total_reject"],
        "reconsidered": stats["reconsidered"],
        "kept_reject": stats["kept_reject"],
        "not_reject": stats["not_reject"],
        "sample": reconsidered[:15],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-review REJECT photos for strong identity SKUs")
    parser.add_argument("--checkpoint", default=str(_DEFAULT_CHECKPOINT))
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    args = parser.parse_args()

    result = rereview_rejected_photos(Path(args.checkpoint), apply=args.apply)

    print(f"\n=== Photo REJECT Re-review ===")
    print(f"  Total REJECT:    {result['total_reject']}")
    print(f"  Reconsidered:    {result['reconsidered']} (strong identity + structured PN)")
    print(f"  Kept REJECT:     {result['kept_reject']}")
    print(f"  Not REJECT:      {result['not_reject']}")

    if result["sample"]:
        print(f"\n  Sample reconsidered (up to 15):")
        for s in result["sample"]:
            print(f"    {s['pn']:20s} identity={s['identity']} loc={s['structured_location']}")

    if not args.apply:
        print("\n  [DRY RUN] Use --apply to write changes.")
    else:
        print("\n  [APPLIED] Checkpoint and evidence bundles updated.")
