"""Tests for full JSON-LD field extraction (Block 2)."""
from __future__ import annotations

import os
import sys

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from photo_pipeline import (
    extract_full_jsonld,
    extract_all_jsonld_from_html,
    _jld_extract_brand,
    _jld_extract_dimensions,
    _jld_extract_seller,
    _jld_extract_rating,
    _jld_extract_additional_props,
    _jld_truncate,
)


class TestExtractFullJsonld:
    def test_full_product_data_extracted(self):
        data = {
            "name": "Frame 3-Gang NOVA",
            "sku": "153711",
            "mpn": "153711",
            "gtin13": "4011160153711",
            "brand": {"name": "PEHA"},
            "description": "3-gang frame for NOVA series",
            "image": "https://example.com/img.jpg",
            "category": "Electrical Accessories",
            "weight": "0.1 kg",
            "aggregateRating": {"ratingValue": 4.5, "reviewCount": 12},
            "offers": {
                "price": "12.50",
                "priceCurrency": "EUR",
                "priceValidUntil": "2026-12-31",
                "itemCondition": "NewCondition",
                "availability": "InStock",
                "seller": {"name": "Conrad Electronic"},
            },
        }
        result = extract_full_jsonld(data)
        assert result["name"] == "Frame 3-Gang NOVA"
        assert result["sku"] == "153711"
        assert result["mpn"] == "153711"
        assert result["gtin13"] == "4011160153711"
        assert result["brand"] == "PEHA"
        assert result["description"] == "3-gang frame for NOVA series"
        assert result["category"] == "Electrical Accessories"
        assert result["price"] == "12.50"
        assert result["currency"] == "EUR"
        assert result["price_valid_until"] == "2026-12-31"
        assert result["availability"] == "InStock"
        assert result["seller"] == "Conrad Electronic"
        assert result["aggregate_rating"]["value"] == 4.5
        assert result["aggregate_rating"]["count"] == 12

    def test_minimal_data_graceful(self):
        data = {"name": "Product X", "@type": "Product"}
        result = extract_full_jsonld(data)
        assert result["name"] == "Product X"
        assert result["sku"] is None
        assert result["mpn"] is None
        assert result["brand"] is None
        assert result["dimensions"] is None
        assert result["aggregate_rating"] is None
        assert result["additional_properties"] is None

    def test_brand_as_dict_extracts_name(self):
        data = {"brand": {"name": "Honeywell", "@type": "Brand"}}
        result = extract_full_jsonld(data)
        assert result["brand"] == "Honeywell"

    def test_brand_as_string_preserved(self):
        data = {"brand": "Esser"}
        result = extract_full_jsonld(data)
        assert result["brand"] == "Esser"

    def test_offers_as_list_uses_first(self):
        data = {
            "offers": [
                {"price": "10.00", "priceCurrency": "USD"},
                {"price": "20.00", "priceCurrency": "EUR"},
            ]
        }
        result = extract_full_jsonld(data)
        assert result["price"] == "10.00"
        assert result["currency"] == "USD"

    def test_additional_properties_first_20(self):
        props = [{"name": f"key{i}", "value": f"val{i}"} for i in range(25)]
        data = {"additionalProperty": props}
        result = extract_full_jsonld(data)
        assert result["additional_properties"] is not None
        assert len(result["additional_properties"]) == 20
        assert result["additional_properties"][0]["name"] == "key0"

    def test_description_truncated_at_500(self):
        data = {"description": "x" * 600}
        result = extract_full_jsonld(data)
        assert len(result["description"]) == 500

    def test_dimensions_extracted(self):
        data = {"width": "80mm", "height": "120mm", "depth": "10mm"}
        result = extract_full_jsonld(data)
        assert result["dimensions"] == {"width": "80mm", "height": "120mm", "depth": "10mm"}

    def test_dimensions_empty_when_missing(self):
        data = {"name": "Product"}
        result = extract_full_jsonld(data)
        assert result["dimensions"] is None

    def test_availability_short_form_from_schemaorg_url(self):
        data = {"availability": "http://schema.org/InStock"}
        result = extract_full_jsonld(data)
        assert result["availability"] == "InStock"


class TestExtractAllJsonldFromHtml:
    def test_product_jsonld_extracted(self):
        html = """
        <html><body>
        <script type="application/ld+json">
        {"@type": "Product", "name": "Frame NOVA", "sku": "153711",
         "brand": {"name": "PEHA"},
         "offers": {"price": "12.50", "priceCurrency": "EUR"}}
        </script>
        </body></html>
        """
        result = extract_all_jsonld_from_html(html, "153711")
        assert result is not None
        assert result["name"] == "Frame NOVA"
        assert result["brand"] == "PEHA"
        assert result["price"] == "12.50"

    def test_non_product_type_skipped(self):
        html = """
        <html><body>
        <script type="application/ld+json">
        {"@type": "Organization", "name": "Example Corp"}
        </script>
        </body></html>
        """
        result = extract_all_jsonld_from_html(html, "123")
        assert result is None

    def test_no_jsonld_returns_none(self):
        html = "<html><body><p>No JSON-LD here</p></body></html>"
        result = extract_all_jsonld_from_html(html, "123")
        assert result is None

    def test_malformed_jsonld_skipped(self):
        html = """
        <html><body>
        <script type="application/ld+json">{ INVALID JSON </script>
        <script type="application/ld+json">{"@type": "Product", "name": "OK"}</script>
        </body></html>
        """
        result = extract_all_jsonld_from_html(html, "")
        assert result is not None
        assert result["name"] == "OK"
