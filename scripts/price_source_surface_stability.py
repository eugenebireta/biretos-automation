"""Deterministic stability helpers for no-price source-surface preservation.

This layer does not invent price and does not override current-run truth. It
materializes whether previously seen compatible no-price source surface can be
preserved explicitly across bounded reruns when the current run drops it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PRICE_SOURCE_SURFACE_STABILITY_SCHEMA_VERSION = "price_source_surface_stability_v1"
CURRENT_SURFACE_POLICY_VERSION = "catalog_evidence_policy_v1"
_ADMISSIBLE_TIERS = {"official", "authorized", "industrial"}
_NO_PRICE_STATUSES = {"no_price_found", "hidden_price"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def _domain(url: Any) -> str:
    if not url:
        return ""
    return (urlparse(str(url)).netloc or "").lower().removeprefix("www.")


def _tier_rank(value: Any) -> int:
    tier = _normalized(value)
    if tier == "official":
        return 3
    if tier == "authorized":
        return 2
    if tier == "industrial":
        return 1
    return 0


def _surface_url(price: dict[str, Any]) -> str:
    return str(price.get("price_source_url") or price.get("source_url") or "")


def _surface_type(price: dict[str, Any], observed_candidate: dict[str, Any] | None = None) -> str:
    observed = dict(observed_candidate or {})
    return str(price.get("price_source_type") or price.get("source_type") or observed.get("source_type") or "")


def _surface_engine(price: dict[str, Any], observed_candidate: dict[str, Any] | None = None) -> str:
    observed = dict(observed_candidate or {})
    return str(price.get("price_source_engine") or price.get("source_engine") or observed.get("engine") or "")


def _surface_tier(price: dict[str, Any], observed_candidate: dict[str, Any] | None = None) -> str:
    observed = dict(observed_candidate or {})
    return str(price.get("price_source_tier") or price.get("source_tier") or observed.get("source_tier") or "")


def _is_surface_cacheable_bundle(bundle: dict[str, Any]) -> bool:
    price = dict(bundle.get("price") or {})
    decision = dict(bundle.get("policy_decision_v2") or {})
    source_url = _surface_url(price)

    return all(
        (
            decision.get("policy_version") == CURRENT_SURFACE_POLICY_VERSION,
            bool(source_url),
            bool(
                price.get("price_source_seen")
                or price.get("price_source_exact_product_lineage_confirmed")
                or price.get("price_source_terminal_weak_lineage")
            ),
        )
    )


def build_surface_cache_entry_from_bundle(
    bundle: dict[str, Any],
    *,
    source_run_id: str,
    bundle_ref: str,
) -> dict[str, Any] | None:
    if not _is_surface_cacheable_bundle(bundle):
        return None

    price = dict(bundle.get("price") or {})
    decision = dict(bundle.get("policy_decision_v2") or {})
    source_url = _surface_url(price)

    return {
        "schema_version": PRICE_SOURCE_SURFACE_STABILITY_SCHEMA_VERSION,
        "pn_primary": bundle.get("pn", ""),
        "source_url": source_url,
        "source_domain": _domain(source_url),
        "source_type": price.get("price_source_type") or price.get("source_type") or "",
        "source_tier": price.get("price_source_tier") or price.get("source_tier") or "",
        "source_engine": price.get("price_source_engine") or price.get("source_engine") or "",
        "price_status": price.get("price_status", ""),
        "price_source_seen": bool(price.get("price_source_seen")),
        "price_source_exact_title_pn_match": bool(price.get("price_source_exact_title_pn_match")),
        "price_source_exact_h1_pn_match": bool(price.get("price_source_exact_h1_pn_match")),
        "price_source_exact_jsonld_pn_match": bool(price.get("price_source_exact_jsonld_pn_match")),
        "price_source_exact_product_context_match": bool(price.get("price_source_exact_product_context_match")),
        "price_source_structured_match_location": price.get("price_source_structured_match_location", ""),
        "price_source_clean_product_page": bool(price.get("price_source_clean_product_page")),
        "price_source_exact_product_lineage_confirmed": bool(price.get("price_source_exact_product_lineage_confirmed")),
        "price_source_lineage_reason_code": price.get("price_source_lineage_reason_code", ""),
        "price_lineage_schema_version": price.get("price_lineage_schema_version", ""),
        "price_no_price_reason_code": price.get("price_no_price_reason_code", ""),
        "no_price_coverage_schema_version": price.get("no_price_coverage_schema_version", ""),
        "policy_version": decision.get("policy_version"),
        "source_run_id": source_run_id,
        "bundle_ref": bundle_ref,
        "bundle_generated_at": bundle.get("generated_at"),
    }


def build_source_surface_cache_payload_from_run_dirs(run_dirs: list[Path]) -> dict[str, Any]:
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
            entry = build_surface_cache_entry_from_bundle(
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
        "schema_version": PRICE_SOURCE_SURFACE_STABILITY_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "policy_version": CURRENT_SURFACE_POLICY_VERSION,
        "runs_indexed": [run_dir.name for run_dir in normalized_dirs],
        "entry_count": len(entries),
        "entries_by_pn": by_pn,
    }


def _candidate_compatible_with_entry(
    *,
    current_url: str,
    current_domain: str,
    current_type: str,
    current_engine: str,
    entry: dict[str, Any],
) -> bool:
    entry_url = str(entry.get("source_url") or "")
    entry_domain = str(entry.get("source_domain") or "")
    entry_type = str(entry.get("source_type") or "")
    entry_engine = str(entry.get("source_engine") or "")

    if current_url and current_url == entry_url:
        return True
    if current_domain and current_domain == entry_domain and current_type == entry_type:
        if not current_engine or not entry_engine or current_engine == entry_engine:
            return True
    return False


def select_prior_admissible_surface_candidate(
    *,
    pn: str,
    current_price_result: dict[str, Any] | None,
    surface_cache_payload: dict[str, Any] | None,
    expected_policy_version: str = CURRENT_SURFACE_POLICY_VERSION,
) -> dict[str, Any] | None:
    if not surface_cache_payload:
        return None
    if surface_cache_payload.get("schema_version") != PRICE_SOURCE_SURFACE_STABILITY_SCHEMA_VERSION:
        return None
    if surface_cache_payload.get("policy_version") != expected_policy_version:
        return None

    current = dict(current_price_result or {})
    current_rank = _tier_rank(current.get("price_source_tier") or current.get("source_tier"))
    current_url = _surface_url(current)

    best_entry: dict[str, Any] | None = None
    best_score: tuple[int, int, int, int, str, str] | None = None
    for entry in surface_cache_payload.get("entries_by_pn", {}).get(pn, []):
        if entry.get("policy_version") != expected_policy_version:
            continue
        if not entry.get("price_source_exact_product_lineage_confirmed"):
            continue
        entry_rank = _tier_rank(entry.get("source_tier"))
        if entry_rank == 0 or _normalized(entry.get("source_tier")) not in _ADMISSIBLE_TIERS:
            continue
        if entry_rank <= current_rank:
            continue
        if current_url and str(entry.get("source_url") or "") == current_url:
            continue

        score = (
            entry_rank,
            1 if entry.get("price_source_clean_product_page") else 0,
            1 if entry.get("price_source_exact_jsonld_pn_match") else 0,
            1 if any(
                (
                    entry.get("price_source_exact_title_pn_match"),
                    entry.get("price_source_exact_h1_pn_match"),
                    entry.get("price_source_exact_product_context_match"),
                )
            )
            else 0,
            str(entry.get("bundle_generated_at") or ""),
            str(entry.get("source_run_id") or ""),
        )
        if best_score is None or score > best_score:
            best_score = score
            best_entry = entry

    if best_entry is None:
        return None

    return {
        "price_source_url": best_entry.get("source_url", ""),
        "price_source_tier": best_entry.get("source_tier", ""),
        "price_source_engine": best_entry.get("source_engine", ""),
        "price_source_exact_product_lineage_confirmed": bool(
            best_entry.get("price_source_exact_product_lineage_confirmed")
        ),
        "price_source_clean_product_page": bool(best_entry.get("price_source_clean_product_page")),
        "price_source_exact_title_pn_match": bool(best_entry.get("price_source_exact_title_pn_match")),
        "price_source_exact_h1_pn_match": bool(best_entry.get("price_source_exact_h1_pn_match")),
        "price_source_exact_jsonld_pn_match": bool(best_entry.get("price_source_exact_jsonld_pn_match")),
        "price_source_exact_product_context_match": bool(
            best_entry.get("price_source_exact_product_context_match")
        ),
        "price_source_structured_match_location": best_entry.get(
            "price_source_structured_match_location", ""
        ),
        "price_source_replacement_candidate_found": True,
        "price_source_replacement_from_prior_surface_cache": True,
        "price_source_replacement_source_run_id": best_entry.get("source_run_id", ""),
        "price_source_replacement_bundle_ref": best_entry.get("bundle_ref", ""),
    }


def should_reuse_prior_admissible_surface(
    current_price_result: dict[str, Any] | None,
    *,
    transient_failure_detected: bool = False,
) -> bool:
    current = dict(current_price_result or {})
    price_status = _normalized(current.get("price_status", ""))
    current_tier = _normalized(current.get("price_source_tier") or current.get("source_tier"))
    lineage_reason = str(current.get("price_source_lineage_reason_code", "") or "")

    if price_status not in _NO_PRICE_STATUSES:
        return False
    if current.get("price_reviewable_no_price_candidate", False):
        return False
    if not current.get("price_source_exact_product_lineage_confirmed", False):
        return False
    if current_tier in _ADMISSIBLE_TIERS:
        return False
    if transient_failure_detected:
        return True
    if current.get("price_source_surface_conflict_detected", False):
        return True
    return bool(
        current.get("price_source_surface_stable", False)
        and lineage_reason.endswith("_weak_tier")
    )


def materialize_source_surface_stability(
    price_result: dict[str, Any] | None,
    *,
    pn: str,
    surface_cache_payload: dict[str, Any] | None,
    observed_candidate: dict[str, Any] | None = None,
    expected_policy_version: str = CURRENT_SURFACE_POLICY_VERSION,
) -> dict[str, Any]:
    result = dict(price_result or {})
    observed = dict(observed_candidate or {})
    result.setdefault(
        "price_source_surface_stability_schema_version",
        PRICE_SOURCE_SURFACE_STABILITY_SCHEMA_VERSION,
    )
    result.setdefault("price_source_surface_stable", False)
    result.setdefault("price_source_surface_seen_current_run", False)
    result.setdefault("price_source_surface_preserved_from_prior_run", False)
    result.setdefault("price_source_surface_drop_detected", False)
    result.setdefault("price_source_surface_conflict_detected", False)
    result.setdefault("price_source_surface_preservation_reason_code", "")
    result.setdefault("price_source_surface_drop_reason_code", "")
    result.setdefault("price_source_surface_conflict_reason_code", "")
    result.setdefault("price_source_surface_preserved_source_run_id", "")
    result.setdefault("price_source_surface_preserved_bundle_ref", "")

    if not surface_cache_payload:
        result["price_source_surface_preservation_reason_code"] = "no_prior_surface_available"
        return result
    if surface_cache_payload.get("schema_version") != PRICE_SOURCE_SURFACE_STABILITY_SCHEMA_VERSION:
        result["price_source_surface_preservation_reason_code"] = "surface_cache_schema_mismatch"
        return result
    if surface_cache_payload.get("policy_version") != expected_policy_version:
        result["price_source_surface_preservation_reason_code"] = "surface_cache_policy_mismatch"
        return result

    prior_entries = [
        entry
        for entry in surface_cache_payload.get("entries_by_pn", {}).get(pn, [])
        if entry.get("policy_version") == expected_policy_version
        and entry.get("price_source_exact_product_lineage_confirmed")
    ]
    if not prior_entries:
        result["price_source_surface_preservation_reason_code"] = "no_prior_surface_available"
        return result

    current_url = _surface_url(result)
    current_domain = str(result.get("price_source_domain") or _domain(current_url) or _domain(observed.get("url")))
    current_type = _surface_type(result, observed)
    current_engine = _surface_engine(result, observed)
    current_seen = bool(result.get("price_source_seen") or current_url)

    if current_seen:
        result["price_source_surface_seen_current_run"] = True
        compatible = next(
            (
                entry for entry in prior_entries
                if _candidate_compatible_with_entry(
                    current_url=current_url,
                    current_domain=current_domain,
                    current_type=current_type,
                    current_engine=current_engine,
                    entry=entry,
                )
            ),
            None,
        )
        if compatible is not None:
            result["price_source_surface_stable"] = True
            result["price_source_surface_preservation_reason_code"] = "current_surface_matches_prior"
            return result
        result["price_source_surface_conflict_detected"] = True
        result["price_source_surface_conflict_reason_code"] = "current_surface_conflicts_with_prior"
        result["price_source_surface_preservation_reason_code"] = "current_surface_conflicts_with_prior"
        return result

    observed_url = str(observed.get("url") or "")
    observed_domain = _domain(observed_url)
    observed_type = str(observed.get("source_type") or "")
    observed_engine = str(observed.get("engine") or "")
    if observed_url or observed_domain:
        compatible = next(
            (
                entry for entry in prior_entries
                if _candidate_compatible_with_entry(
                    current_url=observed_url,
                    current_domain=observed_domain,
                    current_type=observed_type,
                    current_engine=observed_engine,
                    entry=entry,
                )
            ),
            None,
        )
        if compatible is None:
            result["price_source_surface_drop_detected"] = True
            result["price_source_surface_conflict_detected"] = True
            result["price_source_surface_drop_reason_code"] = "current_observed_surface_incompatible_with_prior"
            result["price_source_surface_conflict_reason_code"] = "current_observed_surface_incompatible_with_prior"
            result["price_source_surface_preservation_reason_code"] = "current_observed_surface_incompatible_with_prior"
            return result

    entry = prior_entries[0]
    result.update(
        {
            "price_source_seen": True,
            "price_source_url": entry.get("source_url", ""),
            "price_source_domain": entry.get("source_domain", ""),
            "price_source_type": entry.get("source_type", ""),
            "price_source_tier": entry.get("source_tier", ""),
            "price_source_engine": entry.get("source_engine", ""),
            "source_url": result.get("source_url") or entry.get("source_url", ""),
            "source_type": result.get("source_type") or entry.get("source_type", ""),
            "source_tier": result.get("source_tier") or entry.get("source_tier", ""),
            "source_engine": result.get("source_engine") or entry.get("source_engine", ""),
            "price_source_exact_title_pn_match": bool(entry.get("price_source_exact_title_pn_match")),
            "price_source_exact_h1_pn_match": bool(entry.get("price_source_exact_h1_pn_match")),
            "price_source_exact_jsonld_pn_match": bool(entry.get("price_source_exact_jsonld_pn_match")),
            "price_source_exact_product_context_match": bool(entry.get("price_source_exact_product_context_match")),
            "price_source_structured_match_location": entry.get("price_source_structured_match_location", ""),
            "price_source_clean_product_page": bool(entry.get("price_source_clean_product_page")),
            "price_source_exact_product_lineage_confirmed": bool(entry.get("price_source_exact_product_lineage_confirmed")),
            "price_source_lineage_reason_code": entry.get("price_source_lineage_reason_code", ""),
            "price_lineage_schema_version": entry.get("price_lineage_schema_version", ""),
            "no_price_coverage_schema_version": entry.get("no_price_coverage_schema_version", ""),
            "price_source_surface_stable": True,
            "price_source_surface_preserved_from_prior_run": True,
            "price_source_surface_drop_detected": True,
            "price_source_surface_preservation_reason_code": "preserved_compatible_prior_surface",
            "price_source_surface_drop_reason_code": "current_run_surface_missing_prior_surface_preserved",
            "price_source_surface_preserved_source_run_id": entry.get("source_run_id", ""),
            "price_source_surface_preserved_bundle_ref": entry.get("bundle_ref", ""),
        }
    )
    return result
