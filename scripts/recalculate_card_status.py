"""recalculate_card_status.py — Recalculate policy_decision_v2 for all checkpoint SKUs.

Reads existing checkpoint, merges structured_identity flags into photo_result,
calls build_decision_record_v2_from_legacy_inputs() with the fixed _infer_identity_level(),
and writes updated checkpoint + before/after statistics.

Usage:
    python scripts/recalculate_card_status.py [--dry-run] [--checkpoint PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_scripts_dir = Path(__file__).parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from card_status import build_decision_record_v2_from_legacy_inputs
from confidence import (
    compute_pn_confidence,
    compute_image_confidence,
    compute_price_confidence,
    compute_card_confidence,
    confidence_label,
)

_DEFAULT_CHECKPOINT = Path(__file__).parent.parent / "downloads" / "checkpoint.json"
_SPRINT_DIR = Path(__file__).parent.parent / "research_results" / "identity_sprint"


def _load_sprint_artifacts() -> dict[str, dict]:
    """Load all sprint artifact JSON files keyed by PN (safe_pn decoded)."""
    artifacts: dict[str, dict] = {}
    if not _SPRINT_DIR.is_dir():
        return artifacts
    for f in _SPRINT_DIR.glob("*_identity.json"):
        try:
            data = json.loads(f.read_text("utf-8"))
            pn = data.get("pn")
            if pn:
                artifacts[pn] = data
        except Exception:
            pass
    return artifacts


def _build_photo_result(bundle: dict, sprint_artifacts: dict | None = None) -> dict:
    """Merge photo + structured_identity into a photo_result dict for card_status."""
    photo = dict(bundle.get("photo", {}))
    si = bundle.get("structured_identity", {})

    # Inject structured PN match flags so _infer_identity_level() can read them
    photo["exact_structured_pn_match"] = bool(si.get("exact_structured_pn_match"))
    photo["structured_pn_match_location"] = si.get("structured_pn_match_location", "")
    photo["exact_jsonld_pn_match"] = bool(si.get("exact_jsonld_pn_match"))
    photo["exact_title_pn_match"] = bool(si.get("exact_title_pn_match"))
    photo["exact_h1_pn_match"] = bool(si.get("exact_h1_pn_match"))
    photo["exact_product_context_pn_match"] = bool(si.get("exact_product_context_pn_match"))

    # Preserve externally-confirmed identity that predates structured_identity flags.
    # "confirmed" identity was set by a trusted source not stored in current flags;
    # treat it as a structured match so _infer_identity_level() returns "strong".
    existing_identity = bundle.get("policy_decision_v2", {}).get("identity_level", "")
    if existing_identity == "confirmed" and not photo["exact_structured_pn_match"]:
        photo["exact_structured_pn_match"] = True
        photo["structured_pn_match_location"] = "confirmed_legacy"

    # Inject Gemini-confirmed identity from checkpoint bundle or sprint artifact files
    pn_for_artifact = bundle.get("pn", "")
    artifact = bundle.get("identity_artifact")
    if artifact is None and sprint_artifacts and pn_for_artifact:
        artifact = sprint_artifacts.get(pn_for_artifact)
    if artifact and artifact.get("accept_for_pipeline") and artifact.get("identity_status") == "confirmed":
        if not photo["exact_structured_pn_match"]:
            photo["exact_structured_pn_match"] = True
            photo["structured_pn_match_location"] = photo.get(
                "structured_pn_match_location"
            ) or "gemini_confirmed"

    return photo


def _build_vision_verdict(bundle: dict) -> dict:
    photo = bundle.get("photo", {})
    return {"verdict": photo.get("verdict", "REJECT")}


def _build_price_result(bundle: dict) -> dict:
    price = dict(bundle.get("price", {}))
    # Owner price fallback: if no external price found but our_price_raw exists in xlsx,
    # treat as owner_price — enough for REVIEW_REQUIRED but not AUTO_PUBLISH
    price_status = price.get("price_status", "no_price_found")
    if price_status in ("no_price_found", "", None):
        our_price = bundle.get("our_price_raw", "")
        if our_price and str(our_price).strip():
            price["price_status"] = "owner_price"
            price["price_source"] = "owner_xlsx"
            price["price_confidence_note"] = "owner price from xlsx, not market validated"
    return price


def _build_datasheet_result(bundle: dict) -> dict:
    return dict(bundle.get("datasheet", {}))


def recalculate_all(
    checkpoint_path: Path = _DEFAULT_CHECKPOINT,
    dry_run: bool = False,
) -> dict:
    """Recalculate policy_decision_v2 for every SKU in checkpoint.

    Returns before/after statistics dict.
    """
    data = json.loads(checkpoint_path.read_text("utf-8"))
    sprint_artifacts = _load_sprint_artifacts()
    if sprint_artifacts:
        print(f"[INFO] Loaded {len(sprint_artifacts)} sprint artifact(s) from {_SPRINT_DIR}")

    before_v2 = Counter()
    after_v2 = Counter()
    before_identity = Counter()
    after_identity = Counter()
    changed = []

    for pn, bundle in data.items():
        pdv2_before = bundle.get("policy_decision_v2", {})
        before_v2[pdv2_before.get("card_status", "MISSING")] += 1
        before_identity[pdv2_before.get("identity_level", "unknown")] += 1

        photo_result = _build_photo_result(bundle, sprint_artifacts=sprint_artifacts)
        vision_verdict = _build_vision_verdict(bundle)
        price_result = _build_price_result(bundle)
        datasheet_result = _build_datasheet_result(bundle)

        name = bundle.get("name", "")
        assembled_title = bundle.get("assembled_title", "") or name

        try:
            new_decision = build_decision_record_v2_from_legacy_inputs(
                pn=pn,
                name=name,
                assembled_title=assembled_title,
                photo_result=photo_result,
                vision_verdict=vision_verdict,
                price_result=price_result,
                datasheet_result=datasheet_result,
            )
        except Exception as exc:
            print(f"[WARN] {pn}: build_decision failed: {exc}")
            after_v2[pdv2_before.get("card_status", "MISSING")] += 1
            after_identity[pdv2_before.get("identity_level", "unknown")] += 1
            continue

        old_status = pdv2_before.get("card_status", "MISSING")
        old_identity = pdv2_before.get("identity_level", "unknown")
        new_status = new_decision.get("card_status", "MISSING")
        new_identity = new_decision.get("identity_level", "unknown")

        after_v2[new_status] += 1
        after_identity[new_identity] += 1

        if old_status != new_status or old_identity != new_identity:
            changed.append({
                "pn": pn,
                "identity_before": old_identity,
                "identity_after": new_identity,
                "status_before": old_status,
                "status_after": new_status,
            })

        # Recalculate confidence with correct structured_pn_match_location
        try:
            source_tier = price_result.get("source_tier", "unknown")
            pn_loc = photo_result.get("structured_pn_match_location", "")
            if not pn_loc and photo_result.get("exact_structured_pn_match"):
                pn_loc = "jsonld"
            if not pn_loc:
                pn_loc = photo_result.get("pn_match_location", "")

            price_status = price_result.get("price_status", "no_price_found")
            photo_verdict = vision_verdict.get("verdict", "REJECT")

            pn_c = compute_pn_confidence(
                location=pn_loc,
                is_numeric=bool(photo_result.get("pn_match_is_numeric", False)),
                source_tier=source_tier,
                brand_cooccurrence=bool(photo_result.get("brand_cooccurrence", True)),
                brand_mismatch=bool(price_result.get("brand_mismatch")),
                category_mismatch=bool(price_result.get("category_mismatch")),
                suffix_conflict=bool(price_result.get("suffix_conflict")),
            )
            img_c = compute_image_confidence(
                source_tier=photo_result.get("source_trust_tier", source_tier),
                pn_match_confidence=pn_c,
                is_banner=False,
                is_stock_photo=bool(photo_result.get("stock_photo_flag")),
                is_tiny=(photo_result.get("width", 999) < 150 or photo_result.get("height", 999) < 150),
                jsonld_image=bool(photo_result.get("mpn_confirmed")),
                brand_mismatch=bool(price_result.get("brand_mismatch")),
                category_mismatch=bool(price_result.get("category_mismatch")),
            )
            price_c = compute_price_confidence(
                source_tier=source_tier,
                pn_match_confidence=pn_c,
                price_status=price_status,
                unit_basis=price_result.get("offer_unit_basis", "unknown"),
                brand_mismatch=bool(price_result.get("brand_mismatch")),
                category_mismatch=bool(price_result.get("category_mismatch")),
            )
            cc = compute_card_confidence(
                pn_confidence=pn_c,
                image_confidence=img_c,
                price_confidence=price_c,
                price_status=price_status,
                photo_verdict=photo_verdict,
            )
            new_confidence = {
                "pn_confidence": cc.pn_confidence,
                "image_confidence": cc.image_confidence,
                "price_confidence": cc.price_confidence,
                "overall": cc.overall,
                "overall_label": confidence_label(cc.overall),
                "publishability": cc.publishability,
                "notes": cc.notes,
            }
        except Exception as exc:
            print(f"[WARN] {pn}: confidence recalc failed: {exc}")
            new_confidence = bundle.get("confidence", {})

        if not dry_run:
            # Preserve boost signals already set by retrospective boost
            for key in ("identity_boost_signals", "identity_boost_source", "identity_boost_ts"):
                if key in pdv2_before and key not in new_decision:
                    new_decision[key] = pdv2_before[key]
            bundle["policy_decision_v2"] = new_decision
            bundle["confidence"] = new_confidence

    if not dry_run:
        checkpoint_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    stats = {
        "total": len(data),
        "changed_count": len(changed),
        "before": {
            "card_status": dict(before_v2),
            "identity_level": dict(before_identity),
        },
        "after": {
            "card_status": dict(after_v2),
            "identity_level": dict(after_identity),
        },
        "changed_sample": changed[:20],
    }
    return stats


def _print_stats(stats: dict) -> None:
    print("\n" + "=" * 60)
    print(f"Recalculate card_status - {stats['total']} SKUs")
    print(f"Changed: {stats['changed_count']}")
    print("\n" + "-" * 40)
    print("BEFORE  policy_decision_v2.card_status:")
    for k, v in sorted(stats["before"]["card_status"].items()):
        print(f"  {k:<20} {v}")
    print("\nAFTER   policy_decision_v2.card_status:")
    for k, v in sorted(stats["after"]["card_status"].items()):
        print(f"  {k:<20} {v}")
    print("\n" + "-" * 40)
    print("BEFORE  identity_level:")
    for k, v in sorted(stats["before"]["identity_level"].items()):
        print(f"  {k:<20} {v}")
    print("\nAFTER   identity_level:")
    for k, v in sorted(stats["after"]["identity_level"].items()):
        print(f"  {k:<20} {v}")

    if stats["changed_sample"]:
        print("\n" + "-" * 40)
        print("Sample changes (up to 20):")
        for c in stats["changed_sample"]:
            id_change = (
                f"{c['identity_before']} -> {c['identity_after']}"
                if c["identity_before"] != c["identity_after"]
                else c["identity_after"]
            )
            print(
                f"  {c['pn']:<20} "
                f"{c['status_before']:<14} -> {c['status_after']:<14}  "
                f"identity: {id_change}"
            )
    print("=" * 60 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Recalculate card_status for all checkpoint SKUs.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write checkpoint.")
    parser.add_argument(
        "--checkpoint",
        default=str(_DEFAULT_CHECKPOINT),
        help="Path to checkpoint.json",
    )
    args = parser.parse_args()

    cp_path = Path(args.checkpoint)
    if not cp_path.exists():
        print(f"[ERROR] Checkpoint not found: {cp_path}")
        sys.exit(1)

    stats = recalculate_all(checkpoint_path=cp_path, dry_run=args.dry_run)
    _print_stats(stats)

    if args.dry_run:
        print("[DRY RUN] Checkpoint NOT written.")
    else:
        print(f"[OK] Checkpoint written: {cp_path}")


if __name__ == "__main__":
    main()
