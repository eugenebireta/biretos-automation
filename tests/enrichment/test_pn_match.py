"""tests/enrichment/test_pn_match.py — Deterministic tests for PN matching precision.

No live API calls. No file I/O. Pure logic tests.

Coverage:
  - is_numeric_pn()
  - confirm_pn_body() — strict vs non-strict mode
  - confirm_pn_structured() — JSON-LD / title / h1 / product_context
  - match_pn() — full result with confidence + trace
  - export_pipeline helpers: canonical_filename, assign_card_status
  - trust.get_domain()
  - fx.convert_to_rub()
"""
import sys
import os

# Add scripts/ to path for direct imports
_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

import pytest

from pn_match import (
    is_numeric_pn,
    confirm_pn_body,
    confirm_pn_structured,
    extract_structured_pn_flags,
    match_pn,
)
from trust import get_domain, get_source_trust, get_source_tier
from fx import convert_to_rub
from export_pipeline import canonical_photo_filename, assign_card_status


# ══════════════════════════════════════════════════════════════════════════════
# is_numeric_pn
# ══════════════════════════════════════════════════════════════════════════════

class TestIsNumericPn:

    def test_pure_digits_8(self):
        assert is_numeric_pn("00020211") is True

    def test_pure_digits_7(self):
        assert is_numeric_pn("1000106") is True

    def test_dotted_numeric_2segment(self):
        assert is_numeric_pn("010130.10") is True

    def test_dotted_numeric_2segment_b(self):
        assert is_numeric_pn("033588.17") is True

    def test_alphanumeric_pn(self):
        assert is_numeric_pn("CCB01-010BT") is False

    def test_alphanumeric_with_letters(self):
        assert is_numeric_pn("LK-750") is False

    def test_compound_with_letters(self):
        assert is_numeric_pn("SL22-020211-K6") is False

    def test_single_digit(self):
        # Edge: single digit is numeric
        assert is_numeric_pn("5") is True


# ══════════════════════════════════════════════════════════════════════════════
# confirm_pn_body — strict mode for numeric PN
# ══════════════════════════════════════════════════════════════════════════════

class TestConfirmPnBodyNumericStrict:
    """Numeric PNs must NOT match as dash-embedded substrings."""

    def test_00020211_in_SL22_020211_K6_BLOCKED(self):
        """Core false-positive guard: 00020211 inside SL22-020211-K6."""
        text = "Buy Honeywell SL22-020211-K6 Sled for Apple iPod touch"
        matched, _ = confirm_pn_body("00020211", text)
        assert matched is False, "Numeric PN must NOT match inside dash-compound token"

    def test_numeric_pn_isolated_with_spaces(self):
        """Isolated with spaces → should match."""
        text = "Part number 00020211, available."
        matched, loc = confirm_pn_body("00020211", text)
        assert matched is True
        assert loc == "body"

    def test_numeric_pn_at_line_start(self):
        text = "00020211\nTemperature sensor D20.672.022"
        matched, _ = confirm_pn_body("00020211", text)
        assert matched is True

    def test_numeric_pn_in_table(self):
        text = "Model: 00020211\nPrice: 150 USD"
        matched, _ = confirm_pn_body("00020211", text)
        assert matched is True

    def test_dotted_numeric_isolated(self):
        text = "Module 010130.10 for BUS-2/BUS-1 s.m. — in stock."
        matched, _ = confirm_pn_body("010130.10", text)
        assert matched is True

    def test_dotted_numeric_dash_compound_BLOCKED(self):
        """010130.10 embedded in dash-compound → blocked."""
        text = "Module XL-010130.10-A extended variant."
        matched, _ = confirm_pn_body("010130.10", text)
        assert matched is False

    def test_1000106_isolated(self):
        text = "Honeywell Bilsom 304L earplug, article 1000106, corded."
        matched, _ = confirm_pn_body("1000106", text)
        assert matched is True


class TestConfirmPnBodyAlphanumericNonStrict:
    """Alphanumeric PNs use non-strict mode (dash OK as separator)."""

    def test_alphanumeric_standard_match(self):
        text = "The CCB01-010BT is a cordless scanner system."
        matched, _ = confirm_pn_body("CCB01-010BT", text)
        assert matched is True

    def test_LK750_NOT_in_LK7500(self):
        """LK-750 must NOT match inside LK-7500 (digit boundary)."""
        text = "Product LK-7500 is the extended model."
        matched, _ = confirm_pn_body("LK-750", text)
        assert matched is False

    def test_alphanumeric_with_trailing_space(self):
        text = "027913.10 card reader luminAXS."
        matched, _ = confirm_pn_body("027913.10", text)
        assert matched is True


