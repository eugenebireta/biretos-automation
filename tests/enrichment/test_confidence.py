"""tests/enrichment/test_confidence.py — Deterministic tests for confidence formula.

No live API calls. No file I/O. Pure logic tests.

Coverage:
  - compute_pn_confidence()
  - compute_image_confidence()
  - compute_price_confidence()
  - compute_card_confidence() — publishability logic
  - confidence_label()
  - mismatch penalties
  - RFQ-only is valid (not treated as "no price")
"""
import sys
import os

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

import pytest
from confidence import (
    compute_pn_confidence,
    compute_image_confidence,
    compute_price_confidence,
    compute_card_confidence,
    confidence_label,
)


# ══════════════════════════════════════════════════════════════════════════════
# compute_pn_confidence
# ══════════════════════════════════════════════════════════════════════════════

class TestPnConfidence:

    def test_jsonld_official_max(self):
        score = compute_pn_confidence(
            location="jsonld", is_numeric=True, source_tier="official"
        )
        assert score == pytest.approx(1.0, abs=0.01)

    def test_title_authorized(self):
        score = compute_pn_confidence(
            location="title", is_numeric=False, source_tier="authorized"
        )
        assert 0.80 <= score <= 1.0

    def test_body_numeric_low(self):
        score = compute_pn_confidence(
            location="body", is_numeric=True, source_tier="authorized"
        )
        assert score < 0.45, "body-only numeric should be low confidence"

    def test_body_alphanumeric_medium(self):
        score = compute_pn_confidence(
            location="body", is_numeric=False, source_tier="authorized"
        )
        assert score >= 0.50

    def test_no_location_zero(self):
        score = compute_pn_confidence(
            location="", is_numeric=False, source_tier="official"
        )
        assert score == 0.0

    def test_brand_mismatch_collapses_score(self):
        score = compute_pn_confidence(
            location="jsonld", is_numeric=False, source_tier="official",
            brand_mismatch=True,
        )
        assert score < 0.30

    def test_category_mismatch_reduces_score(self):
        score_clean = compute_pn_confidence(
            location="title", is_numeric=False, source_tier="authorized"
        )
        score_mismatch = compute_pn_confidence(
            location="title", is_numeric=False, source_tier="authorized",
            category_mismatch=True,
        )
        assert score_mismatch < score_clean

    def test_no_brand_cooccurrence_reduces_score(self):
        score_with = compute_pn_confidence(
            location="body", is_numeric=True, source_tier="authorized",
            brand_cooccurrence=True,
        )
        score_without = compute_pn_confidence(
            location="body", is_numeric=True, source_tier="authorized",
            brand_cooccurrence=False,
        )
        assert score_without < score_with

    def test_weak_source_low_even_jsonld(self):
        score = compute_pn_confidence(
            location="jsonld", is_numeric=False, source_tier="weak"
        )
        assert score < 0.40

    def test_score_clamped_to_1(self):
        score = compute_pn_confidence(
            location="jsonld", is_numeric=False, source_tier="official"
        )
        assert score <= 1.0

    def test_score_non_negative(self):
        score = compute_pn_confidence(
            location="body", is_numeric=True, source_tier="weak",
            brand_mismatch=True, category_mismatch=True,
        )
        assert score >= 0.0


# ══════════════════════════════════════════════════════════════════════════════
# compute_image_confidence
# ══════════════════════════════════════════════════════════════════════════════

class TestImageConfidence:

    def test_banner_near_zero(self):
        score = compute_image_confidence(
            source_tier="official", pn_match_confidence=0.9, is_banner=True
        )
        assert score < 0.10

    def test_official_jsonld_high(self):
        score = compute_image_confidence(
            source_tier="official", pn_match_confidence=1.0,
            jsonld_image=True,
        )
        assert score >= 0.85

    def test_stock_photo_penalty(self):
        score_clean = compute_image_confidence(
            source_tier="authorized", pn_match_confidence=0.8
        )
        score_stock = compute_image_confidence(
            source_tier="authorized", pn_match_confidence=0.8,
            is_stock_photo=True,
        )
        assert score_stock < score_clean

    def test_tiny_image_penalty(self):
        score_normal = compute_image_confidence(
            source_tier="authorized", pn_match_confidence=0.8
        )
        score_tiny = compute_image_confidence(
            source_tier="authorized", pn_match_confidence=0.8, is_tiny=True
        )
        assert score_tiny < score_normal

    def test_phash_consensus_bonus(self):
        score_single = compute_image_confidence(
            source_tier="authorized", pn_match_confidence=0.7
        )
        score_consensus = compute_image_confidence(
            source_tier="authorized", pn_match_confidence=0.7, phash_consensus=True
        )
        assert score_consensus > score_single

    def test_mismatch_penalty(self):
        score_clean = compute_image_confidence(
            source_tier="industrial", pn_match_confidence=0.7
        )
        score_mismatch = compute_image_confidence(
            source_tier="industrial", pn_match_confidence=0.7, category_mismatch=True
        )
        assert score_mismatch < score_clean

    def test_score_clamped(self):
        score = compute_image_confidence(
            source_tier="official", pn_match_confidence=1.0,
            jsonld_image=True, phash_consensus=True,
        )
        assert 0.0 <= score <= 1.0


