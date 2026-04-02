from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_price_only_scout_pilot as pilot  # noqa: E402


def test_build_candidate_index_dedupes_urls_and_prefers_higher_tier():
    price_cache_payload = {
        "entries_by_pn": {
            "1000106": [
                {"source_url": "https://example.com/a", "source_type": "authorized_distributor", "source_tier": "authorized"},
            ]
        }
    }
    surface_cache_payload = {
        "entries_by_pn": {
            "1000106": [
                {"source_url": "https://example.com/a", "source_type": "other", "source_tier": "industrial"},
                {"source_url": "https://example.com/b", "source_type": "other", "source_tier": "official"},
            ]
        }
    }

    index = pilot.build_candidate_index_from_caches(
        price_cache_payload=price_cache_payload,
        surface_cache_payload=surface_cache_payload,
    )

    assert [row["url"] for row in index["1000106"]] == ["https://example.com/b", "https://example.com/a"]
    assert index["1000106"][1]["source_tier"] == "authorized"


def test_select_seeded_rows_filters_out_rows_without_candidates():
    rows = [
        {"pn": "1000106", "name": "A", "brand": "Honeywell", "expected_category": "Беруши"},
        {"pn": "9999999", "name": "B", "brand": "Honeywell", "expected_category": "Unknown"},
    ]
    candidate_index = {"1000106": [{"url": "https://example.com/a"}]}

    selected = pilot.select_seeded_rows(rows, candidate_index, limit=20)

    assert selected == [rows[0]]


def test_summarize_results_materializes_explicit_success_gates():
    summary = pilot.summarize_results(
        [
            {
                "price_status": "public_price",
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_surface_conflict_detected": False,
                "cache_fallback_used": False,
                "transient_failure_codes": [],
                "fx_normalization_status": "normalized",
            },
            {
                "price_status": "rfq_only",
                "price_source_exact_product_lineage_confirmed": False,
                "price_source_surface_conflict_detected": False,
                "cache_fallback_used": True,
                "transient_failure_codes": ["openai_quota"],
                "fx_normalization_status": "fx_gap",
            },
        ],
        requested_limit=2,
        selected_rows_count=2,
        prior_run_count=3,
    )

    assert summary["price_status_counts"] == {"public_price": 1, "rfq_only": 1}
    assert summary["exact_product_lineage_confirmed_count"] == 1
    assert summary["cache_fallback_used_count"] == 1
    assert summary["transient_failure_row_count"] == 1
    assert summary["fx_status_counts"] == {"normalized": 1, "fx_gap": 1}
    assert summary["fx_gap_count"] == 1
    assert summary["success_gates"]["requested_limit_satisfied"]["passed"] is True
    assert summary["success_gates"]["every_selected_row_processed"]["passed"] is True
    assert summary["success_gates"]["zero_surface_conflicts"]["passed"] is True
