import os
import sys

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from price_lineage import choose_better_price_lineage_candidate, materialize_pre_llm_price_lineage


class TestPriceLineage:

    def test_exact_structured_page_confirms_lineage_before_llm(self):
        html = """
        <html>
          <head>
            <title>Honeywell 1011893-RU Harness</title>
            <script type="application/ld+json">
              {"@context":"https://schema.org","@type":"Product","mpn":"1011893-RU","name":"Honeywell 1011893-RU Harness"}
            </script>
          </head>
          <body>
            <h1>Honeywell 1011893-RU Harness</h1>
            <div class="product-detail">Honeywell 1011893-RU</div>
          </body>
        </html>
        """
        result = materialize_pre_llm_price_lineage(
            pn="1011893-RU",
            price_result={
                "price_status": "no_price_found",
                "source_url": "https://example.com/product/1011893-RU",
                "source_tier": "authorized",
                "source_type": "authorized_distributor",
            },
            html=html,
            source_url="https://example.com/product/1011893-RU",
            source_type="authorized_distributor",
            source_tier="authorized",
            source_engine="google_us",
            content_type="text/html; charset=utf-8",
            status_code=200,
        )
        assert result["price_source_exact_title_pn_match"] is True
        assert result["price_source_exact_h1_pn_match"] is True
        assert result["price_source_exact_jsonld_pn_match"] is True
        assert result["price_source_clean_product_page"] is True
        assert result["price_source_exact_product_lineage_confirmed"] is True
        assert result["price_source_lineage_confirmed"] is True
        assert result["price_source_lineage_reason_code"] == "structured_exact_product_page"

    def test_exact_structured_page_on_weak_tier_stays_non_reviewable(self):
        html = """
        <html>
          <head><title>Honeywell 1011893-RU Harness</title></head>
          <body>
            <h1>Honeywell 1011893-RU Harness</h1>
            <div class="product-card">Honeywell 1011893-RU</div>
          </body>
        </html>
        """
        result = materialize_pre_llm_price_lineage(
            pn="1011893-RU",
            price_result={
                "price_status": "no_price_found",
                "source_url": "https://ruslader.ru/product/1011893-RU",
                "source_tier": "ru_b2b",
                "source_type": "ru_b2b",
            },
            html=html,
            source_url="https://ruslader.ru/product/1011893-RU",
            source_type="ru_b2b",
            source_tier="ru_b2b",
            source_engine="google_us",
            content_type="text/html",
            status_code=200,
        )
        assert result["price_source_exact_product_lineage_confirmed"] is True
        assert result["price_source_lineage_confirmed"] is True
        assert result["price_reviewable_no_price_candidate"] is False
        assert result["price_source_lineage_reason_code"] == "structured_exact_product_page_weak_tier"

    def test_noisy_family_page_does_not_confirm_lineage(self):
        html = """
        <html>
          <head><title>Honeywell 1006186 Family Listing</title></head>
          <body>
            <h1>Family Listing for Honeywell 1006186</h1>
            <div>similar products and accessories</div>
          </body>
        </html>
        """
        result = materialize_pre_llm_price_lineage(
            pn="1006186",
            price_result={
                "price_status": "no_price_found",
                "source_url": "https://example.com/family/1006186",
                "source_tier": "official",
                "source_type": "other",
            },
            html=html,
            source_url="https://example.com/family/1006186",
            source_type="other",
            source_tier="official",
            source_engine="google_us",
            content_type="text/html",
            status_code=200,
        )
        assert result["price_source_exact_product_lineage_confirmed"] is False
        assert result["price_source_lineage_confirmed"] is False
        assert result["price_source_lineage_reason_code"] == "structured_page_not_clean"

    def test_access_denied_page_stays_non_lineage(self):
        html = "<html><head><title>Access Denied</title></head><body><h1>Access Denied</h1></body></html>"
        result = materialize_pre_llm_price_lineage(
            pn="00020211",
            price_result={
                "price_status": "no_price_found",
                "source_url": "https://example.com/blocked/00020211",
                "source_tier": "official",
                "source_type": "other",
            },
            html=html,
            source_url="https://example.com/blocked/00020211",
            source_type="other",
            source_tier="official",
            source_engine="google_us",
            content_type="text/html",
            status_code=403,
        )
        assert result["price_source_seen"] is True
        assert result["price_source_exact_product_lineage_confirmed"] is False
        assert result["price_source_lineage_reason_code"] == "access_denied_or_non_html"

    def test_official_article_url_shell_confirms_exact_lineage_without_reviewable_page(self):
        html = "<html><head><title>Honeywell SPS Community</title></head><body><div>community shell</div></body></html>"
        result = materialize_pre_llm_price_lineage(
            pn="1012541",
            price_result={
                "price_status": "no_price_found",
                "source_url": "https://sps-support.honeywell.com/s/article/1012541-Leightning-L3Hs-Helmet-Earmuff-3711-3712-3721-Adapter-Data-Sheet-Spanish",
                "source_tier": "official",
                "source_type": "other",
            },
            html=html,
            source_url="https://sps-support.honeywell.com/s/article/1012541-Leightning-L3Hs-Helmet-Earmuff-3711-3712-3721-Adapter-Data-Sheet-Spanish",
            source_type="other",
            source_tier="official",
            source_engine="google_us",
            content_type="text/html; charset=utf-8",
            status_code=200,
        )
        assert result["price_source_structured_match_location"] == "official_article_url"
        assert result["price_source_exact_product_lineage_confirmed"] is True
        assert result["price_source_lineage_confirmed"] is True
        assert result["price_source_clean_product_page"] is False
        assert result["price_exact_product_page"] is False
        assert result["price_source_lineage_reason_code"] == "official_article_url_exact_match"
        assert result["price_no_price_reason_code"] == "exact_page_context_not_clean"
        assert result["price_reviewable_no_price_candidate"] is False

    def test_official_article_url_shell_requires_official_tier(self):
        html = "<html><head><title>Honeywell SPS Community</title></head><body><div>community shell</div></body></html>"
        result = materialize_pre_llm_price_lineage(
            pn="1012541",
            price_result={
                "price_status": "no_price_found",
                "source_url": "https://sps-support.honeywell.com/s/article/1012541-Leightning-L3Hs-Helmet-Earmuff-3711-3712-3721-Adapter-Data-Sheet-Spanish",
                "source_tier": "unknown",
                "source_type": "other",
            },
            html=html,
            source_url="https://sps-support.honeywell.com/s/article/1012541-Leightning-L3Hs-Helmet-Earmuff-3711-3712-3721-Adapter-Data-Sheet-Spanish",
            source_type="other",
            source_tier="unknown",
            source_engine="google_us",
            content_type="text/html; charset=utf-8",
            status_code=200,
        )
        assert result["price_source_exact_product_lineage_confirmed"] is False
        assert result["price_source_structured_match_location"] == ""
        assert result["price_source_lineage_reason_code"] == "structured_exact_match_missing"

    def test_choose_better_price_lineage_candidate_prefers_confirmed_lineage(self):
        weak = {
            "price_source_seen": True,
            "price_source_exact_product_lineage_confirmed": False,
            "price_source_clean_product_page": False,
            "price_source_exact_title_pn_match": False,
            "price_source_exact_h1_pn_match": False,
            "price_source_exact_jsonld_pn_match": False,
            "price_source_exact_product_context_match": False,
        }
        strong = {
            "price_source_seen": True,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_clean_product_page": True,
            "price_source_exact_title_pn_match": True,
            "price_source_exact_h1_pn_match": True,
            "price_source_exact_jsonld_pn_match": False,
            "price_source_exact_product_context_match": False,
        }
        chosen = choose_better_price_lineage_candidate(weak, strong)
        assert chosen["price_source_exact_product_lineage_confirmed"] is True
