"""export_pipeline.py — Evidence bundle + InSales-ready export.

Outputs:
  1. evidence/evidence_{pn}.json — per-SKU full evidence bundle
  2. export/insales_export.csv  — InSales-ready (AUTO_PUBLISH + REVIEW_REQUIRED only)
  3. export/audit_report.json   — run summary + per-SKU status matrix

Card status logic:
  AUTO_PUBLISH:    KEEP photo + publishable price (public/rfq) + no mismatch
  REVIEW_REQUIRED: KEEP photo but price uncertain, OR valid price but no/reject photo
  DRAFT_ONLY:      No usable photo + no valid price, OR mismatch flags block publish

Photo canonical filename:
  {BRAND}_{PN_NORMALIZED}_{SHA1_8}.jpg
  No spaces, uppercase brand+PN, 8-char sha1 suffix for dedup.

Public photo URL:
  base_photo_url + "/" + canonical_filename
  If no hosting configured → staging placeholder [LOCAL:{path}]
"""
from __future__ import annotations

import csv
import json
import re
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Import confidence module if available
_scripts_dir = os.path.dirname(__file__)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

try:
    from confidence import (
        compute_pn_confidence,
        compute_image_confidence,
        compute_price_confidence,
        compute_card_confidence,
        confidence_label,
    )
    _CONFIDENCE_AVAILABLE = True
except ImportError:
    _CONFIDENCE_AVAILABLE = False

from card_status import (
    assign_card_status_legacy,
    build_decision_record_v2_from_legacy_inputs,
    derive_photo_contract_fields,
    derive_photo_status_from_legacy_inputs,
)
from catalog_verifier import build_verifier_shadow_record
from deterministic_false_positive_controls import (
    apply_numeric_keep_guard,
    tighten_public_price_result,
)
from naming_resolver import resolve_title_or_fallback
from no_price_coverage import materialize_no_price_coverage
from price_admissibility import materialize_price_admissibility
from price_evidence_cache import (
    normalize_cache_fallback_reason,
    normalize_transient_failure_codes,
)


# ── H-lite: deterministic title assembly (no AI) ────────────────────────────────

def assemble_title_lite(
    pn: str,
    brand: str,
    raw_title: str,
    subbrand: str = "",
    category: str = "",
    specs: Optional[dict] = None,
) -> str:
    """Assemble a B2B product title deterministically from available evidence.

    Formula: [тип товара] [бренд/подбренд] [PN] [1-2 ключевых признака]

    Rules:
      - Never invents data — only uses provided fields.
      - If no structured info: falls back to brand + PN.
      - raw_title is used as fallback, not primary source (may be messy).
      - Language: preserves original terms as-is (RU/EN mixed OK for B2B).
      - Max length: 150 chars (InSales limit).
    """
    parts: list[str] = []

    # 1. Category / product type (if short and clean)
    if category and len(category) <= 40 and category.lower() not in ("unknown", ""):
        parts.append(category.strip())

    # 2. Brand / subbrand
    brand_part = subbrand.strip() if subbrand else brand.strip()
    if brand_part:
        parts.append(brand_part)

    # 3. PN (always present)
    if pn:
        parts.append(pn.strip())

    # 4. Key feature from specs (max 1-2 values, short ones only)
    if specs:
        feature_keys = (
            "Model:", "Product Line:", "Technology:", "Color:",
            "Напряжение:", "Ток:", "Мощность:", "Тип:",
        )
        added = 0
        for key in feature_keys:
            val = specs.get(key, "").strip()
            if val and len(val) <= 30 and added < 2:
                parts.append(val)
                added += 1

    if parts:
        title = " ".join(parts)
    else:
        # Fallback: use raw_title stripped of extra whitespace
        title = " ".join(raw_title.split()) if raw_title else f"{brand} {pn}"

    resolved_title, _ = resolve_title_or_fallback(
        part_number=pn,
        raw_title=raw_title,
        brand=brand,
        subbrand=subbrand,
        specs=specs,
        fallback_title=title,
    )
    return resolved_title[:150]


# ── Filename normalization ───────────────────────────────────────────────────────

_UNSAFE_RE = re.compile(r"[^\w\-]")


def _safe(s: str) -> str:
    return _UNSAFE_RE.sub("_", s.upper()).strip("_")


def canonical_photo_filename(brand: str, pn: str, sha1: str, ext: str = "jpg") -> str:
    """Canonical photo filename for storage: {BRAND}_{PN}_{SHA1_8}.{ext}"""
    sha1_8 = (sha1 or "00000000")[:8]
    return f"{_safe(brand)}_{_safe(pn)}_{sha1_8}.{ext}"


# ── Card status ──────────────────────────────────────────────────────────────────

def assign_card_status(
    photo_verdict: str,
    price_status: str,
    category_mismatch: bool = False,
    brand_mismatch: bool = False,
    stock_photo_flag: bool = False,
    photo_status: str = "",
) -> tuple[str, list[str]]:
    """Compatibility helper for legacy callers/tests around export rules."""
    effective_photo_verdict = photo_verdict
    effective_stock_photo_flag = stock_photo_flag
    if photo_status and photo_status != "exact_evidence":
        effective_photo_verdict = "NO_PHOTO"
        effective_stock_photo_flag = photo_status == "family_evidence"
    return assign_card_status_legacy(
        photo_verdict=effective_photo_verdict,
        price_status=price_status,
        category_mismatch=category_mismatch,
        brand_mismatch=brand_mismatch,
        stock_photo_flag=effective_stock_photo_flag,
    )


