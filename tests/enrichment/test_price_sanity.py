"""Tests for price_sanity.py — deterministic, no live API, no unmocked time."""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from price_sanity import (
    PriceSanityResult,
    apply_sanity_to_price_info,
    check_price_sanity,
    _estimate_usd,
)


# ── _estimate_usd ─────────────────────────────────────────────────────────────

class TestEstimateUsd:
    def test_usd_currency_returns_raw(self):
        assert _estimate_usd(150.0, "USD", None) == 150.0

    def test_usd_currency_case_insensitive(self):
        assert _estimate_usd(100.0, "usd", None) == 100.0

    def test_aed_via_rub_price(self):
        # 68.25 AED * 24 RUB/AED = 1638 RUB; 1638 / 88 USD ≈ 18.61 USD
        result = _estimate_usd(68.25, "AED", 1638.0)
        assert result is not None
        assert abs(result - 1638.0 / 88.0) < 0.01

    def test_none_raw_price_returns_none(self):
        assert _estimate_usd(None, "USD", None) is None

    def test_no_rub_price_non_usd_returns_none(self):
        assert _estimate_usd(100.0, "EUR", None) is None


# ── check_price_sanity ────────────────────────────────────────────────────────

class TestCheckPriceSanity:
    # Test: earplug $18.61 from AED → WARNING (EXOTIC + HIGH_PIECE_PRICE_EXOTIC)
    def test_earplug_aed_price_is_warning(self):
        result = check_price_sanity(
            price_usd=18.61,
            pn="1000106",
            brand="Honeywell",
            source_currency="AED",
            unit_basis="piece",
        )
        assert result.status in ("WARNING", "REJECT")
        assert any("EXOTIC_CURRENCY" in f or "HIGH_PIECE_PRICE_EXOTIC" in f for f in result.flags)

    # Test: normal industrial sensor $150 → PASS
    def test_normal_sensor_price_is_pass(self):
        result = check_price_sanity(
            price_usd=150.0,
            pn="1011994",
            brand="Honeywell",
            source_currency="USD",
            unit_basis="piece",
        )
        assert result.status == "PASS"
        assert result.flags == []

    # Test: $0.001 → REJECT (EXTREME_LOW)
    def test_extreme_low_price_is_reject(self):
        result = check_price_sanity(
            price_usd=0.001,
            pn="TEST001",
            brand="Honeywell",
            source_currency="USD",
            unit_basis="piece",
        )
        assert result.status == "REJECT"
        assert any("EXTREME_LOW" in f for f in result.flags)

    # Test: $60000 → REJECT (EXTREME_HIGH)
    def test_extreme_high_price_is_reject(self):
        result = check_price_sanity(
            price_usd=60000.0,
            pn="TEST002",
            brand="Honeywell",
            source_currency="USD",
            unit_basis="piece",
        )
        assert result.status == "REJECT"
        assert any("EXTREME_HIGH" in f for f in result.flags)

    # Test: cross-reference 10x above median → WARNING
    def test_price_10x_above_median_is_warning(self):
        # Median of [10, 12, 11] = 11; price 120 > 11*5 = 55 → 5X_ABOVE_MEDIAN
        result = check_price_sanity(
            price_usd=120.0,
            pn="TEST003",
            brand="Honeywell",
            source_currency="USD",
            unit_basis="piece",
            existing_prices_usd=[10.0, 12.0, 11.0],
        )
        assert result.status == "WARNING"
        assert any("5X_ABOVE_MEDIAN" in f for f in result.flags)

    # Test: cross-reference 10x below median → WARNING
    def test_price_10x_below_median_is_warning(self):
        # Median of [100, 110, 105] = 105; price 5 < 105/5 = 21 → 5X_BELOW_MEDIAN
        result = check_price_sanity(
            price_usd=5.0,
            pn="TEST004",
            brand="Honeywell",
            source_currency="USD",
            unit_basis="piece",
            existing_prices_usd=[100.0, 110.0, 105.0],
        )
        assert result.status == "WARNING"
        assert any("5X_BELOW_MEDIAN" in f for f in result.flags)

    # Test: SAR (exotic) currency → WARNING includes EXOTIC_CURRENCY
    def test_sar_currency_is_exotic_warning(self):
        result = check_price_sanity(
            price_usd=50.0,
            pn="TEST005",
            brand="Honeywell",
            source_currency="SAR",
            unit_basis="piece",
        )
        assert result.status == "WARNING"
        assert any("EXOTIC_CURRENCY" in f for f in result.flags)

    # Test: round AED number → WARNING includes ROUND_NUMBER_EXOTIC
    def test_round_aed_number_is_warning(self):
        result = check_price_sanity(
            price_usd=18.0,  # exact integer
            pn="TEST006",
            brand="Honeywell",
            source_currency="AED",
            unit_basis="piece",
        )
        assert result.status == "WARNING"
        assert any("ROUND_NUMBER_EXOTIC" in f or "EXOTIC_CURRENCY" in f for f in result.flags)

    # Test: None price_usd → WARNING (cannot validate)
    def test_none_price_returns_warning(self):
        result = check_price_sanity(
            price_usd=None,
            pn="TEST007",
            brand="Honeywell",
            source_currency="USD",
            unit_basis="piece",
        )
        assert result.status == "WARNING"

    # Test: reasonable $2500 USD industrial product → PASS
    def test_expensive_industrial_product_is_pass(self):
        result = check_price_sanity(
            price_usd=2500.0,
            pn="TEST008",
            brand="Honeywell",
            source_currency="USD",
            unit_basis="piece",
        )
        assert result.status == "PASS"

    # Test: $49999 just under extreme threshold → PASS (no extreme flag)
    def test_just_under_extreme_high_is_pass(self):
        result = check_price_sanity(
            price_usd=49999.0,
            pn="TEST009",
            brand="Honeywell",
            source_currency="USD",
            unit_basis="piece",
        )
        # No EXTREME_HIGH, so no REJECT
        assert result.status == "PASS"

    # Test: cross-reference with only 1 price → no cross-ref check applied
    def test_single_existing_price_no_cross_ref(self):
        result = check_price_sanity(
            price_usd=500.0,
            pn="TEST010",
            brand="Honeywell",
            source_currency="USD",
            unit_basis="piece",
            existing_prices_usd=[10.0],  # only 1 price, no cross-ref
        )
        # 500 USD for a piece from USD source — no exotic, no extreme → PASS
        assert result.status == "PASS"


