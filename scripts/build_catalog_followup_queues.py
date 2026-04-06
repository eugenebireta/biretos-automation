"""Build operational follow-up queues from refreshed local evidence bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from price_admissibility import materialize_price_admissibility


ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
DEFAULT_EVIDENCE_DIR = DOWNLOADS / "evidence"
DEFAULT_OUTPUT_DIR = DOWNLOADS / "scout_cache"
QUEUE_SCHEMA_VERSION = "followup_queue_v2"
PHOTO_RECOVERY_ACTION_CODE = "photo_recovery"
PRICE_SCOUT_ACTION_CODE = "scout_price"
BLOCKED_OWNER_REVIEW_ACTION_CODE = "blocked_owner_review"
STALE_TRUTH_RECONCILE_ACTION_CODE = "stale_truth_reconcile"
ADMISSIBILITY_REVIEW_ACTION_CODE = "admissibility_review"


def _load_bundle(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def iter_bundles(evidence_dir: Path) -> list[dict[str, Any]]:
    bundles: list[dict[str, Any]] = []
    for path in sorted(evidence_dir.glob("evidence_*.json")):
        payload = _load_bundle(path)
        if isinstance(payload, dict) and payload.get("pn"):
            bundles.append(payload)
    return bundles


def compute_source_evidence_fingerprint(evidence_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(evidence_dir.glob("evidence_*.json")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def build_snapshot_id(*, timestamp_token: str, source_evidence_fingerprint: str) -> str:
    return f"snap_{timestamp_token}_{source_evidence_fingerprint.removeprefix('sha256:')[:12]}"


def build_photo_recovery_row(bundle: dict[str, Any], *, snapshot_id: str) -> dict[str, Any]:
    content = bundle.get("content", {})
    price = bundle.get("price", {})
    pn = bundle.get("pn", "")
    return {
        "pn": pn,
        "part_number": bundle.get("pn", ""),
        "product_name": bundle.get("name", ""),
        "brand": bundle.get("brand", ""),
        "snapshot_id": snapshot_id,
        "queue_schema_version": QUEUE_SCHEMA_VERSION,
        "action_code": PHOTO_RECOVERY_ACTION_CODE,
        "card_status": bundle.get("card_status", ""),
        "photo_verdict": bundle.get("photo", {}).get("verdict", ""),
        "photo_verdict_reason": bundle.get("photo", {}).get("verdict_reason", ""),
        "current_image_status": bundle.get("merchandising", {}).get("image_status", "") or bundle.get("photo", {}).get("photo_status", ""),
        "current_image_local_path": bundle.get("merchandising", {}).get("image_local_path", ""),
        "site_placement": content.get("site_placement", ""),
        "product_type": content.get("product_type", ""),
        "description_source": content.get("description_source", ""),
        "price_status": price.get("price_status", ""),
        "price_source_url": price.get("source_url", ""),
        "suggested_action": "find_replacement_photo_from_trusted_source",
    }


def _materialized_price_view(bundle: dict[str, Any]) -> dict[str, Any]:
    price = dict(bundle.get("price", {}) or {})
    historical_state_price_status = str(
        price.get("historical_state_price_status", "")
        or bundle.get("historical_state_price_status", "")
        or bundle.get("state_price_status", "")
        or ""
    ).strip()
    queue_price_status = str(price.get("queue_price_status", "") or "").strip()
    materialized = materialize_price_admissibility(
        price,
        queue_price_status=queue_price_status,
        historical_state_price_status=historical_state_price_status,
    )
    return materialized


def _has_explicit_admissibility(price: dict[str, Any]) -> bool:
    return bool(
        str(price.get("price_admissibility_schema_version", "") or "").strip()
        or str(price.get("offer_admissibility_status", "") or "").strip()
    )


def _price_followup_action_payload(price: dict[str, Any]) -> tuple[str, str]:
    staleness = str(price.get("staleness_or_conflict_status", "") or "").strip()
    offer = str(price.get("offer_admissibility_status", "") or "").strip()
    review_bucket = str(price.get("price_admissibility_review_bucket", "") or "").strip()
    reason_codes = {str(code).strip() for code in price.get("price_admissibility_reason_codes", []) or [] if str(code).strip()}
    if staleness in {"stale_historical_claim", "state_manifest_conflict", "queue_manifest_conflict"}:
        return STALE_TRUTH_RECONCILE_ACTION_CODE, "reconcile_stale_truth_before_followup"
    if staleness == "unresolved_conflict":
        if offer == "admissible_public_price":
            return ADMISSIBILITY_REVIEW_ACTION_CODE, "review_admissible_price_with_surface_conflict"
        if offer == "blocked_or_auth_gated":
            return BLOCKED_OWNER_REVIEW_ACTION_CODE, "confirm_blocked_surface_or_owner_review"
        return STALE_TRUTH_RECONCILE_ACTION_CODE, "reconcile_stale_truth_before_followup"
    if offer == "blocked_or_auth_gated":
        return BLOCKED_OWNER_REVIEW_ACTION_CODE, "confirm_blocked_surface_or_owner_review"
    if review_bucket == "PRICE_ADMISSIBILITY_REVIEW" or reason_codes.intersection(
        {
            "PRICE_COMPONENT_OR_ACCESSORY",
            "PRICE_PACK_UNIT_AMBIGUITY",
            "PRICE_FAMILY_SERIES_ONLY",
            "PRICE_SEMANTIC_IDENTITY_MISMATCH",
        }
    ):
        return ADMISSIBILITY_REVIEW_ACTION_CODE, "review_ambiguous_offer_for_admissibility"
    if offer == "ambiguous_offer":
        return ADMISSIBILITY_REVIEW_ACTION_CODE, "review_ambiguous_offer_for_admissibility"
    if offer == "reference_price":
        return ADMISSIBILITY_REVIEW_ACTION_CODE, "review_reference_price_for_public_admissibility"
    return PRICE_SCOUT_ACTION_CODE, "find_admissible_price_source_or_confirm_no_price"


def build_price_followup_row(bundle: dict[str, Any], *, snapshot_id: str) -> dict[str, Any]:
    content = bundle.get("content", {})
    price = _materialized_price_view(bundle)
    action_code, suggested_action = _price_followup_action_payload(price)
    pn = bundle.get("pn", "")
    return {
        "pn": pn,
        "part_number": bundle.get("pn", ""),
        "product_name": bundle.get("name", ""),
        "brand": bundle.get("brand", ""),
        "snapshot_id": snapshot_id,
        "queue_schema_version": QUEUE_SCHEMA_VERSION,
        "action_code": action_code,
        "card_status": bundle.get("card_status", ""),
        "price_status": price.get("price_status", ""),
        "offer_admissibility_status": price.get("offer_admissibility_status", ""),
        "string_lineage_status": price.get("string_lineage_status", ""),
        "commercial_identity_status": price.get("commercial_identity_status", ""),
        "staleness_or_conflict_status": price.get("staleness_or_conflict_status", ""),
        "price_admissibility_reason_codes": list(price.get("price_admissibility_reason_codes", [])),
        "price_admissibility_review_bucket": price.get("price_admissibility_review_bucket", ""),
        "price_source_url": price.get("source_url", ""),
        "currency": price.get("currency", ""),
        "rub_price": price.get("rub_price"),
        "stock_status": price.get("stock_status", ""),
        "category_mismatch": bool(price.get("category_mismatch")),
        "site_placement": content.get("site_placement", ""),
        "product_type": content.get("product_type", ""),
        "suggested_action": suggested_action,
    }


def run(
    *,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    prefix: str = "",
) -> dict[str, Any]:
    bundles = iter_bundles(evidence_dir)
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    generated_at = now.isoformat().replace("+00:00", "Z")
    source_evidence_fingerprint = compute_source_evidence_fingerprint(evidence_dir)
    snapshot_id = build_snapshot_id(
        timestamp_token=ts,
        source_evidence_fingerprint=source_evidence_fingerprint,
    )
    photo_queue = [
        build_photo_recovery_row(bundle, snapshot_id=snapshot_id)
        for bundle in bundles
        if str(bundle.get("photo", {}).get("verdict", "") or "").strip().upper() == "REJECT"
    ]
    price_queue: list[dict[str, Any]] = []
    for bundle in bundles:
        raw_price = dict(bundle.get("price", {}) or {})
        if _has_explicit_admissibility(raw_price):
            price = _materialized_price_view(bundle)
            if (
                str(price.get("offer_admissibility_status", "") or "").strip() == "admissible_public_price"
                and str(price.get("staleness_or_conflict_status", "") or "").strip() == "clean"
            ):
                continue
            price_queue.append(build_price_followup_row({**bundle, "price": price}, snapshot_id=snapshot_id))
            continue

        if str(raw_price.get("price_status", "") or "").strip() not in {
            "no_price_found",
            "ambiguous_offer",
            "category_mismatch_only",
        }:
            continue
        price_queue.append(build_price_followup_row(bundle, snapshot_id=snapshot_id))

    prefix_part = f"{prefix}_" if prefix else ""
    photo_path = output_dir / f"{prefix_part}photo_recovery_queue_{ts}.jsonl"
    price_path = output_dir / f"{prefix_part}price_followup_queue_{ts}.jsonl"
    summary_path = output_dir / f"{prefix_part}followup_summary_{ts}.json"

    _write_jsonl(photo_path, photo_queue)
    _write_jsonl(price_path, price_queue)

    summary = {
        "generated_at": generated_at,
        "snapshot_generated_at": generated_at,
        "snapshot_id": snapshot_id,
        "queue_schema_version": QUEUE_SCHEMA_VERSION,
        "source_evidence_fingerprint": source_evidence_fingerprint,
        "source_evidence_dir": str(evidence_dir),
        "photo_recovery_queue": str(photo_path),
        "photo_recovery_queue_path": str(photo_path),
        "price_followup_queue": str(price_path),
        "price_followup_queue_path": str(price_path),
        "photo_recovery_count": len(photo_queue),
        "price_followup_count": len(price_queue),
        "source_bundle_count": len(bundles),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build photo/price follow-up queues from refreshed evidence bundles.")
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--prefix", default="")
    args = parser.parse_args()

    summary = run(
        evidence_dir=Path(args.evidence_dir),
        output_dir=Path(args.output_dir),
        prefix=args.prefix,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
