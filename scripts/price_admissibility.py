"""Deterministic price admissibility layer for R1 price evidence.

This layer separates four concerns that were previously blended together:

- string lineage strength
- commercial product identity confidence
- offer admissibility verdict
- staleness / conflict truth state

The module is intentionally pure and replayable. It does not fetch data.
"""
from __future__ import annotations

import re
from typing import Any


PRICE_ADMISSIBILITY_SCHEMA_VERSION = "price_admissibility_v1"

STRING_LINEAGE_STATUSES = {"exact", "family", "weak", "none"}
COMMERCIAL_IDENTITY_STATUSES = {
    "exact_product",
    "family_or_series_only",
    "component_or_accessory",
    "pack_or_bundle_variant",
    "unclear",
}
OFFER_ADMISSIBILITY_STATUSES = {
    "admissible_public_price",
    "reference_price",
    "ambiguous_offer",
    "no_price_found",
    "blocked_or_auth_gated",
}
STALENESS_OR_CONFLICT_STATUSES = {
    "clean",
    "queue_manifest_conflict",
    "state_manifest_conflict",
    "stale_historical_claim",
    "unresolved_conflict",
}

_BLOCKED_HTTP_CODES = {401, 403, 407, 429, 498}
_COMPONENT_OR_ACCESSORY_TOKENS = (
    "accessor",
    "accessory",
    "adapter",
    "afdekking",
    "bracket",
    "cover",
    "cover frame",
    "frame",
    "mount",
    "mounting",
    "ramcek",
    "rozetka",
    "socket",
    "switch",
    "switchgear",
    "wip",
    "wipschakelaar",
)
_FAMILY_OR_SERIES_TOKENS = (
    "catalog",
    "comparison",
    "family",
    "listing",
    "matrix",
    "range",
    "search",
    "series",
)
_SEMANTIC_REASON_CODES = {
    "PRICE_COMPONENT_OR_ACCESSORY",
    "PRICE_PACK_UNIT_AMBIGUITY",
    "PRICE_FAMILY_SERIES_ONLY",
    "PRICE_SEMANTIC_IDENTITY_MISMATCH",
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _normalized_text(value) in {"1", "true", "yes", "y"}


def _int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _pick(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record.get(key) not in (None, ""):
            return record.get(key)
    return None


def _price_status(record: dict[str, Any]) -> str:
    return _normalized_text(_pick(record, "price_status", "offer_admissibility_status") or "no_price_found")


def _public_price_rejection_reasons(record: dict[str, Any]) -> list[str]:
    raw = record.get("public_price_rejection_reasons")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _structured_match_present(record: dict[str, Any]) -> bool:
    return any(
        (
            _bool(record.get("price_source_exact_title_pn_match")),
            _bool(record.get("price_source_exact_h1_pn_match")),
            _bool(record.get("price_source_exact_jsonld_pn_match")),
            _bool(record.get("price_source_exact_product_context_match")),
            bool(_normalized_text(record.get("price_source_structured_match_location"))),
        )
    )


def _price_signal_present(record: dict[str, Any]) -> bool:
    if _pick(record, "price_per_unit", "price_usd") is not None:
        return True
    if _pick(record, "source_price_value", "manual_source_price_value") is not None:
        return True
    return _price_status(record) in {"public_price", "rfq_only", "hidden_price", "ambiguous_offer"}


def _semantic_text(record: dict[str, Any]) -> str:
    parts = [
        _pick(record, "page_product_class") or "",
        _pick(record, "page_title") or "",
        _pick(record, "product_name") or "",
        _pick(record, "page_url") or "",
        _pick(record, "source_url") or "",
        _pick(record, "price_source_url") or "",
        _pick(record, "notes") or "",
    ]
    return " ".join(str(part) for part in parts if str(part).strip()).lower()


def _has_pack_or_bundle_ambiguity(record: dict[str, Any]) -> bool:
    unit_basis = _normalized_text(_pick(record, "offer_unit_basis", "source_offer_unit_basis") or "unknown")
    offer_qty = _pick(record, "offer_qty", "source_offer_qty")
    semantic_text = _semantic_text(record)
    if unit_basis in {"pack", "bundle", "kit"}:
        return True
    if any(token in semantic_text for token in (" pack", "bundle", " kit", "pieces", "piece set")):
        return True
    if offer_qty in (None, "", 1, "1"):
        return False
    try:
        return float(offer_qty) != 1.0
    except Exception:
        return True


def _is_blocked_or_auth_gated(record: dict[str, Any]) -> bool:
    if _bool(record.get("blocked_ui_detected")):
        return True
    http_status = _int(record.get("http_status"))
    if http_status in _BLOCKED_HTTP_CODES:
        return True
    return _price_status(record) in {"blocked_or_auth_gated", "blocked/auth-gated surface"}


def classify_string_lineage_status(record: dict[str, Any] | None) -> str:
    row = dict(record or {})
    reason_code = _normalized_text(row.get("price_source_lineage_reason_code"))
    exact_lineage = _bool(row.get("price_source_exact_product_lineage_confirmed"))

    if exact_lineage:
        if reason_code.endswith("_weak_tier"):
            return "weak"
        return "exact"
    if _structured_match_present(row):
        return "family"
    if _bool(row.get("price_source_seen")):
        return "weak"
    return "none"


def _word_match(token: str, text: str) -> bool:
    return bool(re.search(r"(?:^|[\s\-_/])" + re.escape(token) + r"(?:[\s\-_/.,;:!?]|$)", text))


def classify_commercial_identity_status(record: dict[str, Any] | None) -> str:
    row = dict(record or {})
    semantic_text = _semantic_text(row)
    if _has_pack_or_bundle_ambiguity(row) and _price_signal_present(row):
        return "pack_or_bundle_variant"
    if _bool(row.get("category_mismatch")) or _bool(row.get("brand_mismatch")):
        return "component_or_accessory"
    if any(_word_match(token, semantic_text) for token in _COMPONENT_OR_ACCESSORY_TOKENS):
        return "component_or_accessory"
    if any(_word_match(token, semantic_text) for token in _FAMILY_OR_SERIES_TOKENS):
        return "family_or_series_only"

    lineage = classify_string_lineage_status(row)
    if (
        lineage == "exact"
        and _bool(row.get("price_source_exact_product_lineage_confirmed"))
        and _bool(row.get("price_source_clean_product_page", True))
    ):
        return "exact_product"
    if lineage in {"exact", "family", "weak"}:
        return "family_or_series_only"
    return "unclear"


def classify_offer_admissibility_status(record: dict[str, Any] | None) -> str:
    row = dict(record or {})
    price_status = _price_status(row)
    lineage = classify_string_lineage_status(row)
    commercial_identity = classify_commercial_identity_status(row)
    rejection_reasons = set(_public_price_rejection_reasons(row))
    semantic_barrier = commercial_identity in {
        "family_or_series_only",
        "component_or_accessory",
        "pack_or_bundle_variant",
    }

    if price_status == "public_price":
        if lineage == "exact" and commercial_identity == "exact_product" and not rejection_reasons:
            return "admissible_public_price"
        if not semantic_barrier and rejection_reasons == {"source_tier_not_admissible"}:
            return "reference_price"
        return "ambiguous_offer"

    if _is_blocked_or_auth_gated(row):
        return "blocked_or_auth_gated"

    if price_status in {"rfq_only", "hidden_price"}:
        if commercial_identity == "exact_product":
            return "reference_price"
        return "ambiguous_offer"

    if price_status in {"ambiguous_offer", "category_mismatch_only"}:
        return "ambiguous_offer"

    if _price_signal_present(row):
        if commercial_identity == "exact_product" and not semantic_barrier:
            return "reference_price"
        return "ambiguous_offer"

    return "no_price_found"


def classify_staleness_or_conflict_status(record: dict[str, Any] | None) -> str:
    row = dict(record or {})
    explicit = _normalized_text(row.get("staleness_or_conflict_status"))
    if explicit in STALENESS_OR_CONFLICT_STATUSES:
        return explicit

    if _bool(row.get("price_source_surface_conflict_detected")):
        return "unresolved_conflict"

    current_offer_status = classify_offer_admissibility_status(row)
    queue_status = _normalized_text(row.get("queue_price_status"))
    historical_state_status = _normalized_text(
        _pick(row, "historical_state_price_status", "historical_claim_price_status", "state_price_status")
    )

    if historical_state_status:
        if historical_state_status in {"closed", "public_price"} and current_offer_status != "admissible_public_price":
            return "stale_historical_claim"
        if historical_state_status != current_offer_status:
            return "state_manifest_conflict"

    manifest_status = _price_status(row)
    if queue_status and queue_status != manifest_status:
        return "queue_manifest_conflict"

    return "clean"


def _reason_codes(
    *,
    record: dict[str, Any],
    string_lineage_status: str,
    commercial_identity_status: str,
    offer_admissibility_status: str,
    staleness_or_conflict_status: str,
) -> list[str]:
    reasons: list[str] = []
    if commercial_identity_status == "component_or_accessory":
        reasons.append("PRICE_COMPONENT_OR_ACCESSORY")
    if commercial_identity_status == "pack_or_bundle_variant":
        reasons.append("PRICE_PACK_UNIT_AMBIGUITY")
    if commercial_identity_status == "family_or_series_only":
        reasons.append("PRICE_FAMILY_SERIES_ONLY")
    if string_lineage_status == "exact" and commercial_identity_status != "exact_product":
        reasons.append("PRICE_SEMANTIC_IDENTITY_MISMATCH")
    if offer_admissibility_status == "blocked_or_auth_gated":
        reasons.append("PRICE_BLOCKED_OR_AUTH_GATED")
    if staleness_or_conflict_status == "queue_manifest_conflict":
        reasons.append("PRICE_QUEUE_MANIFEST_CONFLICT")
    if staleness_or_conflict_status == "state_manifest_conflict":
        reasons.append("PRICE_STATE_MANIFEST_CONFLICT")
    if staleness_or_conflict_status == "stale_historical_claim":
        reasons.append("PRICE_STALE_HISTORICAL_CLAIM")
    if staleness_or_conflict_status == "unresolved_conflict":
        reasons.append("PRICE_UNRESOLVED_CONFLICT")
    seen: set[str] = set()
    deduped: list[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            deduped.append(reason)
    return deduped


def _review_bucket(
    *,
    offer_admissibility_status: str,
    staleness_or_conflict_status: str,
    reason_codes: list[str],
) -> str:
    if staleness_or_conflict_status != "clean":
        return "STALE_TRUTH_REVIEW"
    if offer_admissibility_status == "blocked_or_auth_gated":
        return "PRICE_BLOCKED_SURFACE"
    if offer_admissibility_status in {"reference_price", "ambiguous_offer"}:
        return "PRICE_ADMISSIBILITY_REVIEW"
    if any(code in _SEMANTIC_REASON_CODES for code in reason_codes):
        return "PRICE_ADMISSIBILITY_REVIEW"
    return ""


def materialize_price_admissibility(
    record: dict[str, Any] | None,
    *,
    queue_price_status: str = "",
    historical_state_price_status: str = "",
) -> dict[str, Any]:
    row = dict(record or {})
    if queue_price_status and not row.get("queue_price_status"):
        row["queue_price_status"] = queue_price_status
    if historical_state_price_status and not row.get("historical_state_price_status"):
        row["historical_state_price_status"] = historical_state_price_status

    string_lineage_status = classify_string_lineage_status(row)
    commercial_identity_status = classify_commercial_identity_status(row)
    offer_admissibility_status = classify_offer_admissibility_status(row)
    staleness_or_conflict_status = classify_staleness_or_conflict_status(row)
    reason_codes = _reason_codes(
        record=row,
        string_lineage_status=string_lineage_status,
        commercial_identity_status=commercial_identity_status,
        offer_admissibility_status=offer_admissibility_status,
        staleness_or_conflict_status=staleness_or_conflict_status,
    )
    review_bucket = _review_bucket(
        offer_admissibility_status=offer_admissibility_status,
        staleness_or_conflict_status=staleness_or_conflict_status,
        reason_codes=reason_codes,
    )
    review_required = bool(
        review_bucket
        or offer_admissibility_status in {"reference_price", "ambiguous_offer", "blocked_or_auth_gated"}
        or staleness_or_conflict_status != "clean"
    )

    row.update(
        {
            "price_admissibility_schema_version": PRICE_ADMISSIBILITY_SCHEMA_VERSION,
            "string_lineage_status": string_lineage_status,
            "commercial_identity_status": commercial_identity_status,
            "offer_admissibility_status": offer_admissibility_status,
            "staleness_or_conflict_status": staleness_or_conflict_status,
            "price_admissibility_reason_codes": reason_codes,
            "price_admissibility_review_bucket": review_bucket,
            "price_admissibility_review_required": review_required,
        }
    )
    return row