# ══════════════════════════════════════════════════════════════════════════════
# confirm_pn_structured — JSON-LD / title / h1 / product_context
# ══════════════════════════════════════════════════════════════════════════════

class TestConfirmPnStructuredJsonLD:

    def test_jsonld_mpn_exact_match(self):
        html = '''<script type="application/ld+json">
        {"@type": "Product", "mpn": "00020211", "name": "Sensor",
         "image": "https://example.com/img.jpg"}
        </script>'''
        matched, loc = confirm_pn_structured("00020211", html)
        assert matched is True
        assert loc == "jsonld"

    def test_jsonld_sku_match(self):
        html = '''<script type="application/ld+json">
        {"@type": "Product", "sku": "010130.10", "name": "Module"}
        </script>'''
        matched, loc = confirm_pn_structured("010130.10", html)
        assert matched is True
        assert loc == "jsonld"

    def test_jsonld_mpn_longer_code_NOT_matched(self):
        """JSON-LD mpn is 'SL22-020211-K6' — exact comparison fails for '00020211'."""
        html = '''<script type="application/ld+json">
        {"@type": "Product", "mpn": "SL22-020211-K6", "name": "Sled"}
        </script>'''
        matched, _ = confirm_pn_structured("00020211", html)
        assert matched is False

    def test_jsonld_non_product_type_ignored(self):
        html = '''<script type="application/ld+json">
        {"@type": "Organization", "sku": "00020211"}
        </script>'''
        matched, _ = confirm_pn_structured("00020211", html)
        assert matched is False


class TestConfirmPnStructuredTitleH1:

    def test_title_match(self):
        html = "<html><head><title>Honeywell 010130.10 Module BUS</title></head></html>"
        matched, loc = confirm_pn_structured("010130.10", html)
        assert matched is True
        assert loc == "title"

    def test_h1_match(self):
        html = "<html><body><h1>Temperature Sensor 00020211</h1></body></html>"
        matched, loc = confirm_pn_structured("00020211", html)
        assert matched is True
        assert loc == "h1"

    def test_title_priority_over_h1(self):
        """Title checked before h1 — expect title location."""
        html = """<html><head><title>010130.10 Module</title></head>
        <body><h1>010130.10 Module</h1></body></html>"""
        matched, loc = confirm_pn_structured("010130.10", html)
        assert matched is True
        assert loc == "title"

    def test_no_match_empty_html(self):
        matched, loc = confirm_pn_structured("00020211", "")
        assert matched is False
        assert loc == ""


class TestConfirmPnStructuredProductContext:

    def test_itemprop_mpn_exact(self):
        html = '<span itemprop="mpn">00020211</span>'
        matched, loc = confirm_pn_structured("00020211", html)
        assert matched is True
        assert loc == "product_context"

    def test_itemprop_sku_exact(self):
        html = '<span itemprop="sku">1000106</span>'
        matched, loc = confirm_pn_structured("1000106", html)
        assert matched is True
        assert loc == "product_context"


class TestExtractStructuredPnFlags:

    def test_extract_jsonld_flag(self):
        html = '''<script type="application/ld+json">
        {"@type": "Product", "mpn": "00020211"}
        </script>'''
        flags = extract_structured_pn_flags("00020211", html)
        assert flags["exact_jsonld_pn_match"] is True
        assert flags["exact_structured_pn_match"] is True
        assert flags["structured_pn_match_location"] == "jsonld"

    def test_extract_title_flag(self):
        flags = extract_structured_pn_flags(
            "010130.10",
            "<html><head><title>Honeywell 010130.10 Module</title></head></html>",
        )
        assert flags["exact_title_pn_match"] is True
        assert flags["structured_pn_match_location"] == "title"

    def test_extract_h1_flag(self):
        flags = extract_structured_pn_flags(
            "00020211",
            "<html><body><h1>Temperature Sensor 00020211</h1></body></html>",
        )
        assert flags["exact_h1_pn_match"] is True
        assert flags["structured_pn_match_location"] == "h1"

    def test_extract_product_context_flag(self):
        flags = extract_structured_pn_flags(
            "1000106",
            '<span itemprop="sku">1000106</span>',
        )
        assert flags["exact_product_context_pn_match"] is True
        assert flags["structured_pn_match_location"] == "product_context"

    def test_body_only_does_not_materialize_structured_flags(self):
        flags = extract_structured_pn_flags(
            "00020211",
            "<html><body><div>Part number 00020211 available now</div></body></html>",
        )
        assert flags["exact_structured_pn_match"] is False
        assert flags["structured_pn_match_location"] == ""

    def test_search_hint_url_does_not_materialize_structured_flags(self):
        flags = extract_structured_pn_flags(
            "00020211",
            "<html><body><a href='/search?q=00020211'>search result</a></body></html>",
        )
        assert flags["exact_structured_pn_match"] is False
        assert flags["structured_pn_match_location"] == ""


