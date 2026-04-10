"""Tests for brand_knowledge.py YAML registry (Block 4)."""
from __future__ import annotations

import os
import sys

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import brand_knowledge as bk


def setup_function():
    bk.clear_cache()


class TestLoadBrandConfig:
    def test_honeywell_loads(self):
        config = bk.load_brand_config("Honeywell")
        assert config is not None
        assert config["brand"] == "Honeywell"

    def test_case_insensitive(self):
        config = bk.load_brand_config("honeywell")
        assert config is not None
        assert config["brand"] == "Honeywell"

    def test_all_caps_via_alias(self):
        config = bk.load_brand_config("HONEYWELL")
        assert config is not None

    def test_peha_loads(self):
        config = bk.load_brand_config("PEHA")
        assert config is not None
        assert config["brand"] == "PEHA"

    def test_unknown_brand_returns_none(self):
        config = bk.load_brand_config("NonExistentBrand_XYZ999")
        assert config is None

    def test_empty_string_returns_none(self):
        config = bk.load_brand_config("")
        assert config is None

    def test_caching_same_object(self):
        """Second call returns same object (cached)."""
        c1 = bk.load_brand_config("Honeywell")
        c2 = bk.load_brand_config("Honeywell")
        assert c1 is c2


class TestGetProductFamily:
    def test_peha_6digit_pn(self):
        bk.clear_cache()
        assert bk.get_product_family("Honeywell", "153711") == "PEHA"

    def test_peha_5digit_pn(self):
        bk.clear_cache()
        assert bk.get_product_family("Honeywell", "22811") == "PEHA"

    def test_honeywell_7digit_pn(self):
        bk.clear_cache()
        result = bk.get_product_family("Honeywell", "1000106")
        assert result == "Honeywell"

    def test_esser_8xxxxxx_pn(self):
        bk.clear_cache()
        result = bk.get_product_family("Honeywell", "804950")
        assert result == "Esser"

    def test_unknown_brand_returns_none(self):
        bk.clear_cache()
        result = bk.get_product_family("NonExistentBrand_XYZ", "12345")
        assert result is None


class TestGetTrustedDomains:
    def test_honeywell_has_tier1_domains(self):
        bk.clear_cache()
        domains = bk.get_trusted_domains("Honeywell")
        assert "honeywell.com" in domains

    def test_peha_pn_includes_peha_domains(self):
        bk.clear_cache()
        domains = bk.get_trusted_domains("Honeywell", pn="153711")
        # PEHA sub-brand domains should be included
        assert "peha.de" in domains
        # Honeywell parent domains also included
        assert "honeywell.com" in domains

    def test_no_duplicates(self):
        bk.clear_cache()
        domains = bk.get_trusted_domains("Honeywell", pn="153711")
        assert len(domains) == len(set(domains))

    def test_unknown_brand_returns_empty_list(self):
        bk.clear_cache()
        domains = bk.get_trusted_domains("NonExistentBrand")
        assert domains == []

    def test_peha_direct_config(self):
        bk.clear_cache()
        domains = bk.get_trusted_domains("PEHA")
        assert "peha.de" in domains
        assert "conrad.de" in domains


class TestGetDatasheetQuery:
    def test_honeywell_template_used(self):
        bk.clear_cache()
        q = bk.get_datasheet_query("Honeywell", "1000106")
        assert "1000106" in q
        assert "honeywell" in q.lower()
        assert "filetype:pdf" in q

    def test_peha_template(self):
        bk.clear_cache()
        q = bk.get_datasheet_query("PEHA", "153711")
        assert "153711" in q

    def test_unknown_brand_fallback(self):
        bk.clear_cache()
        q = bk.get_datasheet_query("UnknownBrand", "TEST001")
        assert "TEST001" in q
        assert "filetype:pdf" in q


class TestListKnownBrands:
    def test_returns_list(self):
        brands = bk.list_known_brands()
        assert isinstance(brands, list)

    def test_honeywell_in_list(self):
        brands = bk.list_known_brands()
        assert "Honeywell" in brands

    def test_peha_in_list(self):
        brands = bk.list_known_brands()
        assert "PEHA" in brands