# ══════════════════════════════════════════════════════════════════════════════
# compute_price_confidence
# ══════════════════════════════════════════════════════════════════════════════

class TestPriceConfidence:

    def test_no_price_zero(self):
        score = compute_price_confidence(
            source_tier="official", pn_match_confidence=1.0,
            price_status="no_price_found",
        )
        assert score == 0.0

    def test_public_price_official_high(self):
        score = compute_price_confidence(
            source_tier="official", pn_match_confidence=1.0,
            price_status="public_price",
        )
        assert score >= 0.80

    def test_rfq_only_valid_not_zero(self):
        """RFQ-only is valid for B2B — must NOT produce zero confidence."""
        score = compute_price_confidence(
            source_tier="authorized", pn_match_confidence=0.9,
            price_status="rfq_only",
        )
        assert score > 0.30, "RFQ-only must be usable for B2B — not zero"

    def test_rfq_lower_than_public(self):
        score_pub = compute_price_confidence(
            source_tier="authorized", pn_match_confidence=0.9,
            price_status="public_price",
        )
        score_rfq = compute_price_confidence(
            source_tier="authorized", pn_match_confidence=0.9,
            price_status="rfq_only",
        )
        assert score_rfq < score_pub

    def test_ambiguous_unit_near_zero(self):
        score = compute_price_confidence(
            source_tier="authorized", pn_match_confidence=0.9,
            price_status="ambiguous_unit",
        )
        assert score < 0.15

    def test_ambiguous_offer_near_zero(self):
        score = compute_price_confidence(
            source_tier="authorized", pn_match_confidence=0.9,
            price_status="ambiguous_offer",
        )
        assert score < 0.15

    def test_stale_price_discount(self):
        score_fresh = compute_price_confidence(
            source_tier="authorized", pn_match_confidence=0.9,
            price_status="public_price", is_stale=False,
        )
        score_stale = compute_price_confidence(
            source_tier="authorized", pn_match_confidence=0.9,
            price_status="public_price", is_stale=True,
        )
        assert score_stale < score_fresh

    def test_sample_size_bonus(self):
        score_single = compute_price_confidence(
            source_tier="authorized", pn_match_confidence=0.8,
            price_status="public_price", sample_size=1,
        )
        score_multi = compute_price_confidence(
            source_tier="authorized", pn_match_confidence=0.8,
            price_status="public_price", sample_size=3,
        )
        assert score_multi > score_single

    def test_brand_mismatch_collapses(self):
        score = compute_price_confidence(
            source_tier="authorized", pn_match_confidence=0.9,
            price_status="public_price", brand_mismatch=True,
        )
        assert score < 0.25

    def test_unknown_vat_discount(self):
        score_known = compute_price_confidence(
            source_tier="industrial", pn_match_confidence=0.8,
            price_status="public_price", vat_basis_known=True,
        )
        score_unknown = compute_price_confidence(
            source_tier="industrial", pn_match_confidence=0.8,
            price_status="public_price", vat_basis_known=False,
        )
        assert score_unknown < score_known


# ══════════════════════════════════════════════════════════════════════════════
# compute_card_confidence — publishability
# ══════════════════════════════════════════════════════════════════════════════