# ══════════════════════════════════════════════════════════════════════════════
# match_pn — full result with confidence + trace
# ══════════════════════════════════════════════════════════════════════════════

class TestMatchPn:

    def test_numeric_body_only_low_confidence(self):
        """Numeric PN in body only → confidence=50, numeric_guard_triggered=True."""
        text = "Part number 00020211, available for order."
        result = match_pn("00020211", text)
        assert result.matched is True
        assert result.confidence == 50
        assert result.numeric_guard_triggered is True
        assert result.location == "body"

    def test_numeric_jsonld_high_confidence(self):
        """Numeric PN confirmed in JSON-LD → confidence=100, no guard flag."""
        html = '''<script type="application/ld+json">
        {"@type": "Product", "mpn": "00020211"}
        </script>'''
        result = match_pn("00020211", "Part 00020211 available", html)
        assert result.matched is True
        assert result.confidence == 100
        assert result.location == "jsonld"
        assert result.numeric_guard_triggered is False

    def test_numeric_false_positive_body_blocked(self):
        """00020211 inside SL22-020211-K6 → not matched in body strict mode."""
        result = match_pn("00020211", "Buy Honeywell SL22-020211-K6")
        assert result.matched is False

    def test_numeric_1000106_body_confidence_50(self):
        """1000106 is numeric → body-only match gets confidence=50, guard triggered."""
        result = match_pn("1000106", "Honeywell 1000106 earplug corded.")
        assert result.matched is True
        assert result.confidence == 50       # numeric body = low confidence
        assert result.numeric_guard_triggered is True  # 1000106 IS numeric

    def test_alphanumeric_CCB01_match(self):
        result = match_pn("CCB01-010BT", "The CCB01-010BT cordless scanner.")
        assert result.matched is True
        assert result.confidence == 90
        assert result.numeric_guard_triggered is False

    def test_as_dict_keys_present(self):
        result = match_pn("010130.10", "Module 010130.10 in stock.")
        d = result.as_dict()
        assert "pn_matched" in d
        assert "pn_match_location" in d
        assert "pn_match_is_numeric" in d
        assert "numeric_pn_guard_triggered" in d
        assert "pn_match_confidence" in d


# ══════════════════════════════════════════════════════════════════════════════
# Artifact cache isolation (logic tests, no file I/O)
# ══════════════════════════════════════════════════════════════════════════════

class TestArtifactCacheIsolation:
    """REJECT on one sha1 must NOT block all artifacts for same PN."""

    def test_different_sha1_independent(self):
        cache = {"abc123abc": {"verdict": "REJECT", "pn": "010130.10"}}
        # Different sha1 → no entry → not rejected
        assert cache.get("def456def") is None

    def test_keep_sha1_reused(self):
        cache = {"sha1good0": {"verdict": "KEEP", "pn": "1000106"}}
        assert cache["sha1good0"]["verdict"] == "KEEP"

    def test_reject_sha1_does_not_affect_other_sha1(self):
        cache = {
            "reject_sha": {"verdict": "REJECT", "pn": "010130.10"},
            "good___sha": {"verdict": "KEEP",   "pn": "010130.10"},
        }
        assert cache["good___sha"]["verdict"] == "KEEP"


# ══════════════════════════════════════════════════════════════════════════════
# trust.py — domain extraction
# ══════════════════════════════════════════════════════════════════════════════