def _mirror_bundle_card_outcome(decision_record_v2: dict) -> tuple[str, list[str]]:
    """Mirror the authoritative v2 card decision onto legacy bundle fields."""
    review_reason_codes: list[str] = []
    for reason in decision_record_v2.get("review_reasons", []) or []:
        code = str(reason.get("reason_code", "")).strip()
        if code and code not in review_reason_codes:
            review_reason_codes.append(code)
    return str(decision_record_v2["card_status"]), review_reason_codes


# ── Evidence bundle ──────────────────────────────────────────────────────────────
def _negative_marker(marker_class: str, code: str, source_field: str) -> dict:
    return {
        "class": marker_class,
        "code": code,
        "source_field": source_field,
    }


def _append_negative_marker(bucket: list[dict], marker_class: str, code: str, source_field: str) -> None:
    marker = _negative_marker(marker_class, code, source_field)
    if marker not in bucket:
        bucket.append(marker)


def build_negative_evidence_block(
    *,
    photo_result: dict,
    vision_verdict: dict,
    price_result: dict,
) -> dict:
    """Materialize explicit negative evidence markers from deterministic fields."""
    negative = {
        "photo": [],
        "price": [],
        "identity": [],
    }

    if bool(photo_result.get("stock_photo_flag")):
        _append_negative_marker(
            negative["photo"],
            "stock_photo",
            "stock_photo_flag",
            "photo.stock_photo_flag",
        )

    for reason_code in vision_verdict.get("numeric_keep_guard_reasons", []) or []:
        if reason_code:
            _append_negative_marker(
                negative["photo"],
                "numeric_keep_guard",
                str(reason_code),
                "photo.numeric_keep_guard_reasons",
            )

    for reason_code in price_result.get("public_price_rejection_reasons", []) or []:
        if reason_code:
            _append_negative_marker(
                negative["price"],
                "public_price_rejection",
                str(reason_code),
                "price.public_price_rejection_reasons",
            )

    no_price_reason = str(price_result.get("price_no_price_reason_code", "") or "").strip()
    if no_price_reason:
        _append_negative_marker(
            negative["price"],
            "no_price_reason",
            no_price_reason,
            "price.price_no_price_reason_code",
        )

    if bool(price_result.get("price_source_surface_conflict_detected")):
        surface_conflict_reason = str(
            price_result.get("price_source_surface_conflict_reason_code", "") or ""
        ).strip() or "source_surface_conflict_detected"
        _append_negative_marker(
            negative["price"],
            "source_surface_conflict",
            surface_conflict_reason,
            "price.price_source_surface_conflict_reason_code",
        )

    if bool(price_result.get("price_source_terminal_weak_lineage")):
        replacement_reason = str(
            price_result.get("price_source_replacement_reason_code", "") or ""
        ).strip() or "terminal_weak_lineage"
        _append_negative_marker(
            negative["price"],
            "terminal_weak_lineage",
            replacement_reason,
            "price.price_source_replacement_reason_code",
        )

    if bool(price_result.get("category_mismatch")):
        _append_negative_marker(
            negative["identity"],
            "identity_mismatch",
            "category_mismatch",
            "price.category_mismatch",
        )

    if bool(price_result.get("brand_mismatch")):
        _append_negative_marker(
            negative["identity"],
            "identity_mismatch",
            "brand_mismatch",
            "price.brand_mismatch",
        )

    if bool(price_result.get("suffix_conflict")):
        _append_negative_marker(
            negative["identity"],
            "suffix_conflict",
            "suffix_conflict",
            "price.suffix_conflict",
        )

    return negative


_RUN_ID_TS_RE = re.compile(r"(\d{8}T\d{6}Z)")


def _run_id_to_iso8601(run_id: str) -> str:
    match = _RUN_ID_TS_RE.search(str(run_id or "").strip())
    if not match:
        return ""
    raw = match.group(1)
    return (
        f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
        f"T{raw[9:11]}:{raw[11:13]}:{raw[13:15]}Z"
    )


def _has_price_surface_signal(price_result: dict) -> bool:
    return any(
        (
            str(price_result.get("price_status", "") or "").strip() not in {"", "no_price_found"},
            bool(price_result.get("source_url")),
            bool(price_result.get("quote_cta_url")),
            bool(price_result.get("price_source_seen")),
            bool(price_result.get("price_source_url")),
            bool(price_result.get("cache_fallback_used")),
            bool(price_result.get("price_source_surface_preserved_from_prior_run")),
        )
    )


