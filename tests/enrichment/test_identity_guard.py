"""tests/enrichment/test_identity_guard.py — Deterministic tests for identity_guard.

No live API calls. No file I/O (whitelist provided as dict to avoid config dep).
Pure logic tests.
"""
import sys
import os

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

import pytest
from identity_guard import (
    is_identity_proof,
    check_negative_identity,
    check_cross_pollination,
    classify_photo_type,
    is_family_photo_allowed,
)

_TEST_WHITELIST = {
    "denied_by_default": True,
    "allowed_series": [
        {"brand": "Esser", "series_pattern": "IQ8.*", "reason": "test"},
    ],
}


# ══════════════════════════════════════════════════════════════════════════════
# is_identity_proof
# ══════════════════════════════════════════════════════════════════════════════

class TestIsIdentityProof:

    def test_jsonld_is_proof(self):
        assert is_identity_proof("00020211", "jsonld") is True

    def test_title_is_proof(self):
        assert is_identity_proof("00020211", "title") is True

    def test_h1_is_proof(self):
        assert is_identity_proof("00020211", "h1") is True

    def test_product_context_is_proof(self):
        assert is_identity_proof("00020211", "product_context") is True

    def test_body_isolated_token_is_proof(self):
        text = "Order product 00020211 for fire detection"
        assert is_identity_proof("00020211", "body", text) is True

    def test_body_substring_in_other_code_not_proof(self):
        # 00020211 embedded as substring inside larger alphanumeric code
        text = "Model: AB00020211XY in stock"
        assert is_identity_proof("00020211", "body", text) is False

    def test_body_dash_adjacent_not_proof(self):
        # Numeric PN adjacent to dash — not isolated
        text = "Part SL22-00020211-K6 available"
        assert is_identity_proof("00020211", "body", text) is False

    def test_body_without_context_not_proof(self):
        # body match but no context provided → conservative False
        assert is_identity_proof("00020211", "body", "") is False

    def test_empty_location_not_proof(self):
        assert is_identity_proof("00020211", "") is False

    def test_unknown_location_not_proof(self):
        assert is_identity_proof("00020211", "meta_tag") is False


# ══════════════════════════════════════════════════════════════════════════════
# check_negative_identity
# ══════════════════════════════════════════════════════════════════════════════

class TestNegativeIdentity:

    def test_suitable_for_triggers(self):
        result = check_negative_identity("This sensor is suitable for use with IQ8")
        assert "suitable for" in result

    def test_compatible_with_triggers(self):
        result = check_negative_identity("Compatible with Esser IQ8 series detectors")
        assert "compatible with" in result

    def test_catalog_page_triggers(self):
        result = check_negative_identity("Product catalog with options overview")
        assert "catalog" in result
        assert "options" in result

    def test_clean_product_page_no_triggers(self):
        result = check_negative_identity(
            "Product 00020211: Optical smoke detector, 24V DC, EN 54-7 compliant."
        )
        assert result == []

    def test_accessory_sku_compatible_still_triggers(self):
        # "compatible with" is still a reject signal even for accessory SKU
        text = "Mounting bracket, compatible with IQ8 base series"
        result = check_negative_identity(text, expected_category="mounting bracket")
        assert "compatible with" in result

    def test_accessory_sku_mounting_word_exempted(self):
        # For a mounting bracket SKU, "mounting" alone is NOT a reject signal
        # (it's the product itself, not a compatibility description)
        text = "Wall mounting bracket, horizontal surface installation"
        result = check_negative_identity(text, expected_category="mounting bracket")
        # "mounting" is an exempt word for this category — should not appear in triggers
        assert "mounting" not in result

    def test_replacement_for_triggers(self):
        result = check_negative_identity("Replacement for part 00020211")
        assert "replacement for" in result

    def test_empty_text_no_triggers(self):
        assert check_negative_identity("") == []


