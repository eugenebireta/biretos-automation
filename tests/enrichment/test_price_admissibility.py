import os
import sys


_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from price_admissibility import materialize_price_admissibility


def test_101411_type_visible_price_with_semantic_identity_barrier_becomes_ambiguous_offer():
    result = materialize_price_admissibility(
        {
            "part_number": "101411",
            "price_status": "public_price",
            "price_per_unit": 60.15,
            "currency": "EUR",
            "offer_qty": 1,
            "offer_unit_basis": "piece",
            "source_tier": "authorized",
            "http_status": 200,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_lineage_reason_code": "structured_exact_product_page",
            "price_source_clean_product_page": True,
            "page_product_class": "PEHA cover frame switchgear",
            "public_price_rejection_reasons": [],
        }
    )

    assert result["string_lineage_status"] == "exact"
    assert result["commercial_identity_status"] == "component_or_accessory"
    assert result["offer_admissibility_status"] == "ambiguous_offer"
    assert "PRICE_SEMANTIC_IDENTITY_MISMATCH" in result["price_admissibility_reason_codes"]


def test_104011_type_preserves_historical_state_conflict():
    result = materialize_price_admissibility(
        {
            "part_number": "104011",
            "price_status": "no_price_found",
            "source_tier": "authorized",
            "http_status": 200,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_lineage_reason_code": "structured_exact_product_page",
            "price_source_clean_product_page": True,
            "historical_state_price_status": "closed",
        }
    )

    assert result["offer_admissibility_status"] == "no_price_found"
    assert result["staleness_or_conflict_status"] == "stale_historical_claim"
    assert result["price_admissibility_review_bucket"] == "STALE_TRUTH_REVIEW"


def test_page_url_semantics_can_trigger_component_identity_barrier():
    result = materialize_price_admissibility(
        {
            "part_number": "104011",
            "price_status": "no_price_found",
            "source_tier": "industrial",
            "http_status": 200,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_lineage_reason_code": "structured_exact_product_page",
            "price_source_clean_product_page": True,
            "page_url": "https://www.conrad.nl/nl/p/peha-by-honeywell-104011-wipschakelaar-afdekking-zuiver-wit-1-stuk-s-2855045.html",
            "price_source_seen": True,
            "historical_state_price_status": "closed",
        }
    )

    assert result["string_lineage_status"] == "exact"
    assert result["commercial_identity_status"] == "component_or_accessory"
    assert result["offer_admissibility_status"] == "no_price_found"
    assert result["staleness_or_conflict_status"] == "stale_historical_claim"


def test_00020211_type_pack_unit_ambiguity_becomes_ambiguous_offer():
    result = materialize_price_admissibility(
        {
            "part_number": "00020211",
            "price_status": "public_price",
            "price_per_unit": 10.18,
            "currency": "USD",
            "offer_qty": 2,
            "offer_unit_basis": "piece",
            "source_tier": "authorized",
            "http_status": 200,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_lineage_reason_code": "structured_exact_product_page",
            "price_source_clean_product_page": True,
            "page_product_class": "cover frame switchgear",
            "public_price_rejection_reasons": ["ambiguous_pack_unit"],
        }
    )

    assert result["commercial_identity_status"] == "pack_or_bundle_variant"
    assert result["offer_admissibility_status"] == "ambiguous_offer"
    assert "PRICE_PACK_UNIT_AMBIGUITY" in result["price_admissibility_reason_codes"]


def test_1011894_ru_type_exact_lineage_plus_blocked_surface_becomes_blocked_terminal_status():
    result = materialize_price_admissibility(
        {
            "part_number": "1011894-RU",
            "price_status": "no_price_found",
            "source_tier": "ru_b2b",
            "http_status": 403,
            "blocked_ui_detected": True,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_lineage_reason_code": "structured_exact_product_page_weak_tier",
        }
    )

    assert result["string_lineage_status"] == "weak"
    assert result["offer_admissibility_status"] == "blocked_or_auth_gated"
    assert result["price_admissibility_review_bucket"] == "PRICE_BLOCKED_SURFACE"


def test_clean_public_price_case_stays_admissible_public_price():
    result = materialize_price_admissibility(
        {
            "part_number": "1011994",
            "price_status": "public_price",
            "price_per_unit": 9.95,
            "currency": "USD",
            "offer_qty": 1,
            "offer_unit_basis": "piece",
            "source_tier": "official",
            "http_status": 200,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_lineage_reason_code": "structured_exact_product_page",
            "price_source_clean_product_page": True,
            "page_product_class": "product",
            "public_price_rejection_reasons": [],
        }
    )

    assert result["commercial_identity_status"] == "exact_product"
    assert result["offer_admissibility_status"] == "admissible_public_price"
    assert result["price_admissibility_review_required"] is False


def test_exact_public_price_with_blocked_tail_preserves_admissible_offer_and_conflict_review():
    result = materialize_price_admissibility(
        {
            "part_number": "1012541",
            "price_status": "public_price",
            "price_per_unit": 68.9,
            "currency": "PLN",
            "offer_qty": 1,
            "offer_unit_basis": "piece",
            "source_tier": "industrial",
            "http_status": 200,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_lineage_reason_code": "structured_exact_product_page",
            "price_source_clean_product_page": True,
            "page_product_class": "Nauszniki nahełmowe HOWARD L3H (1012541)",
            "public_price_rejection_reasons": [],
            "price_source_surface_conflict_detected": True,
            "blocked_ui_detected": False,
            "blocked_surface_page_url": "https://www.vseinstrumenti.ru/product/protivoshumnye-naushniki-honeywell-lajtning-l3n-s-krepleniyami-iz-stalnoj-provoloki-na-kasku-1012541-2151517/",
        }
    )

    assert result["commercial_identity_status"] == "exact_product"
    assert result["offer_admissibility_status"] == "admissible_public_price"
    assert result["staleness_or_conflict_status"] == "unresolved_conflict"
    assert result["price_admissibility_review_bucket"] == "STALE_TRUTH_REVIEW"
    assert "PRICE_UNRESOLVED_CONFLICT" in result["price_admissibility_reason_codes"]