def infer_price_observation_surface(price_result: dict, run_ts: str) -> dict:
    explicit = str(price_result.get("price_observed_at", "") or "").strip()
    if explicit:
        return {
            "price_observed_at": explicit,
            "price_observed_date": explicit[:10],
            "price_observation_origin": "explicit_field",
        }

    if bool(price_result.get("cache_fallback_used")):
        observed_at = _run_id_to_iso8601(price_result.get("cache_source_run_id", ""))
        return {
            "price_observed_at": observed_at,
            "price_observed_date": observed_at[:10] if observed_at else "",
            "price_observation_origin": "cache_fallback",
        }

    if bool(price_result.get("price_source_surface_preserved_from_prior_run")):
        observed_at = _run_id_to_iso8601(
            price_result.get("price_source_surface_preserved_source_run_id", "")
        )
        return {
            "price_observed_at": observed_at,
            "price_observed_date": observed_at[:10] if observed_at else "",
            "price_observation_origin": "preserved_surface",
        }

    if _has_price_surface_signal(price_result):
        observed_at = str(run_ts or "").strip()
        return {
            "price_observed_at": observed_at,
            "price_observed_date": observed_at[:10] if observed_at else "",
            "price_observation_origin": "current_run",
        }

    return {
        "price_observed_at": "",
        "price_observed_date": "",
        "price_observation_origin": "",
    }


def _extract_url_from_source_ref(value: str) -> str:
    raw = str(value or "").strip()
    if raw.startswith(("http://", "https://")):
        return raw
    if ":" not in raw:
        return ""
    _, candidate = raw.split(":", 1)
    candidate = candidate.strip()
    if candidate.startswith(("http://", "https://")):
        return candidate
    return ""


def _infer_photo_origin_kind(source_ref: str) -> str:
    raw = str(source_ref or "").strip()
    if not raw:
        return ""
    if raw == "cached":
        return "cache"
    if raw == "not_found":
        return "missing"
    if raw.startswith("jsonld:"):
        return "jsonld_page"
    if raw.startswith("img:"):
        return "image_search"
    if raw.startswith(("google:", "yandex:")):
        return "search_result_page"
    if raw.startswith(("http://", "https://")):
        return "page_url"
    return "opaque_ref"


def build_evidence_paths_block(
    *,
    photo_result: dict,
    price_result: dict,
    raw_price_result: dict,
    canonical_photo_filename: str | None,
) -> dict:
    """Materialize explicit photo-vs-price evidence refs without changing legacy fields."""
    photo_source_ref = str(photo_result.get("source", "") or "")
    return {
        "photo": {
            "local_artifact_path": photo_result.get("path", ""),
            "canonical_filename": canonical_photo_filename or "",
            "public_url": None,
            "origin_ref": photo_source_ref,
            "origin_page_url": _extract_url_from_source_ref(photo_source_ref),
            "origin_kind": _infer_photo_origin_kind(photo_source_ref),
        },
        "price": {
            "observed_page_url": raw_price_result.get("source_url") or price_result.get("source_url") or "",
            "quote_cta_url": raw_price_result.get("quote_cta_url") or price_result.get("quote_cta_url") or "",
            "lineage_source_url": raw_price_result.get("price_source_url") or price_result.get("price_source_url") or "",
            "replacement_url": raw_price_result.get("price_source_replacement_url") or price_result.get("price_source_replacement_url") or "",
            "cache_bundle_ref": raw_price_result.get("cache_bundle_ref") or price_result.get("cache_bundle_ref") or "",
            "preserved_surface_bundle_ref": raw_price_result.get("price_source_surface_preserved_bundle_ref") or price_result.get("price_source_surface_preserved_bundle_ref") or "",
        },
    }


