import os
import sys

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from no_price_coverage import choose_better_no_price_candidate, materialize_no_price_coverage


class TestNoPriceCoverage:

    def test_exact_quote_required_page_materializes_reviewable_candidate(self):
        result = materialize_no_price_coverage(
            {
                "price_status": "hidden_price",
                "source_url": "https://example.com/product/00020211",
                "source_tier": "authorized",
                "source_type": "authorized_distributor",
                "pn_exact_confirmed": True,
                "page_context_clean": True,
                "stock_status": "rfq",
                "quote_cta_url": "https://example.com/quote/00020211",
            }
        )
        assert result["price_source_seen"] is True
        assert result["price_source_lineage_confirmed"] is True
        assert result["price_exact_product_page"] is True
        assert result["price_quote_required"] is True
        assert result["price_no_price_reason_code"] == "quote_required"
        assert result["price_reviewable_no_price_candidate"] is True

    def test_source_seen_without_exact_lineage_stays_non_reviewable(self):
        result = materialize_no_price_coverage(
            {
                "price_status": "no_price_found",
                "page_context_clean": True,
            },
            observed_candidate={
                "url": "https://example.com/search?q=00020211",
                "source_type": "authorized_distributor",
                "source_tier": "authorized",
                "engine": "google_us",
            },
        )
        assert result["price_source_seen"] is True
        assert result["price_source_lineage_confirmed"] is False
        assert result["price_source_observed_only"] is True
        assert result["price_no_price_reason_code"] == "source_seen_no_exact_page"
        assert result["price_reviewable_no_price_candidate"] is False

    def test_weak_source_tier_does_not_become_reviewable_candidate(self):
        result = materialize_no_price_coverage(
            {
                "price_status": "hidden_price",
                "source_url": "https://example.com/product/1006186",
                "source_tier": "unknown",
                "pn_exact_confirmed": True,
                "page_context_clean": True,
                "quote_cta_url": "https://example.com/quote/1006186",
            }
        )
        assert result["price_source_lineage_confirmed"] is True
        assert result["price_exact_product_page"] is True
        assert result["price_reviewable_no_price_candidate"] is False

    def test_explicit_exact_lineage_fields_are_preserved_for_non_clean_official_article(self):
        result = materialize_no_price_coverage(
            {
                "price_status": "no_price_found",
                "source_url": "https://sps-support.honeywell.com/s/article/1012541-Leightning-L3Hs-Helmet-Earmuff-3711-3712-3721-Adapter-Data-Sheet-Spanish",
                "source_tier": "official",
                "source_type": "other",
                "price_source_lineage_confirmed": True,
                "price_source_exact_product_lineage_confirmed": True,
                "price_exact_product_page": False,
                "price_page_context_clean": False,
            }
        )
        assert result["price_source_lineage_confirmed"] is True
        assert result["price_exact_product_page"] is False
        assert result["price_no_price_reason_code"] == "exact_page_context_not_clean"
        assert result["price_reviewable_no_price_candidate"] is False
        assert result["price_source_observed_only"] is False

    def test_choose_better_candidate_prefers_reviewable_exact_lineage(self):
        observed_only = materialize_no_price_coverage(
            {"price_status": "no_price_found"},
            observed_candidate={
                "url": "https://example.com/listing/1000106",
                "source_tier": "authorized",
                "source_type": "authorized_distributor",
            },
        )
        exact_quote = materialize_no_price_coverage(
            {
                "price_status": "hidden_price",
                "source_url": "https://example.com/product/1000106",
                "source_tier": "authorized",
                "source_type": "authorized_distributor",
                "pn_exact_confirmed": True,
                "page_context_clean": True,
                "quote_cta_url": "https://example.com/quote/1000106",
            }
        )
        chosen = choose_better_no_price_candidate(observed_only, exact_quote)
        assert chosen["price_source_lineage_confirmed"] is True
        assert chosen["price_reviewable_no_price_candidate"] is True
