"""confidence.py — Explicit confidence aggregation formula for enrichment pipeline.

Design principles:
  - One formula, documented and testable — not scattered ad-hoc scores.
  - Multiplicative model: each factor is a weight in [0.0, 1.0].
    Final score = product of applicable weights, clamped to [0.0, 1.0].
  - Mismatch flags are hard penalties that can collapse a score to near-zero.
  - overall_card_publishability is NOT min(fields) — see note below.

Why NOT min() for overall:
  In B2B industrial, many products have no public price (RFQ only).
  Using min() would make overall_card_confidence low even when photo,
  description and PN are all confirmed. Instead, publishability is
  determined field-by-field with explicit conditions per field.

Confidence levels (for reference in human review):
  >= 0.85  HIGH    — strong evidence, likely AUTO_PUBLISH
  >= 0.60  MEDIUM  — usable but some uncertainty, likely REVIEW_REQUIRED
  >= 0.30  LOW     — weak evidence, likely REVIEW_REQUIRED or DRAFT_ONLY
  <  0.30  VERY_LOW — insufficient evidence
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Location base scores ─────────────────────────────────────────────────────

_PN_LOCATION_BASE: dict[str, float] = {
    "jsonld":           1.00,
    "title":            0.95,
    "h1":               0.92,
    "product_context":  0.85,
    "body":             0.70,   # alphanumeric body
    "":                 0.00,
}

# Numeric body match is penalized (collision risk)
_NUMERIC_BODY_BASE: float = 0.40

# ── Source trust weights ─────────────────────────────────────────────────────

_SOURCE_TRUST_WEIGHT: dict[str, float] = {
    "official":    1.00,
    "authorized":  0.90,
    "industrial":  0.75,
    "ru_b2b":      0.65,
    "aggregator":  0.40,
    "weak":        0.25,
    "unknown":     0.45,
}

# ── Mismatch penalties ────────────────────────────────────────────────────────

_BRAND_MISMATCH_PENALTY:    float = 0.20   # × score
_CATEGORY_MISMATCH_PENALTY: float = 0.30
_SUFFIX_CONFLICT_DISCOUNT:  float = 0.80   # mild discount, not a hard block

# ── Photo penalties ───────────────────────────────────────────────────────────

_BANNER_PENALTY:       float = 0.05
_STOCK_PHOTO_PENALTY:  float = 0.60
_TINY_IMAGE_PENALTY:   float = 0.30   # below MIN_DIM threshold
_JSONLD_IMAGE_BONUS:   float = 1.10   # capped at 1.0

# ── Price factors ─────────────────────────────────────────────────────────────

_AMBIGUOUS_UNIT_FACTOR:  float = 0.50
_UNKNOWN_VAT_DISCOUNT:   float = 0.90
_STALE_PRICE_FACTOR:     float = 0.70   # price older than STALE_MONTHS
STALE_MONTHS:            int   = 12

# ── Numeric guard ────────────────────────────────────────────────────────────

_NUMERIC_GUARD_FACTOR: float = 0.50   # body-only numeric match


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


# ══════════════════════════════════════════════════════════════════════════════
# PN Confidence
# ══════════════════════════════════════════════════════════════════════════════

def compute_pn_confidence(
    location: str,
    is_numeric: bool,
    source_tier: str,
    brand_cooccurrence: bool = True,
    brand_mismatch: bool = False,
    category_mismatch: bool = False,
    suffix_conflict: bool = False,
    numeric_guard_triggered: bool = False,
) -> float:
    """Compute PN confidence score in [0.0, 1.0].

    Args:
        location:             match location from pn_match.match_pn()
        is_numeric:           True if PN is all-digits / dotted-numeric
        source_tier:          trust tier from trust.get_source_tier()
        brand_cooccurrence:   brand name found near PN on page
        brand_mismatch:       page brand conflicts with expected brand
        category_mismatch:    page product class conflicts with expected category
        suffix_conflict:      page has suffix variant of PN (e.g. PN-EU)
        numeric_guard_triggered: pn_match flagged numeric guard

    Returns:
        float in [0.0, 1.0]
    """
    # Base score from match location
    if is_numeric and location == "body":
        base = _NUMERIC_BODY_BASE
    else:
        base = _PN_LOCATION_BASE.get(location, 0.0)

    if base == 0.0:
        return 0.0

    # Source trust weight
    trust = _SOURCE_TRUST_WEIGHT.get(source_tier, _SOURCE_TRUST_WEIGHT["unknown"])

    score = base * trust

    # Brand co-occurrence: if brand not found on page, reduce confidence
    if not brand_cooccurrence:
        score *= 0.60

    # Mismatch penalties
    if brand_mismatch:
        score *= _BRAND_MISMATCH_PENALTY
    if category_mismatch:
        score *= _CATEGORY_MISMATCH_PENALTY

    # Suffix conflict: mild discount
    if suffix_conflict:
        score *= _SUFFIX_CONFLICT_DISCOUNT

    return _clamp(score)


# ══════════════════════════════════════════════════════════════════════════════
# Image Confidence
# ══════════════════════════════════════════════════════════════════════════════

def compute_image_confidence(
    source_tier: str,
    pn_match_confidence: float,
    is_banner: bool = False,
    is_stock_photo: bool = False,
    is_tiny: bool = False,
    jsonld_image: bool = False,
    phash_consensus: bool = False,
    brand_mismatch: bool = False,
    category_mismatch: bool = False,
) -> float:
    """Compute image confidence score in [0.0, 1.0].

    Args:
        source_tier:          trust tier of page where image was found
        pn_match_confidence:  PN confidence on the source page [0.0, 1.0]
        is_banner:            image looks like a banner/header
        is_stock_photo:       same phash seen on many unrelated SKUs
        is_tiny:              image below minimum dimension threshold
        jsonld_image:         image URL came from JSON-LD Product.image
        phash_consensus:      2+ independent sources have similar image
        brand_mismatch:       page brand conflicts with expected brand
        category_mismatch:    page product class conflicts with expected category
    """
    if is_banner:
        return _BANNER_PENALTY

    trust = _SOURCE_TRUST_WEIGHT.get(source_tier, _SOURCE_TRUST_WEIGHT["unknown"])

    # Base: trust × page PN confidence
    score = trust * pn_match_confidence

    if is_tiny:
        score *= _TINY_IMAGE_PENALTY

    if is_stock_photo:
        score *= _STOCK_PHOTO_PENALTY

    # JSON-LD image is more authoritative
    if jsonld_image:
        score = _clamp(score * _JSONLD_IMAGE_BONUS)

    # Consensus from multiple sources boosts confidence
    if phash_consensus:
        score = _clamp(score * 1.20)

    # Mismatch penalties
    if brand_mismatch:
        score *= _BRAND_MISMATCH_PENALTY
    if category_mismatch:
        score *= _CATEGORY_MISMATCH_PENALTY

    return _clamp(score)


# ══════════════════════════════════════════════════════════════════════════════
# Price Confidence
# ══════════════════════════════════════════════════════════════════════════════

def compute_price_confidence(
    source_tier: str,
    pn_match_confidence: float,
    price_status: str,
    unit_basis: str = "piece",
    vat_basis_known: bool = True,
    is_stale: bool = False,
    brand_mismatch: bool = False,
    category_mismatch: bool = False,
    sample_size: int = 1,
) -> float:
    """Compute price confidence score in [0.0, 1.0].

    Args:
        source_tier:          trust tier of price source
        pn_match_confidence:  PN confidence on the price page [0.0, 1.0]
        price_status:         one of public_price / rfq_only / hidden_price /
                              no_price_found / ambiguous_offer / ambiguous_unit
        unit_basis:           piece / pack / kit / unknown
        vat_basis_known:      True if VAT inclusion is known
        is_stale:             price is older than STALE_MONTHS
        brand_mismatch:       page brand conflicts with expected brand
        category_mismatch:    page product class conflicts
        sample_size:          number of clean price candidates in consensus
    """
    if price_status in ("no_price_found", ""):
        return 0.0

    if price_status == "ambiguous_unit":
        return 0.10   # almost unusable

    if price_status in ("ambiguous_offer", "category_mismatch_only", "brand_mismatch_only"):
        return 0.10

    trust = _SOURCE_TRUST_WEIGHT.get(source_tier, _SOURCE_TRUST_WEIGHT["unknown"])
    score = trust * pn_match_confidence

    # RFQ / hidden price = lower commercial confidence but still valid
    if price_status == "rfq_only":
        score *= 0.80
    elif price_status == "hidden_price":
        score *= 0.50

    # Unit basis clarity
    if unit_basis == "unknown":
        score *= _AMBIGUOUS_UNIT_FACTOR
    elif unit_basis in ("pack", "kit"):
        score *= 0.80   # possible per-unit recalculation needed

    # VAT basis unknown: slight discount
    if not vat_basis_known:
        score *= _UNKNOWN_VAT_DISCOUNT

    # Stale price
    if is_stale:
        score *= _STALE_PRICE_FACTOR

    # Mismatch hard penalties
    if brand_mismatch:
        score *= _BRAND_MISMATCH_PENALTY
    if category_mismatch:
        score *= _CATEGORY_MISMATCH_PENALTY

    # Consensus bonus: multiple clean candidates reduce risk
    if sample_size >= 3:
        score = _clamp(score * 1.20)
    elif sample_size == 2:
        score = _clamp(score * 1.10)

    return _clamp(score)


# ══════════════════════════════════════════════════════════════════════════════
# Overall card publishability
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CardConfidence:
    pn_confidence: float = 0.0
    image_confidence: float = 0.0
    price_confidence: float = 0.0
    datasheet_confidence: float = 0.0
    overall: float = 0.0
    publishability: str = "DRAFT_ONLY"   # AUTO_PUBLISH / REVIEW_REQUIRED / DRAFT_ONLY
    notes: list[str] = field(default_factory=list)


# Thresholds
_PN_THRESHOLD:      float = 0.50
_IMAGE_THRESHOLD:   float = 0.40
_PRICE_THRESHOLD:   float = 0.40   # only required for AUTO_PUBLISH, not for REVIEW


def compute_card_confidence(
    pn_confidence: float,
    image_confidence: float,
    price_confidence: float,
    price_status: str,
    datasheet_confidence: float = 0.0,
    photo_verdict: str = "NO_PHOTO",
) -> CardConfidence:
    """Compute overall card confidence and publishability.

    Publishability logic (NOT min-based):
      AUTO_PUBLISH:
        - pn_confidence >= threshold
        - image_confidence >= threshold (photo KEEP)
        - price: public_price OR rfq_only with adequate price_confidence
        - no hard mismatch flags

      REVIEW_REQUIRED:
        - pn confirmed but image or price insufficient/uncertain
        - or image KEEP but price unclear
        - or rfq_only with low confidence

      DRAFT_ONLY:
        - pn not confirmed, or both image and price failed

    Note: rfq_only is VALID for B2B — not treated as "missing price".
    """
    cc = CardConfidence(
        pn_confidence=round(pn_confidence, 3),
        image_confidence=round(image_confidence, 3),
        price_confidence=round(price_confidence, 3),
        datasheet_confidence=round(datasheet_confidence, 3),
    )

    has_pn    = pn_confidence >= _PN_THRESHOLD
    has_image = image_confidence >= _IMAGE_THRESHOLD and photo_verdict == "KEEP"
    price_ok  = price_status in ("public_price", "rfq_only") and price_confidence >= _PRICE_THRESHOLD
    price_present = price_status not in ("no_price_found", "")

    # Weighted combination for overall score
    # PN is most important, then image, then price, then datasheet as bonus
    weights = [
        (pn_confidence,        0.40),
        (image_confidence,     0.30),
        (price_confidence,     0.20),
        (datasheet_confidence, 0.10),
    ]
    cc.overall = round(sum(v * w for v, w in weights), 3)

    # Publishability — per-field conditions, not min()
    if has_pn and has_image and price_ok:
        cc.publishability = "AUTO_PUBLISH"
        return cc

    if has_pn and (has_image or price_ok):
        cc.publishability = "REVIEW_REQUIRED"
        if not has_image:
            cc.notes.append("image_weak_or_missing")
        if not price_ok:
            if price_present:
                cc.notes.append("price_low_confidence")
            else:
                cc.notes.append("price_not_found")
        return cc

    if has_pn and not has_image and not price_present:
        cc.publishability = "REVIEW_REQUIRED"
        cc.notes.append("pn_confirmed_but_no_data")
        return cc

    cc.publishability = "DRAFT_ONLY"
    if not has_pn:
        cc.notes.append("pn_not_confirmed")
    if not has_image:
        cc.notes.append("no_usable_image")
    if not price_present:
        cc.notes.append("no_price_data")
    return cc


# ══════════════════════════════════════════════════════════════════════════════
# Human-readable confidence label
# ══════════════════════════════════════════════════════════════════════════════

def confidence_label(score: float) -> str:
    if score >= 0.85:
        return "HIGH"
    if score >= 0.60:
        return "MEDIUM"
    if score >= 0.30:
        return "LOW"
    return "VERY_LOW"