def build_evidence_bundle(
    pn: str,
    name: str,
    brand: str,
    photo_result: dict,
    vision_verdict: dict,
    price_result: dict,
    datasheet_result: dict,
    run_ts: str,
    our_price_raw: str = "",
    pn_variants: Optional[list] = None,
    subbrand: str = "",
    expected_category: str = "",
    content_seed: Optional[dict] = None,
) -> dict:
    """Build full per-SKU evidence bundle.

    All source data is preserved as-is. FX conversion result is additive.
    Computes overall_card_confidence via confidence.py when available.
    Assembles assembled_title via H-lite title formula.
    """
    guarded_price_result = materialize_price_admissibility(
        materialize_no_price_coverage(tighten_public_price_result(price_result)),
        queue_price_status=str(price_result.get("queue_price_status", "") or "").strip(),
        historical_state_price_status=str(
            price_result.get("historical_state_price_status", "") or ""
        ).strip(),
    )
    guarded_vision_verdict = apply_numeric_keep_guard(
        pn=pn,
        photo_result=photo_result,
        vision_verdict=vision_verdict,
        price_result=guarded_price_result,
    )
    photo_verdict = guarded_vision_verdict.get("verdict", "NO_PHOTO")
    price_status = guarded_price_result.get("price_status", "no_price_found")
    photo_status = derive_photo_status_from_legacy_inputs(photo_result, guarded_vision_verdict)
    photo_contract = derive_photo_contract_fields(photo_status)
    sha1 = photo_result.get("sha1", "")

    canon_fn = canonical_photo_filename(brand, pn, sha1) if sha1 else None

    # H-lite: deterministic title assembly
    assembled_title = assemble_title_lite(
        pn=pn,
        brand=brand,
        raw_title=name,
        subbrand=subbrand,
        category=expected_category,
        specs=photo_result.get("specs"),
    )
    decision_record_v2 = build_decision_record_v2_from_legacy_inputs(
        pn=pn,
        name=name,
        assembled_title=assembled_title,
        photo_result={
            **photo_result,
            "photo_status": photo_status,
            "numeric_keep_guard_applied": bool(guarded_vision_verdict.get("numeric_keep_guard_applied")),
        },
        vision_verdict=guarded_vision_verdict,
        price_result=guarded_price_result,
        datasheet_result=datasheet_result,
    )
    card_status, review_reasons = _mirror_bundle_card_outcome(decision_record_v2)
    negative_evidence = build_negative_evidence_block(
        photo_result=photo_result,
        vision_verdict=guarded_vision_verdict,
        price_result=guarded_price_result,
    )
    price_observation = infer_price_observation_surface(guarded_price_result, run_ts)
    normalized_cache_fallback_reason = normalize_cache_fallback_reason(
        guarded_price_result.get("cache_fallback_reason", "")
    )
    normalized_transient_failure_codes = normalize_transient_failure_codes(
        guarded_price_result.get("transient_failure_codes", [])
    )
    evidence_paths = build_evidence_paths_block(
        photo_result=photo_result,
        price_result=guarded_price_result,
        raw_price_result=price_result,
        canonical_photo_filename=canon_fn,
    )
    content_seed = content_seed or {}
    seeded_description = str(content_seed.get("description", "") or "").strip()
    content_description = seeded_description or photo_result.get("description")
    content_description_source = str(content_seed.get("description_source", "") or "").strip()
    if not content_description_source and seeded_description:
        content_description_source = "content_seed"
    if not content_description_source and photo_result.get("description"):
        content_description_source = "photo_page_meta"

    # Confidence computation
    confidence_block: dict = {}
    if _CONFIDENCE_AVAILABLE:
        source_tier = price_result.get("source_tier", "unknown")
        # Fix: prefer structured_pn_match_location from extract_structured_pn_flags()
        # over legacy pn_match_location (which is often empty/"")
        pn_loc = photo_result.get("structured_pn_match_location", "")
        if not pn_loc and photo_result.get("exact_structured_pn_match"):
            pn_loc = "jsonld"  # structured match found, default to high-confidence location
        if not pn_loc:
            pn_loc = photo_result.get("pn_match_location", "")  # legacy fallback
        pn_conf_raw = photo_result.get("pn_match_confidence", 0)
        pn_conf_norm = pn_conf_raw / 100.0 if pn_conf_raw > 1 else pn_conf_raw

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
            pn_match_confidence=pn_conf_norm,
            is_banner=(photo_verdict == "REJECT" and "баннер" in vision_verdict.get("reason", "").lower()),
            is_stock_photo=bool(photo_result.get("stock_photo_flag")),
            is_tiny=(photo_result.get("width", 999) < 150 or photo_result.get("height", 999) < 150),
            jsonld_image=bool(photo_result.get("mpn_confirmed")),
            brand_mismatch=bool(price_result.get("brand_mismatch")),
            category_mismatch=bool(price_result.get("category_mismatch")),
        )
        price_c = compute_price_confidence(
            source_tier=source_tier,
            pn_match_confidence=pn_conf_norm,
            price_status=price_status,
            unit_basis=price_result.get("offer_unit_basis", "unknown"),
            brand_mismatch=bool(guarded_price_result.get("brand_mismatch")),
            category_mismatch=bool(guarded_price_result.get("category_mismatch")),
        )
        cc = compute_card_confidence(
            pn_confidence=pn_c,
            image_confidence=img_c,
            price_confidence=price_c,
            price_status=price_status,
            photo_verdict=photo_verdict,
        )
        confidence_block = {
            "pn_confidence": cc.pn_confidence,
            "image_confidence": cc.image_confidence,
            "price_confidence": cc.price_confidence,
            "overall": cc.overall,
            "overall_label": confidence_label(cc.overall),
            "publishability": cc.publishability,
            "notes": cc.notes,
        }

    bundle = {
        "schema_version": "1.2",
        "generated_at": run_ts,
        "pn": pn,
        "pn_variants": pn_variants or [],
        "brand": brand,
        "subbrand": subbrand,
        "name": name,
        "assembled_title": assembled_title,
        "our_price_raw": our_price_raw,
        "expected_category": expected_category,

        "card_status": card_status,
        "review_reasons": review_reasons,
        "policy_decision_v2": decision_record_v2,
        "field_statuses_v2": {
            "title_status": decision_record_v2["title_status"],
            "image_status": decision_record_v2["image_status"],
            "price_status": decision_record_v2["price_status"],
            "pdf_status": decision_record_v2["pdf_status"],
        },
        "review_reasons_v2": decision_record_v2["review_reasons"],
        "confidence": confidence_block,
        "evidence_paths": evidence_paths,

        "photo": {
            "verdict": photo_verdict,
            "verdict_reason": guarded_vision_verdict.get("reason", ""),
            **photo_contract,
            "path": photo_result.get("path", ""),
            "sha1": sha1,
            "canonical_filename": canon_fn,
            "public_url": None,        # set by storage adapter
            "width": photo_result.get("width", 0),
            "height": photo_result.get("height", 0),
            "size_kb": photo_result.get("size_kb", 0),
            "source": photo_result.get("source", ""),
            "phash": photo_result.get("phash", ""),
            "stock_photo_flag": bool(photo_result.get("stock_photo_flag")),
            "mpn_confirmed_via_jsonld": bool(photo_result.get("mpn_confirmed")),
            "numeric_keep_guard_applied": bool(guarded_vision_verdict.get("numeric_keep_guard_applied")),
            "numeric_keep_guard_reasons": list(guarded_vision_verdict.get("numeric_keep_guard_reasons", [])),
        },

        "price": {
            "price_status": price_status,
            "price_admissibility_schema_version": guarded_price_result.get("price_admissibility_schema_version", ""),
            "string_lineage_status": guarded_price_result.get("string_lineage_status", ""),
            "commercial_identity_status": guarded_price_result.get("commercial_identity_status", ""),
            "offer_admissibility_status": guarded_price_result.get("offer_admissibility_status", ""),
            "staleness_or_conflict_status": guarded_price_result.get("staleness_or_conflict_status", ""),
            "price_admissibility_reason_codes": list(guarded_price_result.get("price_admissibility_reason_codes", [])),
            "price_admissibility_review_bucket": guarded_price_result.get("price_admissibility_review_bucket", ""),
            "price_admissibility_review_required": bool(
                guarded_price_result.get("price_admissibility_review_required")
            ),
            "queue_price_status": guarded_price_result.get("queue_price_status", ""),
            "historical_state_price_status": guarded_price_result.get("historical_state_price_status", ""),
            "price_per_unit": guarded_price_result.get("price_usd"),
            "currency": guarded_price_result.get("currency"),
            "rub_price": guarded_price_result.get("rub_price"),
            "fx_rate_used": guarded_price_result.get("fx_rate_used"),
            "fx_provider": guarded_price_result.get("fx_provider"),
            "price_confidence": guarded_price_result.get("price_confidence", 0),
            "price_observed_at": price_observation["price_observed_at"],
            "price_observed_date": price_observation["price_observed_date"],
            "price_date": price_observation["price_observed_date"],
            "price_observation_origin": price_observation["price_observation_origin"],
            "source_url": guarded_price_result.get("source_url"),
            "source_type": guarded_price_result.get("source_type"),
            "source_tier": guarded_price_result.get("source_tier"),
            "source_engine": guarded_price_result.get("source_engine", ""),
            "stock_status": guarded_price_result.get("stock_status", "unknown"),
            "offer_unit_basis": guarded_price_result.get("offer_unit_basis", "unknown"),
            "offer_qty": guarded_price_result.get("offer_qty"),
            "lead_time_detected": bool(guarded_price_result.get("lead_time_detected")),
            "quote_cta_url": guarded_price_result.get("quote_cta_url"),
            "suffix_conflict": bool(guarded_price_result.get("suffix_conflict")),
            "category_mismatch": bool(guarded_price_result.get("category_mismatch")),
            "page_product_class": guarded_price_result.get("page_product_class", ""),
            "brand_mismatch": bool(guarded_price_result.get("brand_mismatch")),
            "price_median_clean": guarded_price_result.get("price_median_clean"),
            "price_min_clean": guarded_price_result.get("price_min_clean"),
            "price_max_clean": guarded_price_result.get("price_max_clean"),
            "price_sample_size": guarded_price_result.get("price_sample_size", 1),
            "pn_exact_confirmed": bool(guarded_price_result.get("pn_exact_confirmed")),
            "page_context_clean": bool(guarded_price_result.get("page_context_clean", True)),
            "price_source_seen": bool(guarded_price_result.get("price_source_seen")),
            "price_source_url": guarded_price_result.get("price_source_url"),
            "price_source_domain": guarded_price_result.get("price_source_domain", ""),
            "price_source_type": guarded_price_result.get("price_source_type", ""),
            "price_source_tier": guarded_price_result.get("price_source_tier", ""),
            "price_source_engine": guarded_price_result.get("price_source_engine", ""),
            "price_source_lineage_confirmed": bool(guarded_price_result.get("price_source_lineage_confirmed")),
            "price_source_exact_title_pn_match": bool(guarded_price_result.get("price_source_exact_title_pn_match")),
            "price_source_exact_h1_pn_match": bool(guarded_price_result.get("price_source_exact_h1_pn_match")),
            "price_source_exact_jsonld_pn_match": bool(guarded_price_result.get("price_source_exact_jsonld_pn_match")),
            "price_source_exact_product_context_match": bool(guarded_price_result.get("price_source_exact_product_context_match")),
            "price_source_structured_match_location": guarded_price_result.get("price_source_structured_match_location", ""),
            "price_source_clean_product_page": bool(guarded_price_result.get("price_source_clean_product_page")),
            "price_source_exact_product_lineage_confirmed": bool(guarded_price_result.get("price_source_exact_product_lineage_confirmed")),
            "price_source_lineage_reason_code": guarded_price_result.get("price_source_lineage_reason_code", ""),
            "price_lineage_schema_version": guarded_price_result.get("price_lineage_schema_version", ""),
            "price_source_replacement_candidate_found": bool(guarded_price_result.get("price_source_replacement_candidate_found")),
            "price_source_replacement_url": guarded_price_result.get("price_source_replacement_url", ""),
            "price_source_replacement_domain": guarded_price_result.get("price_source_replacement_domain", ""),
            "price_source_replacement_tier": guarded_price_result.get("price_source_replacement_tier", ""),
            "price_source_replacement_engine": guarded_price_result.get("price_source_replacement_engine", ""),
            "price_source_replacement_exact_lineage_confirmed": bool(guarded_price_result.get("price_source_replacement_exact_lineage_confirmed")),
            "price_source_replacement_match_location": guarded_price_result.get("price_source_replacement_match_location", ""),
            "price_source_admissible_replacement_confirmed": bool(guarded_price_result.get("price_source_admissible_replacement_confirmed")),
            "price_source_terminal_weak_lineage": bool(guarded_price_result.get("price_source_terminal_weak_lineage")),
            "price_source_replacement_reason_code": guarded_price_result.get("price_source_replacement_reason_code", ""),
            "price_source_replacement_schema_version": guarded_price_result.get("price_source_replacement_schema_version", ""),
            "price_source_surface_stable": bool(guarded_price_result.get("price_source_surface_stable")),
            "price_source_surface_seen_current_run": bool(guarded_price_result.get("price_source_surface_seen_current_run")),
            "price_source_surface_preserved_from_prior_run": bool(guarded_price_result.get("price_source_surface_preserved_from_prior_run")),
            "price_source_surface_drop_detected": bool(guarded_price_result.get("price_source_surface_drop_detected")),
            "price_source_surface_conflict_detected": bool(guarded_price_result.get("price_source_surface_conflict_detected")),
            "price_source_surface_preservation_reason_code": guarded_price_result.get("price_source_surface_preservation_reason_code", ""),
            "price_source_surface_drop_reason_code": guarded_price_result.get("price_source_surface_drop_reason_code", ""),
            "price_source_surface_conflict_reason_code": guarded_price_result.get("price_source_surface_conflict_reason_code", ""),
            "price_source_surface_preserved_source_run_id": guarded_price_result.get("price_source_surface_preserved_source_run_id", ""),
            "price_source_surface_preserved_bundle_ref": guarded_price_result.get("price_source_surface_preserved_bundle_ref", ""),
            "price_source_surface_stability_schema_version": guarded_price_result.get("price_source_surface_stability_schema_version", ""),
            "price_exact_product_page": bool(guarded_price_result.get("price_exact_product_page")),
            "price_page_context_clean": bool(guarded_price_result.get("price_page_context_clean", True)),
            "price_quote_required": bool(guarded_price_result.get("price_quote_required")),
            "price_rfq_only": bool(guarded_price_result.get("price_rfq_only")),
            "price_no_price_reason_code": guarded_price_result.get("price_no_price_reason_code", ""),
            "price_reviewable_no_price_candidate": bool(guarded_price_result.get("price_reviewable_no_price_candidate")),
            "price_source_observed_only": bool(guarded_price_result.get("price_source_observed_only")),
            "no_price_coverage_schema_version": guarded_price_result.get("no_price_coverage_schema_version", ""),
            "public_price_rejection_reasons": list(guarded_price_result.get("public_price_rejection_reasons", [])),
            "cache_fallback_used": bool(guarded_price_result.get("cache_fallback_used")),
            "cache_fallback_reason": normalized_cache_fallback_reason,
            "cache_schema_version": guarded_price_result.get("cache_schema_version", ""),
            "cache_policy_version": guarded_price_result.get("cache_policy_version", ""),
            "cache_source_run_id": guarded_price_result.get("cache_source_run_id", ""),
            "cache_bundle_ref": guarded_price_result.get("cache_bundle_ref", ""),
            "transient_failure_detected": bool(guarded_price_result.get("transient_failure_detected")),
            "transient_failure_codes": normalized_transient_failure_codes,
        },

        "datasheet": datasheet_result,

        "structured_identity": {
            "exact_jsonld_pn_match": bool(photo_result.get("exact_jsonld_pn_match")),
            "exact_title_pn_match": bool(photo_result.get("exact_title_pn_match")),
            "exact_h1_pn_match": bool(photo_result.get("exact_h1_pn_match")),
            "exact_product_context_pn_match": bool(photo_result.get("exact_product_context_pn_match")),
            "exact_structured_pn_match": bool(photo_result.get("exact_structured_pn_match")),
            "structured_pn_match_location": photo_result.get("structured_pn_match_location", ""),
        },
        "negative_evidence": negative_evidence,

        "content": {
            "specs": photo_result.get("specs") or {},
            "description": content_description,
            "description_source": content_description_source,
            "site_placement": str(content_seed.get("site_placement", "") or "").strip(),
            "product_type": str(content_seed.get("product_type", "") or "").strip(),
            "seed_name": str(content_seed.get("seed_name", "") or "").strip(),
        },

        "trace": {
            "pn_match_location": photo_result.get("pn_match_location", ""),
            "pn_match_confidence": photo_result.get("pn_match_confidence", 0),
            "pn_match_is_numeric": bool(photo_result.get("pn_match_is_numeric", False)),
            "numeric_pn_guard_triggered": bool(photo_result.get("numeric_pn_guard_triggered")),
            "brand_cooccurrence": bool(photo_result.get("brand_cooccurrence", True)),
            "jsonld_hit": bool(photo_result.get("mpn_confirmed")),
            "source_trust_weight": photo_result.get("source_trust_weight"),
            "structured_pn_match_location": photo_result.get("structured_pn_match_location", ""),
            "exact_structured_pn_match": bool(photo_result.get("exact_structured_pn_match")),
            "exact_jsonld_pn_match": bool(photo_result.get("exact_jsonld_pn_match")),
            "exact_title_pn_match": bool(photo_result.get("exact_title_pn_match")),
            "exact_h1_pn_match": bool(photo_result.get("exact_h1_pn_match")),
            "exact_product_context_pn_match": bool(photo_result.get("exact_product_context_pn_match")),
            "price_source_seen": bool(guarded_price_result.get("price_source_seen")),
            "price_source_lineage_confirmed": bool(guarded_price_result.get("price_source_lineage_confirmed")),
            "price_source_exact_product_lineage_confirmed": bool(guarded_price_result.get("price_source_exact_product_lineage_confirmed")),
            "price_source_lineage_reason_code": guarded_price_result.get("price_source_lineage_reason_code", ""),
            "price_source_admissible_replacement_confirmed": bool(guarded_price_result.get("price_source_admissible_replacement_confirmed")),
            "price_source_terminal_weak_lineage": bool(guarded_price_result.get("price_source_terminal_weak_lineage")),
            "price_source_replacement_reason_code": guarded_price_result.get("price_source_replacement_reason_code", ""),
            "price_source_surface_stable": bool(guarded_price_result.get("price_source_surface_stable")),
            "price_source_surface_preserved_from_prior_run": bool(guarded_price_result.get("price_source_surface_preserved_from_prior_run")),
            "price_source_surface_drop_detected": bool(guarded_price_result.get("price_source_surface_drop_detected")),
            "price_source_surface_conflict_detected": bool(guarded_price_result.get("price_source_surface_conflict_detected")),
            "price_source_surface_preservation_reason_code": guarded_price_result.get("price_source_surface_preservation_reason_code", ""),
            "price_source_surface_drop_reason_code": guarded_price_result.get("price_source_surface_drop_reason_code", ""),
            "price_source_surface_conflict_reason_code": guarded_price_result.get("price_source_surface_conflict_reason_code", ""),
            "price_observed_at": price_observation["price_observed_at"],
            "price_observed_date": price_observation["price_observed_date"],
            "price_date": price_observation["price_observed_date"],
            "price_observation_origin": price_observation["price_observation_origin"],
            "price_exact_product_page": bool(guarded_price_result.get("price_exact_product_page")),
            "price_reviewable_no_price_candidate": bool(guarded_price_result.get("price_reviewable_no_price_candidate")),
            "price_no_price_reason_code": guarded_price_result.get("price_no_price_reason_code", ""),
        },
    }
    try:
        bundle["verifier_shadow"] = build_verifier_shadow_record(bundle)
    except Exception as exc:  # noqa: BLE001
        bundle["verifier_shadow"] = {
            "schema_version": "catalog_verifier_shadow_record_v1",
            "policy_version": "catalog_verifier_policy_v1",
            "mode": "shadow",
            "feature_enabled": False,
            "trace_id": f"catalog_verifier:{pn}:{run_ts}",
            "idempotency_key": "",
            "router": {
                "should_route": False,
                "trigger_codes": [],
                "deterministic_card_status": decision_record_v2["card_status"],
                "deterministic_identity_level": decision_record_v2["identity_level"],
            },
            "decision_merger": {
                "final_decision_source": "deterministic_policy",
                "decision_effect": "none",
                "allow_auto_publish_unlock": False,
                "allow_verifier_override": False,
                "owner_approval_required_for_influence": True,
                "effective_card_status": decision_record_v2["card_status"],
            },
            "packet": None,
            "response": None,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "reasoning_tokens": 0,
                "estimated_cost_usd": 0.0,
            },
            "call_state": "shadow_error",
            "error": str(exc),
            "llm_request_id": "",
        }
    return bundle