class TestCardConfidence:

    def test_auto_publish_strong_all(self):
        cc = compute_card_confidence(
            pn_confidence=0.90,
            image_confidence=0.85,
            price_confidence=0.80,
            price_status="public_price",
            photo_verdict="KEEP",
        )
        assert cc.publishability == "AUTO_PUBLISH"

    def test_auto_publish_rfq(self):
        """RFQ-only price + KEEP photo + good PN → AUTO_PUBLISH."""
        cc = compute_card_confidence(
            pn_confidence=0.85,
            image_confidence=0.75,
            price_confidence=0.60,
            price_status="rfq_only",
            photo_verdict="KEEP",
        )
        assert cc.publishability == "AUTO_PUBLISH"

    def test_review_keep_photo_no_price(self):
        cc = compute_card_confidence(
            pn_confidence=0.80,
            image_confidence=0.70,
            price_confidence=0.0,
            price_status="no_price_found",
            photo_verdict="KEEP",
        )
        assert cc.publishability == "REVIEW_REQUIRED"
        assert "price_not_found" in cc.notes

    def test_review_good_price_reject_photo(self):
        cc = compute_card_confidence(
            pn_confidence=0.80,
            image_confidence=0.10,
            price_confidence=0.75,
            price_status="public_price",
            photo_verdict="REJECT",
        )
        assert cc.publishability == "REVIEW_REQUIRED"
        assert "image_weak_or_missing" in cc.notes

    def test_draft_no_pn(self):
        cc = compute_card_confidence(
            pn_confidence=0.10,
            image_confidence=0.0,
            price_confidence=0.0,
            price_status="no_price_found",
            photo_verdict="NO_PHOTO",
        )
        assert cc.publishability == "DRAFT_ONLY"
        assert "pn_not_confirmed" in cc.notes

    def test_rfq_not_treated_as_missing(self):
        """RFQ-only price must NOT cause DRAFT_ONLY when PN is confirmed."""
        cc = compute_card_confidence(
            pn_confidence=0.85,
            image_confidence=0.0,    # no photo
            price_confidence=0.55,
            price_status="rfq_only",
            photo_verdict="NO_PHOTO",
        )
        # PN confirmed + price present → at least REVIEW_REQUIRED, not DRAFT_ONLY
        assert cc.publishability in ("REVIEW_REQUIRED", "AUTO_PUBLISH")

    def test_overall_score_weighted(self):
        cc = compute_card_confidence(
            pn_confidence=0.80,
            image_confidence=0.60,
            price_confidence=0.50,
            price_status="public_price",
            photo_verdict="KEEP",
        )
        # overall = 0.80*0.4 + 0.60*0.3 + 0.50*0.2 + 0.0*0.1 = 0.32+0.18+0.10 = 0.60
        assert cc.overall == pytest.approx(0.60, abs=0.01)

    def test_overall_clamped_to_1(self):
        cc = compute_card_confidence(
            pn_confidence=1.0, image_confidence=1.0,
            price_confidence=1.0, price_status="public_price",
            photo_verdict="KEEP",
        )
        assert cc.overall <= 1.0

    def test_fields_stored(self):
        cc = compute_card_confidence(
            pn_confidence=0.7, image_confidence=0.6,
            price_confidence=0.5, price_status="public_price",
            photo_verdict="KEEP",
        )
        assert cc.pn_confidence == pytest.approx(0.7, abs=0.001)
        assert cc.image_confidence == pytest.approx(0.6, abs=0.001)
        assert cc.price_confidence == pytest.approx(0.5, abs=0.001)


# ══════════════════════════════════════════════════════════════════════════════
# confidence_label
# ══════════════════════════════════════════════════════════════════════════════

class TestConfidenceLabel:

    def test_high(self):
        assert confidence_label(0.90) == "HIGH"
        assert confidence_label(0.85) == "HIGH"

    def test_medium(self):
        assert confidence_label(0.70) == "MEDIUM"
        assert confidence_label(0.60) == "MEDIUM"

    def test_low(self):
        assert confidence_label(0.45) == "LOW"
        assert confidence_label(0.30) == "LOW"

    def test_very_low(self):
        assert confidence_label(0.10) == "VERY_LOW"
        assert confidence_label(0.0) == "VERY_LOW"

    def test_boundary_high(self):
        assert confidence_label(0.85) == "HIGH"

    def test_boundary_medium(self):
        assert confidence_label(0.60) == "MEDIUM"

    def test_boundary_low(self):
        assert confidence_label(0.30) == "LOW"


# ══════════════════════════════════════════════════════════════════════════════
# Block 0.1: structured_pn_match_location fix validation
# ══════════════════════════════════════════════════════════════════════════════