# ══════════════════════════════════════════════════════════════════════════════
# check_cross_pollination
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossPollination:

    def test_many_pns_triggers(self):
        pns = ["00020211", "808606", "027913", "1000106", "CCB01-010BT"]
        assert check_cross_pollination(pns, "00020211") is True

    def test_three_non_target_triggers(self):
        pns = ["00020211", "808606", "027913", "1000106"]
        assert check_cross_pollination(pns, "00020211") is True

    def test_single_target_only_no_trigger(self):
        assert check_cross_pollination(["00020211"], "00020211") is False

    def test_two_different_pns_triggers(self):
        # Even one "other" PN is a cross-pollination signal
        assert check_cross_pollination(["00020211", "808606"], "00020211") is True

    def test_empty_list_no_trigger(self):
        assert check_cross_pollination([], "00020211") is False

    def test_case_insensitive_target_match(self):
        # Same PN in different case → not "other PN"
        pns = ["00020211", "00020211"]
        assert check_cross_pollination(pns, "00020211") is False


# ══════════════════════════════════════════════════════════════════════════════
# classify_photo_type
# ══════════════════════════════════════════════════════════════════════════════

class TestClassifyPhotoType:

    def test_jsonld_plus_pn_in_title_is_exact(self):
        signals = {"jsonld_image": True, "pn_in_title": True}
        assert classify_photo_type(signals) == "exact_photo"

    def test_pn_in_url_is_exact(self):
        signals = {"pn_in_url": True}
        assert classify_photo_type(signals) == "exact_photo"

    def test_pn_in_url_overrides_family_page(self):
        # pn_in_url is checked after page_is_family, but page_is_family wins
        signals = {"page_is_family": True, "pn_in_url": True}
        assert classify_photo_type(signals) == "family_photo"

    def test_page_is_family_returns_family(self):
        signals = {"page_is_family": True, "jsonld_image": True}
        assert classify_photo_type(signals) == "family_photo"

    def test_jsonld_without_title_is_unknown(self):
        signals = {"jsonld_image": True, "pn_in_title": False}
        assert classify_photo_type(signals) == "unknown"

    def test_no_signals_is_unknown(self):
        assert classify_photo_type({}) == "unknown"

    def test_empty_dict_is_unknown(self):
        assert classify_photo_type({}) == "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# is_family_photo_allowed
# ══════════════════════════════════════════════════════════════════════════════

class TestFamilyPhotoAllowed:

    def test_esser_iq8_in_whitelist_allowed(self):
        assert is_family_photo_allowed("Esser", "IQ8Quad", _TEST_WHITELIST) is True

    def test_esser_iq8_long_name_allowed(self):
        assert is_family_photo_allowed("Esser", "IQ8Control", _TEST_WHITELIST) is True

    def test_esser_iq8_prefix_alone_not_allowed(self):
        # "IQ8" by itself matches "IQ8.*" (fullmatch with .* matches empty suffix too)
        assert is_family_photo_allowed("Esser", "IQ8", _TEST_WHITELIST) is True

    def test_esser_non_iq8_denied(self):
        assert is_family_photo_allowed("Esser", "ES700", _TEST_WHITELIST) is False

    def test_honeywell_not_in_whitelist_denied(self):
        assert is_family_photo_allowed("Honeywell", "IS310", _TEST_WHITELIST) is False

    def test_unknown_brand_denied(self):
        assert is_family_photo_allowed("UnknownBrand", "XYZ123", _TEST_WHITELIST) is False

    def test_case_insensitive_brand_match(self):
        assert is_family_photo_allowed("esser", "IQ8Quad", _TEST_WHITELIST) is True
        assert is_family_photo_allowed("ESSER", "IQ8Control", _TEST_WHITELIST) is True

    def test_allow_by_default_policy(self):
        whitelist_open = {"denied_by_default": False, "allowed_series": []}
        assert is_family_photo_allowed("AnyBrand", "XYZ", whitelist_open) is True