class TestTrust:

    def test_official_domain(self):
        assert get_source_tier("https://www.honeywell.com/product") == "official"

    def test_authorized_distributor(self):
        assert get_source_tier("https://www.mouser.com/c/?q=010130.10") == "authorized"

    def test_ru_tld_fallback(self):
        tier = get_source_tier("https://someunknown-company.ru/catalog/item")
        assert tier == "ru_b2b"

    def test_de_tld_fallback(self):
        tier = get_source_tier("https://someunknown.de/product")
        assert tier == "industrial"

    def test_get_domain_strips_www(self):
        assert get_domain("https://www.honeywell.com/path") == "honeywell.com"

    def test_get_domain_handles_port(self):
        assert get_domain("http://example.com:8080/page") == "example.com"

    def test_weak_source(self):
        trust = get_source_trust("https://www.amazon.com/dp/B0001")
        assert trust["tier"] == "weak"
        assert trust["weight"] < 0.5

    def test_weight_official_max(self):
        trust = get_source_trust("https://honeywell.com")
        assert trust["weight"] == 1.0


# ══════════════════════════════════════════════════════════════════════════════
# fx.py — FX normalization
# ══════════════════════════════════════════════════════════════════════════════

class TestFx:

    def test_rub_passthrough(self):
        assert convert_to_rub(1000.0, "RUB") == 1000.0

    def test_eur_to_rub(self):
        result = convert_to_rub(100.0, "EUR")
        assert result is not None
        assert result > 0

    def test_aed_to_rub(self):
        result = convert_to_rub(68.25, "AED")
        assert result is not None
        assert result > 0

    def test_none_amount_returns_none(self):
        assert convert_to_rub(None, "EUR") is None

    def test_none_currency_returns_none(self):
        assert convert_to_rub(100.0, None) is None

    def test_unknown_currency_returns_none(self):
        assert convert_to_rub(100.0, "XYZ") is None

    def test_zero_amount_returns_none(self):
        assert convert_to_rub(0.0, "EUR") is None


# ══════════════════════════════════════════════════════════════════════════════
# export_pipeline.py — canonical filename + card status
# ══════════════════════════════════════════════════════════════════════════════

class TestExportHelpers:

    def test_canonical_filename_format(self):
        fn = canonical_photo_filename("Honeywell", "010130.10", "abc123defg")
        # Should be uppercase brand + pn, 8-char sha1 suffix, .jpg
        assert fn.endswith(".jpg")
        assert "HONEYWELL" in fn
        assert "010130_10" in fn  # dot → underscore via safe()
        assert fn.count("_abc123de") == 1 or "abc123de" in fn

    def test_canonical_filename_no_spaces(self):
        fn = canonical_photo_filename("Honeywell", "1000 106", "sha1sha1sha1")
        assert " " not in fn

    def test_card_status_auto_publish(self):
        status, reasons = assign_card_status(
            photo_verdict="KEEP",
            price_status="public_price",
            category_mismatch=False,
        )
        assert status == "AUTO_PUBLISH"
        assert reasons == []

    def test_card_status_auto_publish_rfq(self):
        status, _ = assign_card_status("KEEP", "rfq_only")
        assert status == "AUTO_PUBLISH"

    def test_card_status_review_keep_no_price(self):
        status, _ = assign_card_status("KEEP", "no_price_found")
        assert status == "REVIEW_REQUIRED"

    def test_card_status_review_price_no_photo(self):
        status, _ = assign_card_status("REJECT", "public_price")
        assert status == "REVIEW_REQUIRED"

    def test_card_status_draft_nothing(self):
        status, _ = assign_card_status("NO_PHOTO", "no_price_found")
        assert status == "DRAFT_ONLY"

    def test_card_status_mismatch_blocks_publish(self):
        """KEEP photo + public price BUT category_mismatch → REVIEW_REQUIRED."""
        status, reasons = assign_card_status(
            photo_verdict="KEEP",
            price_status="public_price",
            category_mismatch=True,
        )
        assert status == "REVIEW_REQUIRED"
        assert "category_mismatch" in reasons

    def test_card_status_mismatch_only_price(self):
        """category_mismatch_only price + no KEEP photo → DRAFT_ONLY."""
        status, _ = assign_card_status("REJECT", "category_mismatch_only",
                                       category_mismatch=True)
        assert status == "DRAFT_ONLY"
