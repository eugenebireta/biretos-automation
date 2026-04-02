"""Deterministic no-price source/page coverage helpers for bounded sanity runs.

This layer preserves upstream source lineage for exact-product price pages even
when no numeric public price is available. It does not invent prices and does
not override price admissibility. The goal is to separate:

- true no-source/no-evidence cases
- source-seen but unconfirmed cases
- exact-product no-price / quote-required cases that are reviewable later
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


NO_PRICE_COVERAGE_SCHEMA_VERSION = "no_price_coverage_v1"
_REVIEWABLE_TIERS = {"official", "authorized", "industrial"}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _domain(url: Any) -> str:
    if not url:
        return ""
    return (urlparse(str(url)).netloc or "").lower().removeprefix("www.")


def _tier_rank(value: Any) -> int:
    tier = _normalized_text(value)
    if tier == "official":
        return 3
    if tier == "authorized":
        return 2
    if tier == "industrial":
        return 1
    return 0


def _derive_no_price_reason_code(
    *,
    price_status: str,
    source_seen: bool,
    lineage_confirmed: bool,
    page_context_clean: bool,
    quote_required: bool,
    transient_failure_detected: bool,
) -> str:
    if price_status not in {"no_price_found", "hidden_price", "rfq_only", ""}:
        return ""
    if not source_seen:
        return "no_source_candidates"
    if transient_failure_detected and not lineage_confirmed:
        return "transient_failure_before_lineage"
    if not lineage_confirmed:
        return "source_seen_no_exact_page"
    if not page_context_clean:
        return "exact_page_context_not_clean"
    if price_status == "rfq_only":
        return "rfq_only"
    if quote_required:
        return "quote_required"
    return "no_visible_price_exact_page"


def materialize_no_price_coverage(
    price_result: dict[str, Any] | None,
    *,
    observed_candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add explicit no-price source/page coverage fields to a price result."""
    result = dict(price_result or {})
    observed = dict(observed_candidate or {})

    source_url = str(
        result.get("source_url")
        or result.get("price_source_url")
        or observed.get("url")
        or ""
    )
    source_type = str(
        result.get("source_type")
        or result.get("price_source_type")
        or observed.get("source_type")
        or ""
    )
    source_tier = str(
        result.get("source_tier")
        or result.get("price_source_tier")
        or observed.get("source_tier")
        or ""
    )
    source_engine = str(
        result.get("source_engine")
        or result.get("price_source_engine")
        or observed.get("engine")
        or ""
    )
    price_status = _normalized_text(result.get("price_status", "no_price_found"))
    explicit_lineage_confirmed = bool(
        result.get("price_source_lineage_confirmed")
        or result.get("price_source_exact_product_lineage_confirmed")
    )
    explicit_page_context_clean = (
        bool(result.get("price_page_context_clean"))
        if "price_page_context_clean" in result
        else bool(result.get("page_context_clean", True))
    )
    page_context_clean = explicit_page_context_clean
    pn_exact_confirmed = bool(result.get("pn_exact_confirmed"))
    category_mismatch = bool(result.get("category_mismatch"))
    brand_mismatch = bool(result.get("brand_mismatch"))
    quote_cta_url = str(result.get("quote_cta_url") or "")
    source_seen = bool(source_url)
    lineage_confirmed = explicit_lineage_confirmed or (
        bool(result.get("source_url") or result.get("price_source_url")) and pn_exact_confirmed
    )
    exact_product_page = (
        bool(result.get("price_exact_product_page"))
        if "price_exact_product_page" in result
        else (
            lineage_confirmed
            and not category_mismatch
            and not brand_mismatch
            and page_context_clean
        )
    )
    quote_required = bool(
        quote_cta_url
        or _normalized_text(result.get("stock_status")) == "rfq"
        or price_status in {"hidden_price", "rfq_only"}
    )
    no_price_reason_code = _derive_no_price_reason_code(
        price_status=price_status,
        source_seen=source_seen,
        lineage_confirmed=lineage_confirmed,
        page_context_clean=page_context_clean,
        quote_required=quote_required,
        transient_failure_detected=bool(result.get("transient_failure_detected")),
    )
    reviewable_no_price_candidate = bool(
        price_status in {"no_price_found", "hidden_price"}
        and exact_product_page
        and _tier_rank(source_tier) > 0
        and not result.get("public_price_rejection_reasons")
    )

    result["no_price_coverage_schema_version"] = NO_PRICE_COVERAGE_SCHEMA_VERSION
    result["price_source_seen"] = source_seen
    result["price_source_url"] = source_url
    result["price_source_domain"] = _domain(source_url)
    result["price_source_type"] = source_type
    result["price_source_tier"] = source_tier
    result["price_source_engine"] = source_engine
    result["price_source_lineage_confirmed"] = lineage_confirmed
    result["price_exact_product_page"] = exact_product_page
    result["price_page_context_clean"] = page_context_clean
    result["price_quote_required"] = quote_required
    result["price_rfq_only"] = price_status == "rfq_only"
    result["price_no_price_reason_code"] = no_price_reason_code
    result["price_reviewable_no_price_candidate"] = reviewable_no_price_candidate
    result["price_source_observed_only"] = source_seen and not lineage_confirmed
    return result


def choose_better_no_price_candidate(
    current: dict[str, Any] | None,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Pick the most useful explicit no-price lineage candidate deterministically."""
    if current is None:
        return candidate

    def score(item: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
        return (
            1 if item.get("price_reviewable_no_price_candidate") else 0,
            1 if item.get("price_source_lineage_confirmed") else 0,
            1 if item.get("price_quote_required") else 0,
            _tier_rank(item.get("price_source_tier")),
            int(item.get("price_confidence") or 0),
            1 if item.get("price_source_seen") else 0,
        )

    return candidate if score(candidate) > score(current) else current
