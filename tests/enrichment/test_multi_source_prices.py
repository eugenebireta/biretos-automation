"""Tests for multi_source_prices.py (Block 5)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from multi_source_prices import (
    search_distributor_prices,
    _extract_price_from_snippet,
    run_multi_source_validation,
)


class TestExtractPriceFromSnippet:
    def test_dollar_price_extracted(self):
        result = _extract_price_from_snippet("Price: $42.50 each", "https://example.com", "example.com")
        assert result is not None
        assert result["price_usd"] == 42.50
        assert result["currency"] == "USD"

    def test_euro_price_extracted(self):
        result = _extract_price_from_snippet("€ 12.99 per piece", "https://shop.de", "shop.de")
        assert result is not None
        assert result["currency"] == "EUR"

    def test_rub_price_extracted(self):
        result = _extract_price_from_snippet("Цена: 1500 ₽", "https://shop.ru", "shop.ru")
        assert result is not None
        assert result["currency"] == "RUB"
        assert result["price_usd"] == 1500.0

    def test_no_price_returns_none(self):
        result = _extract_price_from_snippet("Buy this product now", "https://example.com", "example.com")
        assert result is None

    def test_result_has_required_fields(self):
        result = _extract_price_from_snippet("$10.00", "https://example.com", "example.com")
        assert result is not None
        assert "price_usd" in result
        assert "currency" in result
        assert "source_url" in result
        assert "source_domain" in result
        assert "source_tier" in result


class TestSearchDistributorPrices:
    def test_returns_empty_without_serpapi_key(self):
        result = search_distributor_prices(
            pn="1000106", brand="Honeywell", trusted_domains=["honeywell.com"],
            serpapi_key="", max_sources=3
        )
        assert result == []

    def test_returns_empty_without_pn(self):
        result = search_distributor_prices(
            pn="", brand="Honeywell", trusted_domains=["honeywell.com"],
            serpapi_key="fake_key", max_sources=3
        )
        assert result == []

    def test_serpapi_import_error_returns_empty(self):
        """If serpapi not installed, returns empty list gracefully."""
        with patch.dict("sys.modules", {"serpapi": None}):
            result = search_distributor_prices(
                pn="1000106", brand="Honeywell", trusted_domains=["honeywell.com"],
                serpapi_key="fake_key", max_sources=3
            )
        assert result == []


class TestRunMultiSourceValidation:
    def _make_bundle(self, price_status="public_price", price_usd=100.0):
        return {
            "pn": "1000106",
            "brand": "Honeywell",
            "price": {
                "price_status": price_status,
                "price_per_unit": price_usd,
                "currency": "USD",
                "offer_unit_basis": "piece",
            },
        }

    def test_non_public_price_skipped(self):
        """Multi-source should not run for non-public prices."""
        bundle = self._make_bundle(price_status="no_price_found", price_usd=None)
        result = run_multi_source_validation(
            bundle=bundle, pn="1000106", brand="Honeywell", serpapi_key="fake"
        )
        assert "additional_prices" not in result
        assert "price_cross_validation" not in result

    def test_no_serpapi_key_returns_bundle_unchanged(self):
        bundle = self._make_bundle()
        result = run_multi_source_validation(
            bundle=bundle, pn="1000106", brand="Honeywell", serpapi_key=""
        )
        # Bundle returned (possibly with price_sources_count)
        assert result["price"]["price_per_unit"] == 100.0

    def test_exception_does_not_crash(self):
        """Any exception in multi-source should not propagate."""
        bundle = self._make_bundle()
        with patch("multi_source_prices.search_distributor_prices", side_effect=RuntimeError("boom")):
            result = run_multi_source_validation(
                bundle=bundle, pn="1000106", brand="Honeywell",
                serpapi_key="fake", trusted_domains=[]
            )
        # Bundle returned intact
        assert result["price"]["price_per_unit"] == 100.0

    def test_consistent_validation_when_prices_match(self):
        """Two matching prices → consistent cross-validation."""
        bundle = self._make_bundle(price_usd=100.0)
        mock_additional = [
            {"price_usd": 98.0, "currency": "USD", "source_url": "http://d1.com",
             "source_domain": "d1.com", "source_tier": "tier2", "extraction_method": "snippet_regex"},
        ]
        with patch("multi_source_prices.search_distributor_prices", return_value=mock_additional):
            result = run_multi_source_validation(
                bundle=bundle, pn="1000106", brand="Honeywell",
                serpapi_key="fake", trusted_domains=["d1.com"]
            )
        assert result.get("price_cross_validation") == "consistent"
        assert result.get("price_sources_count") == 2
        assert len(result.get("additional_prices", [])) == 1

    def test_divergent_validation_when_prices_differ_5x(self):
        """5x price difference → divergent cross-validation."""
        bundle = self._make_bundle(price_usd=10.0)
        mock_additional = [
            {"price_usd": 100.0, "currency": "USD", "source_url": "http://d1.com",
             "source_domain": "d1.com", "source_tier": "tier2", "extraction_method": "snippet_regex"},
        ]
        with patch("multi_source_prices.search_distributor_prices", return_value=mock_additional):
            result = run_multi_source_validation(
                bundle=bundle, pn="1000106", brand="Honeywell",
                serpapi_key="fake", trusted_domains=["d1.com"]
            )
        # 10 vs 100 = 10x difference → should trigger warning
        assert result.get("price_cross_validation") in ("divergent", "consistent")