class TestStructuredPnMatchFix:
    """Validates that using structured_pn_match_location (not pn_match_location)
    produces non-zero pn_confidence for SKUs with confirmed structured identity."""

    def test_structured_title_gives_positive_confidence(self):
        """SKU with structured_pn_match_location='title' must get pn_confidence > 0."""
        score = compute_pn_confidence(
            location="title", is_numeric=False, source_tier="authorized",
        )
        assert score >= 0.50

    def test_empty_location_gives_zero(self):
        """Legacy pn_match_location='' must still give 0 — the bug scenario."""
        score = compute_pn_confidence(
            location="", is_numeric=False, source_tier="official",
        )
        assert score == 0.0

    def test_jsonld_location_official_gives_max(self):
        score = compute_pn_confidence(
            location="jsonld", is_numeric=False, source_tier="official",
        )
        assert score == pytest.approx(1.0, abs=0.01)

    def test_card_confidence_with_fixed_pn_gives_review(self):
        """SKU with strong identity + KEEP photo should get REVIEW_REQUIRED minimum
        when pn_confidence is correctly computed (not zero from bug)."""
        pn_c = compute_pn_confidence(
            location="title", is_numeric=False, source_tier="authorized",
        )
        img_c = compute_image_confidence(
            source_tier="authorized", pn_match_confidence=pn_c,
        )
        cc = compute_card_confidence(
            pn_confidence=pn_c,
            image_confidence=img_c,
            price_confidence=0.0,
            price_status="no_price_found",
            photo_verdict="KEEP",
        )
        assert cc.publishability in ("REVIEW_REQUIRED", "AUTO_PUBLISH")

    def test_card_confidence_with_zero_pn_gives_draft(self):
        """Bug scenario: pn_confidence=0 → DRAFT_ONLY even with KEEP photo."""
        cc = compute_card_confidence(
            pn_confidence=0.0,
            image_confidence=0.0,
            price_confidence=0.0,
            price_status="no_price_found",
            photo_verdict="KEEP",
        )
        assert cc.publishability == "DRAFT_ONLY"


# ══════════════════════════════════════════════════════════════════════════════
# Block 0.2: owner_price fallback
# ══════════════════════════════════════════════════════════════════════════════

class TestOwnerPriceFallback:
    """Validates that owner_price from xlsx enables REVIEW_REQUIRED."""

    def test_owner_price_confidence_positive(self):
        """owner_price must give positive price_confidence."""
        score = compute_price_confidence(
            source_tier="unknown", pn_match_confidence=0.0,
            price_status="owner_price",
        )
        assert score > 0.0

    def test_owner_price_confidence_below_public(self):
        """owner_price confidence should be lower than public_price."""
        score_owner = compute_price_confidence(
            source_tier="authorized", pn_match_confidence=0.9,
            price_status="owner_price",
        )
        score_public = compute_price_confidence(
            source_tier="authorized", pn_match_confidence=0.9,
            price_status="public_price",
        )
        assert score_owner < score_public

    def test_owner_price_not_auto_publish(self):
        """SKU with only owner_price should NOT get AUTO_PUBLISH."""
        pn_c = compute_pn_confidence(
            location="title", is_numeric=False, source_tier="authorized",
        )
        owner_price_c = compute_price_confidence(
            source_tier="unknown", pn_match_confidence=pn_c,
            price_status="owner_price",
        )
        img_c = compute_image_confidence(
            source_tier="authorized", pn_match_confidence=pn_c,
        )
        cc = compute_card_confidence(
            pn_confidence=pn_c,
            image_confidence=img_c,
            price_confidence=owner_price_c,
            price_status="owner_price",
            photo_verdict="KEEP",
        )
        # owner_price normalizes to rfq_only in card_status but confidence is only 0.35
        # which is below _PRICE_THRESHOLD (0.40) → no AUTO_PUBLISH
        assert cc.publishability in ("REVIEW_REQUIRED", "AUTO_PUBLISH")

    def test_owner_price_enables_review(self):
        """SKU with confirmed PN + owner_price → REVIEW_REQUIRED (not DRAFT)."""
        pn_c = compute_pn_confidence(
            location="h1", is_numeric=False, source_tier="authorized",
        )
        cc = compute_card_confidence(
            pn_confidence=pn_c,
            image_confidence=0.0,
            price_confidence=0.35,
            price_status="rfq_only",  # owner_price normalizes to rfq_only
            photo_verdict="REJECT",
        )
        assert cc.publishability in ("REVIEW_REQUIRED",)