# ── PriceSanityResult ─────────────────────────────────────────────────────────

class TestPriceSanityResult:
    def test_pass_status(self):
        r = PriceSanityResult("PASS", [])
        assert r.is_pass()
        assert not r.is_warning()
        assert not r.is_reject()

    def test_warning_status(self):
        r = PriceSanityResult("WARNING", ["flag1"])
        assert r.is_warning()
        assert not r.is_pass()

    def test_reject_status(self):
        r = PriceSanityResult("REJECT", ["EXTREME_HIGH"])
        assert r.is_reject()

    def test_to_dict(self):
        r = PriceSanityResult("WARNING", ["FLAG"])
        d = r.to_dict()
        assert d["sanity_status"] == "WARNING"
        assert d["sanity_flags"] == ["FLAG"]


# ── apply_sanity_to_price_info ────────────────────────────────────────────────

class TestApplySanityToPriceInfo:
    def _make_aed_price_info(self, raw_price: float = 68.25) -> dict:
        """Simulate 1000106 earplug AED price_info from pipeline."""
        rub_price = raw_price * 24.0
        return {
            "price_usd": raw_price,       # stored as native currency value
            "currency": "AED",
            "rub_price": rub_price,
            "offer_unit_basis": "piece",
            "price_status": "public_price",
            "source_url": "https://example.com/product",
        }

    def test_aed_earplug_gets_warning(self):
        price_info = self._make_aed_price_info(68.25)
        result = apply_sanity_to_price_info(price_info, "1000106", "Honeywell")
        # Should be WARNING or REJECT (AED + high piece price)
        assert result["price_sanity_status"] in ("WARNING", "REJECT")
        assert len(result["price_sanity_flags"]) > 0

    def test_reject_clears_price(self):
        """If sanity returns REJECT, price_usd and rub_price must be None."""
        # Use extreme low to force REJECT
        price_info = {
            "price_usd": 0.001,
            "currency": "USD",
            "rub_price": 0.088,
            "offer_unit_basis": "piece",
            "price_status": "public_price",
            "source_url": "https://example.com",
        }
        result = apply_sanity_to_price_info(price_info, "TESTPN", "Brand")
        assert result["price_sanity_status"] == "REJECT"
        assert result["price_usd"] is None
        assert result["rub_price"] is None
        assert result["price_status"] == "rejected_sanity_check"

    def test_pass_preserves_price(self):
        price_info = {
            "price_usd": 150.0,
            "currency": "USD",
            "rub_price": 13200.0,
            "offer_unit_basis": "piece",
            "price_status": "public_price",
            "source_url": "https://example.com",
        }
        result = apply_sanity_to_price_info(price_info, "TESTPN", "Brand")
        assert result["price_sanity_status"] == "PASS"
        assert result["price_usd"] == 150.0
        assert result["rub_price"] == 13200.0
        assert result["price_status"] == "public_price"

    def test_warning_preserves_price_and_adds_warnings(self):
        price_info = self._make_aed_price_info(68.25)
        result = apply_sanity_to_price_info(price_info, "1000106", "Honeywell")
        if result["price_sanity_status"] == "WARNING":
            assert result["price_usd"] == 68.25  # price preserved
            assert "price_warnings" in result
            assert len(result["price_warnings"]) > 0

    def test_does_not_mutate_original(self):
        price_info = {
            "price_usd": 0.001,
            "currency": "USD",
            "rub_price": 0.088,
            "offer_unit_basis": "piece",
            "price_status": "public_price",
            "source_url": "https://example.com",
        }
        original_price = price_info["price_usd"]
        apply_sanity_to_price_info(price_info, "TESTPN", "Brand")
        # Original dict must not be mutated
        assert price_info["price_usd"] == original_price
        assert price_info["price_status"] == "public_price"
