"""Deterministic cache-first helpers for bounded sanity price resilience.

The cache is not a source of truth. It is only a replay aid for bounded sanity
reruns when live deterministic price extraction fails transiently
(quota/rate-limit/timeout/temporary API failure). Cached evidence is eligible
only if it was already accepted under the current deterministic policy family
and its lineage is explicit.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from deterministic_false_positive_controls import tighten_public_price_result


PRICE_CACHE_SCHEMA_VERSION = "price_evidence_cache_v1"
CURRENT_PRICE_POLICY_VERSION = "catalog_evidence_policy_v1"
_ADMISSIBLE_TIERS = {"official", "authorized", "industrial"}
_TRANSIENT_FAILURE_CODES = {
    "llm_quota",
    "llm_rate_limit",
    "llm_temporary_failure",
    "llm_timeout",
}
_LEGACY_FAILURE_CODE_ALIASES = {
    "openai_quota": "llm_quota",
    "openai_rate_limit": "llm_rate_limit",
    "openai_temporary_failure": "llm_temporary_failure",
    "openai_timeout": "llm_timeout",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def _domain(url: Any) -> str:
    if not url:
        return ""
    return (urlparse(str(url)).netloc or "").lower().removeprefix("www.")


def _candidate_url_index(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(c.get("url") or ""): dict(c) for c in candidates if c.get("url")}


def _is_cacheable_bundle(bundle: dict[str, Any]) -> bool:
    price = dict(bundle.get("price") or {})
    decision = dict(bundle.get("policy_decision_v2") or {})
    field_statuses = dict(bundle.get("field_statuses_v2") or {})
    guarded = tighten_public_price_result(price)
    source_tier = _normalized(guarded.get("source_tier"))

    return all(
        (
            decision.get("policy_version") == CURRENT_PRICE_POLICY_VERSION,
            field_statuses.get("price_status") == "ACCEPTED",
            guarded.get("price_status") in {"public_price", "rfq_only"},
            bool(guarded.get("pn_exact_confirmed")),
            bool(guarded.get("page_context_clean")),
            not guarded.get("category_mismatch"),
            not guarded.get("brand_mismatch"),
            not guarded.get("public_price_rejection_reasons"),
            source_tier in _ADMISSIBLE_TIERS,
            bool(guarded.get("source_url")),
        )
    )


def build_cache_entry_from_bundle(
    bundle: dict[str, Any],
    *,
    source_run_id: str,
    bundle_ref: str,
) -> dict[str, Any] | None:
    """Extract one lineage-safe cache entry from a prior bounded-run bundle."""
    if not _is_cacheable_bundle(bundle):
        return None

    price = dict(bundle.get("price") or {})
    decision = dict(bundle.get("policy_decision_v2") or {})
    source_url = str(price.get("source_url") or "")

    return {
        "schema_version": PRICE_CACHE_SCHEMA_VERSION,
        "pn_primary": bundle.get("pn", ""),
        "price_status": price.get("price_status"),
        "price_per_unit": price.get("price_per_unit"),
        "currency": price.get("currency"),
        "rub_price": price.get("rub_price"),
        "fx_rate_used": price.get("fx_rate_used"),
        "fx_provider": price.get("fx_provider"),
        "price_confidence": price.get("price_confidence", 0),
        "source_url": source_url,
        "source_domain": _domain(source_url),
        "source_type": price.get("source_type"),
        "source_tier": price.get("source_tier"),
        "stock_status": price.get("stock_status", "unknown"),
        "offer_unit_basis": price.get("offer_unit_basis", "unknown"),
        "offer_qty": price.get("offer_qty"),
        "lead_time_detected": bool(price.get("lead_time_detected")),
        "suffix_conflict": bool(price.get("suffix_conflict")),
        "category_mismatch": bool(price.get("category_mismatch")),
        "brand_mismatch": bool(price.get("brand_mismatch")),
        "page_product_class": price.get("page_product_class", ""),
        "price_sample_size": price.get("price_sample_size", 1),
        "pn_exact_confirmed": bool(price.get("pn_exact_confirmed")),
        "exact_product_page": bool(price.get("pn_exact_confirmed")),
        "page_context_clean": bool(price.get("page_context_clean")),
        "public_price_rejection_reasons": list(price.get("public_price_rejection_reasons", [])),
        "policy_version": decision.get("policy_version"),
        "source_run_id": source_run_id,
        "bundle_ref": bundle_ref,
        "bundle_generated_at": bundle.get("generated_at"),
    }


def build_cache_payload_from_run_dirs(run_dirs: list[Path]) -> dict[str, Any]:
    """Seed a bounded-run cache from prior admissible evidence bundles."""
    entries: list[dict[str, Any]] = []
    normalized_dirs = [Path(run_dir) for run_dir in run_dirs]
    for run_dir in normalized_dirs:
        evidence_dir = run_dir / "evidence"
        if not evidence_dir.exists():
            continue
        for bundle_path in sorted(evidence_dir.glob("evidence_*.json")):
            try:
                bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            entry = build_cache_entry_from_bundle(
                bundle,
                source_run_id=run_dir.name,
                bundle_ref=str(bundle_path),
            )
            if entry is not None:
                entries.append(entry)

    entries.sort(
        key=lambda item: (
            str(item.get("bundle_generated_at") or ""),
            str(item.get("source_run_id") or ""),
            str(item.get("bundle_ref") or ""),
        ),
        reverse=True,
    )

    by_pn: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        by_pn.setdefault(entry["pn_primary"], []).append(entry)

    return {
        "schema_version": PRICE_CACHE_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "policy_version": CURRENT_PRICE_POLICY_VERSION,
        "runs_indexed": [run_dir.name for run_dir in normalized_dirs],
        "entry_count": len(entries),
        "entries_by_pn": by_pn,
    }


def select_cached_price_fallback(
    *,
    pn: str,
    candidates: list[dict[str, Any]],
    cache_payload: dict[str, Any] | None,
    failure_codes: list[str],
    expected_policy_version: str = CURRENT_PRICE_POLICY_VERSION,
) -> dict[str, Any] | None:
    """Reuse prior admissible price evidence only for transient bounded failures."""
    if not cache_payload:
        return None
    if cache_payload.get("schema_version") != PRICE_CACHE_SCHEMA_VERSION:
        return None
    if cache_payload.get("policy_version") != expected_policy_version:
        return None

    normalized_failure_codes = {
        _LEGACY_FAILURE_CODE_ALIASES.get(_normalized(code), _normalized(code))
        for code in failure_codes
    }
    if not normalized_failure_codes.intersection(_TRANSIENT_FAILURE_CODES):
        return None

    candidate_index = _candidate_url_index(candidates)
    if not candidate_index:
        return None

    for entry in cache_payload.get("entries_by_pn", {}).get(pn, []):
        if entry.get("policy_version") != expected_policy_version:
            continue
        source_url = str(entry.get("source_url") or "")
        candidate = candidate_index.get(source_url)
        if not candidate:
            continue
        if _normalized(candidate.get("source_tier")) != _normalized(entry.get("source_tier")):
            continue
        if entry.get("public_price_rejection_reasons"):
            continue
        if not entry.get("page_context_clean"):
            continue
        if not entry.get("exact_product_page"):
            continue

        return {
            "price_usd": entry.get("price_per_unit"),
            "currency": entry.get("currency"),
            "rub_price": entry.get("rub_price"),
            "fx_rate_used": entry.get("fx_rate_used"),
            "fx_provider": entry.get("fx_provider"),
            "source_url": source_url,
            "source_type": entry.get("source_type"),
            "source_tier": entry.get("source_tier"),
            "price_status": entry.get("price_status"),
            "price_confidence": entry.get("price_confidence", 0),
            "stock_status": entry.get("stock_status", "unknown"),
            "offer_unit_basis": entry.get("offer_unit_basis", "unknown"),
            "offer_qty": entry.get("offer_qty"),
            "lead_time_detected": bool(entry.get("lead_time_detected")),
            "suffix_conflict": bool(entry.get("suffix_conflict")),
            "category_mismatch": bool(entry.get("category_mismatch")),
            "page_product_class": entry.get("page_product_class", ""),
            "brand_mismatch": bool(entry.get("brand_mismatch")),
            "price_sample_size": entry.get("price_sample_size", 1),
            "pn_exact_confirmed": bool(entry.get("pn_exact_confirmed")),
            "page_context_clean": bool(entry.get("page_context_clean")),
            "public_price_rejection_reasons": list(entry.get("public_price_rejection_reasons", [])),
            "cache_fallback_used": True,
            "cache_fallback_reason": ",".join(sorted(normalized_failure_codes)),
            "transient_failure_codes": sorted(normalized_failure_codes),
            "cache_schema_version": PRICE_CACHE_SCHEMA_VERSION,
            "cache_policy_version": entry.get("policy_version"),
            "cache_source_run_id": entry.get("source_run_id"),
            "cache_bundle_ref": entry.get("bundle_ref"),
            "cache_source_domain": entry.get("source_domain"),
        }

    return None
