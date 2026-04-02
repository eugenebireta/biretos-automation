import os
import sys

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from price_source_replacement import (
    choose_better_replacement_candidate,
    materialize_source_replacement_surface,
)


class TestPriceSourceReplacement:

    def test_admissible_replacement_is_materialized_explicitly(self):
        current = {
            "price_status": "no_price_found",
            "price_source_tier": "ru_b2b",
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_url": "https://weak.example/item/1011893-RU",
        }
        replacement = {
            "price_source_url": "https://official.example/product/1011893-RU",
            "price_source_tier": "official",
            "price_source_engine": "google_us",
            "price_source_structured_match_location": "title",
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_clean_product_page": True,
            "price_source_exact_title_pn_match": True,
        }
        result = materialize_source_replacement_surface(
            current,
            admissible_replacement_candidate=replacement,
        )
        assert result["price_source_replacement_candidate_found"] is True
        assert result["price_source_admissible_replacement_confirmed"] is True
        assert result["price_source_terminal_weak_lineage"] is False
        assert result["price_source_replacement_tier"] == "official"
        assert result["price_source_replacement_reason_code"] == "admissible_replacement_confirmed"

    def test_weak_exact_lineage_without_replacement_becomes_terminal(self):
        current = {
            "price_status": "no_price_found",
            "price_source_tier": "unknown",
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_url": "https://weak.example/item/1006186",
        }
        result = materialize_source_replacement_surface(current)
        assert result["price_source_replacement_candidate_found"] is False
        assert result["price_source_admissible_replacement_confirmed"] is False
        assert result["price_source_terminal_weak_lineage"] is True
        assert result["price_source_replacement_reason_code"] == "weak_exact_lineage_no_admissible_replacement"

    def test_current_admissible_exact_source_is_confirmed_without_separate_replacement(self):
        current = {
            "price_status": "no_price_found",
            "price_source_tier": "official",
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_url": "https://sps-support.honeywell.com/s/article/1012541-Leightning-L3Hs-Helmet-Earmuff-3711-3712-3721-Adapter-Data-Sheet-Spanish",
        }
        result = materialize_source_replacement_surface(current)
        assert result["price_source_replacement_candidate_found"] is False
        assert result["price_source_admissible_replacement_confirmed"] is True
        assert result["price_source_terminal_weak_lineage"] is False
        assert result["price_source_replacement_reason_code"] == "source_already_admissible"

    def test_no_exact_lineage_does_not_become_terminal_replacement_case(self):
        current = {
            "price_status": "no_price_found",
            "price_source_tier": "weak",
            "price_source_exact_product_lineage_confirmed": False,
            "price_source_url": "https://weak.example/search?q=00020211",
        }
        result = materialize_source_replacement_surface(current)
        assert result["price_source_terminal_weak_lineage"] is False
        assert result["price_source_replacement_reason_code"] == "no_exact_lineage_for_replacement"

    def test_choose_better_replacement_prefers_higher_tier_exact_candidate(self):
        weak = {
            "price_source_tier": "industrial",
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_clean_product_page": True,
            "price_source_exact_title_pn_match": True,
        }
        strong = {
            "price_source_tier": "official",
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_clean_product_page": True,
            "price_source_exact_title_pn_match": True,
        }
        chosen = choose_better_replacement_candidate(weak, strong)
        assert chosen["price_source_tier"] == "official"
