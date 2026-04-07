"""Refresh local evidence/export artifacts from existing evidence + local seed data.

This runner is intentionally bounded:
  - it does not call external APIs;
  - it reuses current evidence bundles as the source of truth for price/photo facts;
  - it overlays trusted local content seeds from honeywell_insales_import.csv;
  - it attaches merchandising placeholder images only when the accepted enhanced
    derivative exists and lineage is preserved.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from catalog_seed import load_insales_seed_index
from card_status import derive_photo_contract_fields
from export_pipeline import write_audit_report, write_evidence_bundles, write_insales_export
from price_admissibility import materialize_price_admissibility


ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
DEFAULT_INPUT_FILE = DOWNLOADS / "honeywell_insales_import.csv"
DEFAULT_EVIDENCE_DIR = DOWNLOADS / "evidence"
DEFAULT_PHOTO_MANIFEST = DOWNLOADS / "scout_cache" / "photo_enhance_manifest_all25_recheck.jsonl"
DEFAULT_PHOTO_VERDICT_FILE = DOWNLOADS / "photo_verdict.json"
DEFAULT_PRICE_MANIFEST = DOWNLOADS / "scout_cache" / "merged_manifest.jsonl"
DEFAULT_BLOCKED_PRICE_MANIFEST = DOWNLOADS / "scout_cache" / "bvs_25sku_manifest.jsonl"
DEFAULT_EXPORT_DIR = DOWNLOADS / "export"
DEFAULT_CANONICAL_DATA_FILE = DOWNLOADS / "product_data.json"
AUDITS_DIR = DOWNLOADS / "audits"


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _safe_pn_key(value: str) -> str:
    return str(value or "").strip().upper()


def load_photo_verdict_index(path: Path) -> dict[str, dict[str, Any]]:
    payload = _load_json(path, {})
    if not isinstance(payload, dict):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for pn, row in payload.items():
        if isinstance(row, dict):
            index[_safe_pn_key(pn)] = row
    return index


def load_merchandising_index(path: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in _load_jsonl(path):
        pn = _safe_pn_key(row.get("part_number", ""))
        if not pn:
            continue
        enhanced_local_path = str(row.get("enhanced_local_path", "") or "").strip()
        enhanced_exists = bool(row.get("enhanced_exists")) and bool(enhanced_local_path)
        if enhanced_exists and not Path(enhanced_local_path).exists():
            enhanced_exists = False

        index[pn] = {
            "image_local_path": enhanced_local_path if enhanced_exists else "",
            "image_status": str(row.get("output_photo_status", "") or "").strip(),
            "image_kind": str(row.get("derivative_kind", "") or "").strip(),
            "image_temporary": bool(enhanced_exists and row.get("output_photo_status") == "placeholder"),
            "replacement_required": bool(row.get("replacement_required", False)),
            "lineage_preserved": bool(row.get("lineage_preserved", False)),
            "source_manifest_ref": str(path),
            "source_photo_verdict": str(row.get("source_photo_verdict", "") or "").strip(),
            "cleanup_recommended": bool(row.get("cleanup_recommended", False)),
            "policy_reason_code": str(row.get("policy_reason_code", "") or "").strip(),
        }
    return index


def load_price_overlay_index(path: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in _load_jsonl(path):
        pn = _safe_pn_key(row.get("part_number", ""))
        if pn:
            index[pn] = row
    return index


def load_blocked_price_overlay_index(path: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in _load_jsonl(path):
        pn = _safe_pn_key(row.get("part_number", ""))
        if not pn:
            continue
        if bool(row.get("blocked_ui_detected")) or str(row.get("http_status", "") or "").strip() in {"401", "403", "407", "429", "498"}:
            index[pn] = row
    return index


def iter_evidence_bundles(evidence_dir: Path, limit: int | None = None) -> list[dict[str, Any]]:
    bundles: list[dict[str, Any]] = []
    for path in sorted(evidence_dir.glob("evidence_*.json")):
        payload = _load_json(path, {})
        if isinstance(payload, dict) and payload.get("pn"):
            bundles.append(payload)
    if limit is not None:
        return bundles[:limit]
    return bundles


def _fallback_photo_status(bundle: dict[str, Any], verdict_value: str) -> str:
    photo = bundle.get("photo", {})
    current_status = str(photo.get("photo_status", "") or "").strip()
    if current_status:
        return current_status
    if verdict_value == "KEEP":
        return "exact_evidence"
    return "rejected"


def _build_photo_result(bundle: dict[str, Any], verdict_row: dict[str, Any] | None) -> dict[str, Any]:
    photo = bundle.get("photo", {})
    content = bundle.get("content", {})
    trace = bundle.get("trace", {})
    structured = bundle.get("structured_identity", {})
    verdict_value = str((verdict_row or {}).get("verdict", photo.get("verdict", "NO_PHOTO")) or "NO_PHOTO").strip().upper()
    return {
        "path": photo.get("path", ""),
        "sha1": photo.get("sha1", ""),
        "width": photo.get("width", 0),
        "height": photo.get("height", 0),
        "size_kb": photo.get("size_kb", 0),
        "source": photo.get("source", ""),
        "phash": photo.get("phash", ""),
        "stock_photo_flag": bool(photo.get("stock_photo_flag")),
        "mpn_confirmed": bool(photo.get("mpn_confirmed_via_jsonld")),
        "description": content.get("description"),
        "specs": content.get("specs") or {},
        "pn_match_location": trace.get("pn_match_location", ""),
        "pn_match_confidence": trace.get("pn_match_confidence", 0),
        "pn_match_is_numeric": bool(trace.get("pn_match_is_numeric", False)),
        "numeric_pn_guard_triggered": bool(trace.get("numeric_pn_guard_triggered")),
        "brand_cooccurrence": bool(trace.get("brand_cooccurrence", True)),
        "source_trust_weight": trace.get("source_trust_weight"),
        "structured_pn_match_location": structured.get("structured_pn_match_location", ""),
        "exact_structured_pn_match": bool(structured.get("exact_structured_pn_match")),
        "exact_jsonld_pn_match": bool(structured.get("exact_jsonld_pn_match")),
        "exact_title_pn_match": bool(structured.get("exact_title_pn_match")),
        "exact_h1_pn_match": bool(structured.get("exact_h1_pn_match")),
        "exact_product_context_pn_match": bool(structured.get("exact_product_context_pn_match")),
        "photo_status": _fallback_photo_status(bundle, verdict_value),
    }


def _build_vision_verdict(bundle: dict[str, Any], verdict_row: dict[str, Any] | None) -> dict[str, Any]:
    photo = bundle.get("photo", {})
    if verdict_row:
        verdict_value = str(verdict_row.get("verdict", "") or "").strip().upper()
        if verdict_value:
            return {
                "verdict": verdict_value,
                "reason": str(verdict_row.get("reason", "") or "").strip(),
            }
    return {
        "verdict": str(photo.get("verdict", "NO_PHOTO") or "NO_PHOTO").strip().upper(),
        "reason": str(photo.get("verdict_reason", "") or "").strip(),
    }


def _build_price_result(bundle: dict[str, Any]) -> dict[str, Any]:
    price = dict(bundle.get("price", {}) or {})
    if "price_per_unit" in price and "price_usd" not in price:
        price["price_usd"] = price.get("price_per_unit")
    return price


def _build_merchandising_block(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "image_local_path": "",
            "image_status": "",
            "image_kind": "",
            "image_temporary": False,
            "replacement_required": False,
            "lineage_preserved": False,
            "source_manifest_ref": "",
            "source_photo_verdict": "",
            "cleanup_recommended": False,
            "policy_reason_code": "",
        }
    return {
        "image_local_path": row.get("image_local_path", ""),
        "image_status": row.get("image_status", ""),
        "image_kind": row.get("image_kind", ""),
        "image_temporary": bool(row.get("image_temporary", False)),
        "replacement_required": bool(row.get("replacement_required", False)),
        "lineage_preserved": bool(row.get("lineage_preserved", False)),
        "source_manifest_ref": row.get("source_manifest_ref", ""),
        "source_photo_verdict": row.get("source_photo_verdict", ""),
        "cleanup_recommended": bool(row.get("cleanup_recommended", False)),
        "policy_reason_code": row.get("policy_reason_code", ""),
    }


def build_product_data_entry(bundle: dict[str, Any]) -> dict[str, Any]:
    content = bundle.get("content", {})
    raw_price = dict(bundle.get("price", {}) or {})
    price = materialize_price_admissibility(
        raw_price,
        historical_state_price_status=str(
            bundle.get("historical_state_price_status", "")
            or bundle.get("state_price_status", "")
            or ""
        ).strip(),
    )
    merchandising = bundle.get("merchandising", {})
    return {
        "specs": content.get("specs") or {},
        "description": content.get("description"),
        "description_source": content.get("description_source", ""),
        "site_placement": content.get("site_placement", ""),
        "product_type": content.get("product_type", ""),
        "seed_name": content.get("seed_name", ""),
        "price_usd": price.get("price_per_unit"),
        "price_source": price.get("source_url"),
        "price_status": price.get("price_status"),
        "offer_admissibility_status": price.get("offer_admissibility_status", ""),
        "string_lineage_status": price.get("string_lineage_status", ""),
        "commercial_identity_status": price.get("commercial_identity_status", ""),
        "staleness_or_conflict_status": price.get("staleness_or_conflict_status", ""),
        "price_admissibility_reason_codes": list(price.get("price_admissibility_reason_codes", []) or []),
        "price_admissibility_review_bucket": price.get("price_admissibility_review_bucket", ""),
        "price_confidence": price.get("price_confidence"),
        "price_currency": price.get("currency"),
        "stock_status": price.get("stock_status"),
        "suffix_conflict": bool(price.get("suffix_conflict")),
        "category_mismatch": bool(price.get("category_mismatch")),
        "page_product_class": price.get("page_product_class"),
        "image_local_path": merchandising.get("image_local_path", ""),
        "image_status": merchandising.get("image_status", ""),
    }


def _append_unique_code(codes: list[str], code: str) -> list[str]:
    if code and code not in codes:
        codes.append(code)
    return codes


def _append_review_reason_record(records: list[dict[str, Any]], pn: str, reason_code: str) -> list[dict[str, Any]]:
    if any(str(row.get("reason_code", "")) == reason_code for row in records):
        return records
    if reason_code == "NO_IMAGE_EVIDENCE":
        records.append(
            {
                "reason_code": "NO_IMAGE_EVIDENCE",
                "field": "image",
                "severity": "INFO",
                "candidate_ids": [f"cand_image_{pn}"],
                "evidence_ids": [f"ev_image_{pn}"],
                "policy_rule_id": "local_catalog_refresh_v1",
                "bucket": "MISSING_MINIMUM_EVIDENCE",
            }
        )
    return records


def _materialize_bundle_price_truth(bundle: dict[str, Any]) -> None:
    price = dict(bundle.get("price", {}) or {})
    materialized = materialize_price_admissibility(
        price,
        historical_state_price_status=str(
            bundle.get("historical_state_price_status", "")
            or bundle.get("state_price_status", "")
            or ""
        ).strip(),
    )
    bundle["price"] = materialized


def _merge_price_overlay(
    bundle: dict[str, Any],
    *,
    price_overlay_row: dict[str, Any] | None,
    blocked_price_overlay_row: dict[str, Any] | None,
) -> tuple[bool, bool]:
    if not price_overlay_row and not blocked_price_overlay_row:
        return False, False

    price = dict(bundle.get("price", {}) or {})
    for key in (
        "price_admissibility_schema_version",
        "string_lineage_status",
        "commercial_identity_status",
        "offer_admissibility_status",
        "staleness_or_conflict_status",
        "price_admissibility_reason_codes",
        "price_admissibility_review_bucket",
        "price_admissibility_review_required",
    ):
        price.pop(key, None)

    if price_overlay_row:
        for key in (
            "price_status",
            "price_per_unit",
            "currency",
            "rub_price",
            "fx_rate_used",
            "fx_provider",
            "price_confidence",
            "stock_status",
            "offer_unit_basis",
            "offer_qty",
            "lead_time_detected",
            "quote_cta_url",
            "page_product_class",
            "price_source_seen",
            "price_source_exact_product_lineage_confirmed",
            "price_source_lineage_reason_code",
            "price_source_surface_stable",
            "price_source_surface_conflict_detected",
            "price_source_surface_conflict_reason_code",
            "source_domain",
            "source_tier",
            "source_type",
            "source_provider",
            "source_role",
            "source_price_value",
            "source_price_currency",
            "source_offer_qty",
            "source_offer_unit_basis",
            "notes",
            "http_status",
            "review_required",
            "cache_fallback_used",
            "merge_source",
            "transient_failure_codes",
            "page_url",
            "price_basis_note",
        ):
            if key in price_overlay_row and price_overlay_row.get(key) is not None:
                price[key] = price_overlay_row.get(key)
        page_url = str(price_overlay_row.get("page_url", "") or "").strip()
        if page_url:
            price["source_url"] = page_url
            price["price_source_url"] = page_url
        if price_overlay_row.get("price_per_unit") is not None:
            price["price_usd"] = price_overlay_row.get("price_per_unit")
        if price_overlay_row.get("source_domain"):
            price["price_source_domain"] = price_overlay_row.get("source_domain")
        if price_overlay_row.get("source_tier"):
            price["price_source_tier"] = price_overlay_row.get("source_tier")
        if price_overlay_row.get("source_type"):
            price["price_source_type"] = price_overlay_row.get("source_type")

    prefer_current_price_overlay = bool(
        price_overlay_row
        and str(price.get("price_status", "") or "").strip() == "public_price"
        and bool(price.get("price_source_exact_product_lineage_confirmed"))
    )

    if blocked_price_overlay_row:
        if not prefer_current_price_overlay and blocked_price_overlay_row.get("blocked_ui_detected") is not None:
            price["blocked_ui_detected"] = blocked_price_overlay_row.get("blocked_ui_detected")
        if not prefer_current_price_overlay and blocked_price_overlay_row.get("http_status") is not None:
            price["http_status"] = blocked_price_overlay_row.get("http_status")
        blocked_page_url = str(blocked_price_overlay_row.get("page_url", "") or "").strip()
        if blocked_page_url:
            price["blocked_surface_page_url"] = blocked_page_url
            price["blocked_surface_domain"] = str(blocked_price_overlay_row.get("source_domain", "") or "").strip()

    bundle["price"] = price
    return bool(price_overlay_row), bool(blocked_price_overlay_row)


def _apply_photo_verdict_override(refreshed: dict[str, Any], photo_verdict_row: dict[str, Any] | None) -> None:
    if not photo_verdict_row:
        photo = refreshed.get("photo", {})
        if photo and not photo.get("photo_status"):
            contract_status = "exact_evidence" if str(photo.get("verdict", "")).upper() == "KEEP" else "rejected"
            photo.update(derive_photo_contract_fields(contract_status))
        return

    pn = str(refreshed.get("pn", "") or "").strip()
    photo = refreshed.setdefault("photo", {})
    verdict_value = str(photo_verdict_row.get("verdict", photo.get("verdict", "")) or "").strip().upper()
    verdict_reason = str(photo_verdict_row.get("reason", photo.get("verdict_reason", "")) or "").strip()
    existing_verdict = str(photo.get("verdict", "") or "").strip().upper()

    photo["verdict"] = verdict_value or existing_verdict or "NO_PHOTO"
    photo["verdict_reason"] = verdict_reason

    if photo["verdict"] == "KEEP":
        if not photo.get("photo_status"):
            photo.update(derive_photo_contract_fields("exact_evidence"))
        return

    photo.update(derive_photo_contract_fields("rejected"))
    price_status = str(refreshed.get("price", {}).get("price_status", "") or "").strip()
    refreshed["card_status"] = "REVIEW_REQUIRED" if price_status in {"public_price", "rfq_only"} else "DRAFT_ONLY"

    review_reasons = list(refreshed.get("review_reasons", []) or [])
    refreshed["review_reasons"] = _append_unique_code(review_reasons, "NO_IMAGE_EVIDENCE")

    decision = refreshed.get("policy_decision_v2")
    if isinstance(decision, dict):
        decision["card_status"] = refreshed["card_status"]
        decision["image_status"] = "INSUFFICIENT"
        decision["review_reasons"] = _append_review_reason_record(
            list(decision.get("review_reasons", []) or []),
            pn,
            "NO_IMAGE_EVIDENCE",
        )
        decision["review_buckets"] = sorted(
            {
                *[str(bucket) for bucket in decision.get("review_buckets", []) or []],
                "MISSING_MINIMUM_EVIDENCE",
            }
        )
        refreshed["review_reasons_v2"] = decision["review_reasons"]
    field_statuses = refreshed.get("field_statuses_v2")
    if isinstance(field_statuses, dict):
        field_statuses["image_status"] = "INSUFFICIENT"


def refresh_bundle(
    bundle: dict[str, Any],
    *,
    content_seed: dict[str, Any],
    merchandising_row: dict[str, Any] | None,
    photo_verdict_row: dict[str, Any] | None,
    price_overlay_row: dict[str, Any] | None,
    blocked_price_overlay_row: dict[str, Any] | None,
    run_ts: str,
) -> dict[str, Any]:
    refreshed = deepcopy(bundle)
    refreshed["generated_at"] = run_ts
    refreshed["our_price_raw"] = str(content_seed.get("our_price_raw", "") or refreshed.get("our_price_raw", "") or "").strip()
    refreshed["expected_category"] = str(
        content_seed.get("product_type", "") or refreshed.get("expected_category", "") or ""
    ).strip()

    content = dict(refreshed.get("content", {}) or {})
    content["specs"] = content.get("specs") or {}
    if content_seed.get("description"):
        content["description"] = content_seed.get("description")
        content["description_source"] = content_seed.get("description_source", "insales_import_seed")
    else:
        content["description_source"] = content.get("description_source", "")
    content["site_placement"] = str(content_seed.get("site_placement", "") or content.get("site_placement", "") or "").strip()
    content["product_type"] = str(content_seed.get("product_type", "") or content.get("product_type", "") or "").strip()
    content["seed_name"] = str(content_seed.get("seed_name", "") or content.get("seed_name", "") or "").strip()
    refreshed["content"] = content
    price_overlay_applied, blocked_price_overlay_applied = _merge_price_overlay(
        refreshed,
        price_overlay_row=price_overlay_row,
        blocked_price_overlay_row=blocked_price_overlay_row,
    )
    _materialize_bundle_price_truth(refreshed)

    refreshed["merchandising"] = _build_merchandising_block(merchandising_row)
    _apply_photo_verdict_override(refreshed, photo_verdict_row)
    if str(refreshed.get("photo", {}).get("verdict", "") or "").strip().upper() == "REJECT":
        refreshed["merchandising"]["image_local_path"] = ""
        refreshed["merchandising"]["image_status"] = "rejected"
        refreshed["merchandising"]["image_temporary"] = False
    policy_card_status = str((refreshed.get("policy_decision_v2") or {}).get("card_status", "") or "").strip()
    card_status_source = "base_bundle_preserved"
    if photo_verdict_row and str(photo_verdict_row.get("verdict", "") or "").strip().upper() == "REJECT":
        card_status_source = "photo_verdict_override"
    refreshed["refresh_trace"] = {
        "refresh_mode": "local_catalog_refresh_v1",
        "content_seed_applied": bool(content_seed.get("description") or content_seed.get("site_placement") or content_seed.get("product_type")),
        "content_seed_source": content_seed.get("description_source", ""),
        "photo_verdict_cache_applied": bool(photo_verdict_row),
        "photo_verdict_value": str((photo_verdict_row or {}).get("verdict", "") or "").strip(),
        "price_overlay_applied": price_overlay_applied,
        "blocked_price_overlay_applied": blocked_price_overlay_applied,
        "merchandising_attached": bool(refreshed["merchandising"].get("image_local_path")),
        "merchandising_image_status": refreshed["merchandising"].get("image_status", ""),
        "card_status_source": card_status_source,
        "policy_card_status_historical": policy_card_status,
        "policy_card_status_mismatch": bool(policy_card_status and policy_card_status != refreshed.get("card_status")),
    }
    return refreshed


def _make_output_root(output_root: Path | None) -> Path:
    if output_root is not None:
        return output_root
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return AUDITS_DIR / f"local_catalog_refresh_{ts}"


def run(
    *,
    input_file: Path = DEFAULT_INPUT_FILE,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    photo_manifest: Path = DEFAULT_PHOTO_MANIFEST,
    photo_verdict_file: Path = DEFAULT_PHOTO_VERDICT_FILE,
    price_manifest: Path = DEFAULT_PRICE_MANIFEST,
    blocked_price_manifest: Path = DEFAULT_BLOCKED_PRICE_MANIFEST,
    output_root: Path | None = None,
    canonical_evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    canonical_export_dir: Path = DEFAULT_EXPORT_DIR,
    canonical_data_file: Path = DEFAULT_CANONICAL_DATA_FILE,
    promote_canonical: bool = False,
    base_photo_url: str = "",
    limit: int | None = None,
) -> dict[str, Any]:
    output_root = _make_output_root(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    audit_evidence_dir = output_root / "evidence"
    audit_export_path = output_root / "insales_export.csv"
    audit_report_path = output_root / "audit_report.json"
    audit_product_data_path = output_root / "product_data.json"
    summary_path = output_root / "summary.json"

    seeds = load_insales_seed_index(input_file)
    merchandising_index = load_merchandising_index(photo_manifest)
    photo_verdict_index = load_photo_verdict_index(photo_verdict_file)
    price_overlay_index = load_price_overlay_index(price_manifest)
    blocked_price_overlay_index = load_blocked_price_overlay_index(blocked_price_manifest)
    bundles = iter_evidence_bundles(evidence_dir, limit=limit)
    run_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    refreshed_bundles: list[dict[str, Any]] = []
    refreshed_product_data: dict[str, Any] = {}
    content_seeded_count = 0
    merchandising_attached_count = 0
    photo_rejected_count = 0
    policy_card_status_mismatch_count = 0

    for bundle in bundles:
        pn = str(bundle.get("pn", "") or "").strip()
        content_seed = dict(seeds.get(pn, {}) or {})
        photo_verdict_row = photo_verdict_index.get(_safe_pn_key(pn))
        merchandising_row = merchandising_index.get(_safe_pn_key(pn))
        refreshed = refresh_bundle(
            bundle,
            content_seed=content_seed,
            merchandising_row=merchandising_row,
            photo_verdict_row=photo_verdict_row,
            price_overlay_row=price_overlay_index.get(_safe_pn_key(pn)),
            blocked_price_overlay_row=blocked_price_overlay_index.get(_safe_pn_key(pn)),
            run_ts=run_ts,
        )
        refreshed_bundles.append(refreshed)
        refreshed_product_data[pn] = build_product_data_entry(refreshed)
        if refreshed["refresh_trace"]["content_seed_applied"]:
            content_seeded_count += 1
        if refreshed["refresh_trace"]["merchandising_attached"]:
            merchandising_attached_count += 1
        if refreshed.get("photo", {}).get("verdict") == "REJECT":
            photo_rejected_count += 1
        if refreshed["refresh_trace"].get("policy_card_status_mismatch"):
            policy_card_status_mismatch_count += 1

    write_evidence_bundles(refreshed_bundles, audit_evidence_dir)
    exported_count = write_insales_export(refreshed_bundles, audit_export_path, base_photo_url=base_photo_url)
    audit_summary = write_audit_report(
        refreshed_bundles,
        audit_report_path,
        {
            "run_ts": run_ts,
            "mode": "local_catalog_refresh_v1",
            "promote_canonical": promote_canonical,
            "input_file": str(input_file),
            "photo_manifest": str(photo_manifest),
            "price_manifest": str(price_manifest),
            "blocked_price_manifest": str(blocked_price_manifest),
            "source_evidence_dir": str(evidence_dir),
            "canonical_evidence_dir": str(canonical_evidence_dir),
        },
    )
    audit_product_data_path.write_text(json.dumps(refreshed_product_data, ensure_ascii=False, indent=2), encoding="utf-8")

    if promote_canonical:
        canonical_export_dir.mkdir(parents=True, exist_ok=True)
        canonical_evidence_dir.mkdir(parents=True, exist_ok=True)
        write_evidence_bundles(refreshed_bundles, canonical_evidence_dir)
        write_insales_export(
            refreshed_bundles,
            canonical_export_dir / "insales_export.csv",
            base_photo_url=base_photo_url,
        )
        write_audit_report(
            refreshed_bundles,
            canonical_export_dir / "audit_report.json",
            {
                "run_ts": run_ts,
                "mode": "local_catalog_refresh_v1",
                "promoted_from": str(output_root),
                "source_evidence_dir": str(evidence_dir),
            },
        )
        canonical_data_file.write_text(json.dumps(refreshed_product_data, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "mode": "local_catalog_refresh_v1",
        "run_ts": run_ts,
        "input_file": str(input_file),
        "source_evidence_dir": str(evidence_dir),
        "canonical_evidence_dir": str(canonical_evidence_dir),
        "photo_manifest": str(photo_manifest),
        "photo_verdict_file": str(photo_verdict_file),
        "price_manifest": str(price_manifest),
        "blocked_price_manifest": str(blocked_price_manifest),
        "output_root": str(output_root),
        "input_bundle_count": len(bundles),
        "refreshed_bundle_count": len(refreshed_bundles),
        "content_seeded_count": content_seeded_count,
        "merchandising_attached_count": merchandising_attached_count,
        "photo_rejected_count": photo_rejected_count,
        "policy_card_status_mismatch_count": policy_card_status_mismatch_count,
        "exported_rows": exported_count,
        "cards": audit_summary.get("cards", {}),
        "promote_canonical": promote_canonical,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh local evidence/export artifacts from current evidence + seed data.")
    parser.add_argument("--input-file", default=str(DEFAULT_INPUT_FILE))
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    parser.add_argument("--canonical-evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    parser.add_argument("--photo-manifest", default=str(DEFAULT_PHOTO_MANIFEST))
    parser.add_argument("--photo-verdict-file", default=str(DEFAULT_PHOTO_VERDICT_FILE))
    parser.add_argument("--price-manifest", default=str(DEFAULT_PRICE_MANIFEST))
    parser.add_argument("--blocked-price-manifest", default=str(DEFAULT_BLOCKED_PRICE_MANIFEST))
    parser.add_argument("--output-root", default="")
    parser.add_argument("--base-photo-url", default="")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--promote-canonical", action="store_true")
    args = parser.parse_args()

    summary = run(
        input_file=Path(args.input_file),
        evidence_dir=Path(args.evidence_dir),
        canonical_evidence_dir=Path(args.canonical_evidence_dir),
        photo_manifest=Path(args.photo_manifest),
        photo_verdict_file=Path(args.photo_verdict_file),
        price_manifest=Path(args.price_manifest),
        blocked_price_manifest=Path(args.blocked_price_manifest),
        output_root=Path(args.output_root) if args.output_root else None,
        promote_canonical=args.promote_canonical,
        base_photo_url=args.base_photo_url,
        limit=args.limit,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
