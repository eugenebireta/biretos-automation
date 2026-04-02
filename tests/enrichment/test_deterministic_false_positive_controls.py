import sys
import os

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from deterministic_false_positive_controls import (
    apply_numeric_keep_guard,
    tighten_public_price_result,
)


class TestPublicPriceControls:

    def test_category_mismatch_page_is_not_public_price(self):
        result = tighten_public_price_result({
            "price_status": "public_price",
            "source_tier": "authorized",
            "category_mismatch": True,
            "offer_unit_basis": "piece",
            "offer_qty": 1,
        })
        assert result["price_status"] == "category_mismatch_only"
        assert "category_or_brand_mismatch" in result["public_price_rejection_reasons"]

    def test_accessory_page_is_not_public_price(self):
        result = tighten_public_price_result({
            "price_status": "public_price",
            "source_tier": "authorized",
            "page_product_class": "accessory kit",
            "offer_unit_basis": "piece",
            "offer_qty": 1,
        })
        assert result["price_status"] == "category_mismatch_only"
        assert "noisy_page_context" in result["public_price_rejection_reasons"]

    def test_ambiguous_pack_unit_is_not_public_price(self):
        result = tighten_public_price_result({
            "price_status": "public_price",
            "source_tier": "authorized",
            "offer_unit_basis": "pack",
            "offer_qty": 10,
        })
        assert result["price_status"] == "ambiguous_offer"
        assert "ambiguous_pack_unit" in result["public_price_rejection_reasons"]

    def test_unknown_tier_public_price_is_not_exact_public_price(self):
        result = tighten_public_price_result({
            "price_status": "public_price",
            "source_tier": "unknown",
            "offer_unit_basis": "piece",
            "offer_qty": 1,
        })
        assert result["price_status"] == "ambiguous_offer"
        assert "source_tier_not_admissible" in result["public_price_rejection_reasons"]

    def test_true_exact_public_price_still_passes(self):
        result = tighten_public_price_result({
            "price_status": "public_price",
            "source_tier": "authorized",
            "offer_unit_basis": "piece",
            "offer_qty": 1,
            "page_product_class": "product",
            "pn_exact_confirmed": True,
        })
        assert result["price_status"] == "public_price"
        assert result["public_price_rejection_reasons"] == []


class TestNumericKeepControls:

    def test_exact_structured_context_can_keep_numeric_pn(self):
        result = apply_numeric_keep_guard(
            pn="010130.10",
            photo_result={
                "exact_structured_pn_match": True,
                "structured_pn_match_location": "jsonld",
            },
            vision_verdict={"verdict": "KEEP", "reason": "looks right"},
        )
        assert result["verdict"] == "KEEP"
        assert result["numeric_keep_guard_applied"] is False

    def test_body_only_context_cannot_keep_numeric_pn(self):
        result = apply_numeric_keep_guard(
            pn="1000106",
            photo_result={"pn_match_location": "body"},
            vision_verdict={"verdict": "KEEP", "reason": "looks right"},
        )
        assert result["verdict"] == "REJECT"
        assert "missing_exact_structured_context" in result["numeric_keep_guard_reasons"]

    def test_family_listing_matrix_context_cannot_keep_numeric_pn(self):
        result = apply_numeric_keep_guard(
            pn="033588.17",
            photo_result={"exact_structured_pn_match": True, "structured_pn_match_location": "title"},
            vision_verdict={"verdict": "KEEP", "reason": "looks right"},
            price_result={"page_product_class": "family listing matrix"},
        )
        assert result["verdict"] == "REJECT"
        assert "noisy_page_context" in result["numeric_keep_guard_reasons"]

    def test_accessory_context_cannot_keep_numeric_pn(self):
        result = apply_numeric_keep_guard(
            pn="00020211",
            photo_result={"exact_structured_pn_match": True, "structured_pn_match_location": "jsonld"},
            vision_verdict={"verdict": "KEEP", "reason": "looks right"},
            price_result={"page_product_class": "accessory mount"},
        )
        assert result["verdict"] == "REJECT"
        assert "noisy_page_context" in result["numeric_keep_guard_reasons"]

    def test_alphanumeric_pn_not_forced_through_numeric_guard(self):
        result = apply_numeric_keep_guard(
            pn="LK-750",
            photo_result={"pn_match_location": "body"},
            vision_verdict={"verdict": "KEEP", "reason": "looks right"},
        )
        assert result["verdict"] == "KEEP"
        assert result["numeric_keep_guard_applied"] is False