# ── Write helpers ────────────────────────────────────────────────────────────────

def write_evidence_bundles(bundles: list[dict], evidence_dir: Path) -> None:
    """Write one JSON file per SKU into evidence_dir/."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for b in bundles:
        pn_safe = re.sub(r'[\\/:*?"<>|]', "_", b["pn"])
        path = evidence_dir / f"evidence_{pn_safe}.json"
        path.write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")


_BASE_FIELDS = [
    "Артикул", "Название", "Бренд", "Изображение",
    "Цена", "Валюта", "Статус цены", "Статус наличия",
    "Описание", "Описание развёрнутое", "Источник описания", "Размещение на сайте", "Тип товара",
    "Название RU (DR)", "Описание RU (DR)", "Цена DR", "Валюта DR", "Источник цены DR",
    "Изображение DR", "Категория DR",
    "Статус изображения", "Статус карточки", "Причины проверки",
]


def write_insales_export(
    bundles: list[dict],
    output_path: Path,
    base_photo_url: str = "",
) -> int:
    """Write InSales-compatible CSV export.

    Only AUTO_PUBLISH and REVIEW_REQUIRED cards are included.
    DRAFT_ONLY are excluded.

    Returns count of exported rows.
    """
    rows = []
    for b in bundles:
        if b["card_status"] == "DRAFT_ONLY":
            continue

        photo = b.get("photo", {})
        merchandising = b.get("merchandising", {})
        content = b.get("content", {})
        price = b.get("price", {})
        dr = b.get("deep_research", {})

        # Photo URL
        photo_url = ""
        if merchandising.get("image_local_path"):
            photo_url = f"[LOCAL:{merchandising['image_local_path']}]"
        elif photo.get("canonical_filename") and base_photo_url:
            photo_url = f"{base_photo_url.rstrip('/')}/{photo['canonical_filename']}"
        elif (
            photo.get("path")
            and str(photo.get("verdict", "") or "").strip().upper() != "REJECT"
            and str(photo.get("photo_status", "") or "").strip().lower() != "rejected"
        ):
            photo_url = f"[LOCAL:{photo['path']}]"

        # Price — RUB if converted, else original
        price_val = price.get("rub_price") or price.get("price_per_unit")
        price_currency = "RUB" if price.get("rub_price") else (price.get("currency") or "")

        # Use assembled_title (H-lite) when available, fallback to raw name
        title_for_export = b.get("assembled_title") or b["name"]

        row: dict = {
            "Артикул":            b["pn"],
            "Название":           title_for_export,
            "Бренд":              b["brand"],
            "Изображение":        photo_url,
            "Цена":               str(price_val) if price_val else "",
            "Валюта":             price_currency,
            "Статус цены":        price.get("price_status", ""),
            "Статус наличия":     price.get("stock_status", ""),
            "Описание":           (content.get("description") or "")[:500],
            "Описание развёрнутое": (content.get("description_long_ru") or "")[:2000],
            "Источник описания":  content.get("description_source", ""),
            "Размещение на сайте": content.get("site_placement", ""),
            "Тип товара":         content.get("product_type", ""),
            "Название RU (DR)":   (dr.get("title_ru") or b.get("dr_category") or "")[:200],
            "Описание RU (DR)":   (dr.get("description_ru") or "")[:2000],
            "Цена DR":            str(b.get("dr_price") or "") if b.get("dr_price") else "",
            "Валюта DR":          b.get("dr_currency", ""),
            "Источник цены DR":   b.get("dr_price_source", ""),
            "Изображение DR":     b.get("dr_image_url", ""),
            "Категория DR":       b.get("dr_category", ""),
            "Статус изображения": merchandising.get("image_status") or photo.get("photo_status", ""),
            "Статус карточки":    b["card_status"],
            "Причины проверки":   "; ".join(b.get("review_reasons", [])),
        }

        # Specs as additional columns
        for k, v in (content.get("specs") or {}).items():
            col_name = f"Характеристика: {k}"
            row[col_name] = str(v)[:200]

        rows.append(row)

    if not rows:
        return 0

    # Collect all columns (preserve order)
    all_cols: list[str] = []
    seen: set[str] = set()
    for f in _BASE_FIELDS:
        if f not in seen:
            all_cols.append(f)
            seen.add(f)
    for row in rows:
        for f in row:
            if f not in seen:
                all_cols.append(f)
                seen.add(f)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def write_audit_report(
    bundles: list[dict],
    output_path: Path,
    run_meta: dict,
) -> dict:
    """Write audit_report.json and return summary dict."""
    total = len(bundles)

    def count(pred) -> int:
        return sum(1 for b in bundles if pred(b))

    def pct(n: int) -> str:
        return f"{n / total * 100:.1f}%" if total else "0%"

    auto_pub = count(lambda b: b["card_status"] == "AUTO_PUBLISH")
    review_req = count(lambda b: b["card_status"] == "REVIEW_REQUIRED")
    draft = count(lambda b: b["card_status"] == "DRAFT_ONLY")

    keep = count(lambda b: b["photo"]["verdict"] == "KEEP")
    public_price = count(lambda b: b["price"]["price_status"] == "public_price")
    rfq = count(lambda b: b["price"]["price_status"] == "rfq_only")
    cat_mismatch = count(lambda b: b["price"]["category_mismatch"])
    no_price = count(lambda b: b["price"]["price_status"] in ("no_price_found", ""))
    datasheet_found = count(lambda b: (b.get("datasheet") or {}).get("datasheet_status") == "found")
    numeric_guard = count(lambda b: b["trace"].get("numeric_pn_guard_triggered"))
    stock_flag = count(lambda b: b["photo"].get("stock_photo_flag"))
    suffix_conflict = count(lambda b: b["price"].get("suffix_conflict"))

    summary = {
        "run_meta": run_meta,
        "total_sku": total,
        "photo": {
            "keep": keep, "keep_rate": pct(keep),
            "reject": total - keep - count(lambda b: b["photo"]["verdict"] == "NO_PHOTO"),
            "no_photo": count(lambda b: b["photo"]["verdict"] == "NO_PHOTO"),
        },
        "price": {
            "public_price": public_price,
            "rfq_only": rfq,
            "no_price_found": no_price,
            "category_mismatch_isolated": cat_mismatch,
        },
        "datasheet": {"found": datasheet_found},
        "cards": {
            "auto_publish": auto_pub, "auto_publish_rate": pct(auto_pub),
            "review_required": review_req,
            "draft_only": draft,
        },
        "flags": {
            "numeric_pn_guard_triggered": numeric_guard,
            "stock_photo_flag": stock_flag,
            "suffix_conflict": suffix_conflict,
            "category_mismatch": cat_mismatch,
        },
    }

    per_sku = [
        {
            "pn": b["pn"],
            "name": b["name"][:60],
            "card_status": b["card_status"],
            "photo_verdict": b["photo"]["verdict"],
            "price_status": b["price"]["price_status"],
            "review_reasons": b.get("review_reasons", []),
        }
        for b in bundles
    ]

    report = {**summary, "per_sku": per_sku}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
