"""Deterministic admissible-source replacement helpers for no-price lineage.

This layer does not invent prices and does not relax routing. It only classifies
whether a weak exact-lineage no-price source has a stronger admissible exact
replacement candidate among the already-fetched deterministic candidate pages.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


PRICE_SOURCE_REPLACEMENT_SCHEMA_VERSION = "price_source_replacement_v1"
_ADMISSIBLE_TIERS = {"official", "authorized", "industrial"}


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


def choose_better_replacement_candidate(
    current: dict[str, Any] | None,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    if current is None:
        return candidate

    def score(item: dict[str, Any]) -> tuple[int, int, int, int]:
        return (
            _tier_rank(item.get("price_source_tier")),
            1 if item.get("price_source_exact_product_lineage_confirmed") else 0,
            1 if item.get("price_source_clean_product_page") else 0,
            1 if any(
                (
                    item.get("price_source_exact_title_pn_match"),
                    item.get("price_source_exact_h1_pn_match"),
                    item.get("price_source_exact_jsonld_pn_match"),
                    item.get("price_source_exact_product_context_match"),
                )
            )
            else 0,
        )

    return candidate if score(candidate) > score(current) else current


def materialize_source_replacement_surface(
    price_result: dict[str, Any] | None,
    *,
    admissible_replacement_candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = dict(price_result or {})
    current_tier = _normalized_text(result.get("price_source_tier") or result.get("source_tier"))
    current_exact_lineage = bool(result.get("price_source_exact_product_lineage_confirmed"))
    current_admissible = current_tier in _ADMISSIBLE_TIERS

    replacement = dict(admissible_replacement_candidate or {})
    replacement_confirmed = bool(
        (current_exact_lineage and current_admissible)
        or (
            replacement
            and replacement.get("price_source_exact_product_lineage_confirmed")
            and _normalized_text(replacement.get("price_source_tier")) in _ADMISSIBLE_TIERS
        )
    )

    result.update(
        {
            "price_source_replacement_candidate_found": bool(replacement),
            "price_source_replacement_url": replacement.get("price_source_url", ""),
            "price_source_replacement_domain": _domain(replacement.get("price_source_url", "")),
            "price_source_replacement_tier": replacement.get("price_source_tier", ""),
            "price_source_replacement_engine": replacement.get("price_source_engine", ""),
            "price_source_replacement_exact_lineage_confirmed": bool(
                replacement.get("price_source_exact_product_lineage_confirmed")
            ),
            "price_source_replacement_match_location": replacement.get(
                "price_source_structured_match_location", ""
            ),
            "price_source_admissible_replacement_confirmed": replacement_confirmed,
            "price_source_terminal_weak_lineage": bool(
                current_exact_lineage and not current_admissible and not replacement_confirmed
            ),
            "price_source_replacement_schema_version": PRICE_SOURCE_REPLACEMENT_SCHEMA_VERSION,
        }
    )

    if current_admissible:
        reason_code = "source_already_admissible"
    elif replacement_confirmed:
        reason_code = "admissible_replacement_confirmed"
    elif current_exact_lineage:
        reason_code = "weak_exact_lineage_no_admissible_replacement"
    else:
        reason_code = "no_exact_lineage_for_replacement"
    result["price_source_replacement_reason_code"] = reason_code
    return result
