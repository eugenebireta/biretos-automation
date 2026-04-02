"""Deterministic false-positive controls for Phase A sanity blockers.

This module is intentionally pure and replayable. It does not fetch data and
does not depend on runtime clients. The goal is to tighten two known blocker
families without widening scope:

1. false public-price admissibility on noisy / weak / ambiguous pages
2. unsafe KEEP outcomes for numeric or dotted-numeric PN cases without
   exact structured product identity
"""
from __future__ import annotations

from typing import Any

from pn_match import is_numeric_pn

_STRUCTURED_CONTEXTS = {"jsonld", "title", "h1", "product_context"}
_ADMISSIBLE_PUBLIC_PRICE_TIERS = {"official", "authorized", "industrial"}
_NOISY_PAGE_CLASS_TOKENS = (
    "accessor",
    "accessory",
    "bundle",
    "category",
    "comparison",
    "cover frame",
    "family",
    "kit",
    "listing",
    "matrix",
    "mount",
    "mounting",
    "pack",
    "replacement",
    "search",
    "socket",
    "spare",
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _has_noisy_page_product_class(page_product_class: Any) -> bool:
    norm = _normalized_text(page_product_class)
    return any(token in norm for token in _NOISY_PAGE_CLASS_TOKENS)


def _has_pack_or_unit_ambiguity(price_result: dict[str, Any]) -> bool:
    unit_basis = _normalized_text(price_result.get("offer_unit_basis", "unknown"))
    offer_qty = price_result.get("offer_qty")
    if unit_basis in {"pack", "kit", "unknown"}:
        return True
    if offer_qty in (None, 1):
        return False
    try:
        return float(offer_qty) != 1.0
    except Exception:
        return True


def tighten_public_price_result(price_result: dict[str, Any] | None) -> dict[str, Any]:
    """Downgrade unsafe public-price pages before legacy export decisions.

    Only explicit public_price candidates are tightened. RFQ-only is preserved.
    Public price stays admissible only when the page is clean, exact-product-like,
    and comes from an admissible tier with unambiguous unit semantics.
    """
    result = dict(price_result or {})
    price_status = _normalized_text(result.get("price_status", "no_price_found"))
    if price_status != "public_price":
        result.setdefault("public_price_rejection_reasons", [])
        result.setdefault("page_context_clean", not (
            bool(result.get("category_mismatch")) or
            bool(result.get("brand_mismatch")) or
            _has_noisy_page_product_class(result.get("page_product_class", ""))
        ))
        return result

    rejection_reasons: list[str] = []
    page_product_class = result.get("page_product_class", "")
    source_tier = _normalized_text(result.get("source_tier"))

    if bool(result.get("category_mismatch")) or bool(result.get("brand_mismatch")):
        rejection_reasons.append("category_or_brand_mismatch")
    if _has_noisy_page_product_class(page_product_class):
        rejection_reasons.append("noisy_page_context")
    if source_tier not in _ADMISSIBLE_PUBLIC_PRICE_TIERS:
        rejection_reasons.append("source_tier_not_admissible")
    if _has_pack_or_unit_ambiguity(result):
        rejection_reasons.append("ambiguous_pack_unit")

    page_context_clean = not any(
        reason in {"category_or_brand_mismatch", "noisy_page_context"}
        for reason in rejection_reasons
    )

    result["page_context_clean"] = page_context_clean
    result["public_price_rejection_reasons"] = rejection_reasons
    result["pn_exact_confirmed"] = bool(result.get("pn_exact_confirmed"))

    if not rejection_reasons:
        return result

    if any(reason in {"category_or_brand_mismatch", "noisy_page_context"} for reason in rejection_reasons):
        result["price_status"] = "category_mismatch_only"
    else:
        result["price_status"] = "ambiguous_offer"

    result["price_confidence"] = min(int(result.get("price_confidence") or 0), 25)
    return result


def apply_numeric_keep_guard(
    pn: str,
    photo_result: dict[str, Any] | None,
    vision_verdict: dict[str, Any] | None,
    price_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reject unsafe KEEP for numeric/dotted PN cases without exact context.

    For numeric/dotted PNs, a KEEP verdict is only allowed when exact structured
    product identity is already present in the parsed page evidence. Body/free-text
    matches are intentionally insufficient.
    """
    guarded = dict(vision_verdict or {})
    if _normalized_text(guarded.get("verdict")) != "keep":
        guarded.setdefault("numeric_keep_guard_applied", False)
        guarded.setdefault("numeric_keep_guard_reasons", [])
        return guarded
    if not is_numeric_pn(pn):
        guarded.setdefault("numeric_keep_guard_applied", False)
        guarded.setdefault("numeric_keep_guard_reasons", [])
        return guarded

    photo = dict(photo_result or {})
    price = dict(price_result or {})
    exact_context = any(
        (
            bool(photo.get("mpn_confirmed")),
            bool(photo.get("mpn_confirmed_via_jsonld")),
            bool(photo.get("exact_structured_pn_match")),
            _normalized_text(photo.get("structured_pn_match_location")) in _STRUCTURED_CONTEXTS,
            _normalized_text(photo.get("pn_match_location")) in _STRUCTURED_CONTEXTS,
        )
    )

    rejection_reasons: list[str] = []
    if not exact_context:
        rejection_reasons.append("missing_exact_structured_context")
    if bool(photo.get("stock_photo_flag")):
        rejection_reasons.append("stock_or_family_like_photo")
    if bool(price.get("category_mismatch")) or bool(price.get("brand_mismatch")):
        rejection_reasons.append("page_context_not_clean")
    if _has_noisy_page_product_class(price.get("page_product_class", "")):
        rejection_reasons.append("noisy_page_context")

    guarded["numeric_keep_guard_applied"] = bool(rejection_reasons)
    guarded["numeric_keep_guard_reasons"] = rejection_reasons

    if not rejection_reasons:
        return guarded

    guarded["verdict"] = "REJECT"
    guarded["reason"] = (
        "deterministic numeric/dotted PN guard: "
        + ", ".join(rejection_reasons)
    )
    return guarded
