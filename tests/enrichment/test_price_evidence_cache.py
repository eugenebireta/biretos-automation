"""Tests for deterministic bounded-run price evidence cache fallback."""
import json
import os
import sys


_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from price_evidence_cache import (  # noqa: E402
    CURRENT_PRICE_POLICY_VERSION,
    PRICE_CACHE_SCHEMA_VERSION,
    build_cache_entry_from_bundle,
    build_cache_payload_from_run_dirs,
    select_cached_price_fallback,
)


def _safe_bundle(
    *,
    pn: str = "010130.10",
    price_status: str = "public_price",
    source_url: str = "https://example.com/product/01013010",
    source_tier: str = "authorized",
    field_price_status: str = "ACCEPTED",
    pn_exact_confirmed: bool = True,
    page_context_clean: bool = True,
    rejection_reasons: list[str] | None = None,
    category_mismatch: bool = False,
    brand_mismatch: bool = False,
) -> dict:
    return {
        "pn": pn,
        "generated_at": "2026-03-27T00:00:00Z",
        "field_statuses_v2": {
            "price_status": field_price_status,
        },
        "policy_decision_v2": {
            "policy_version": CURRENT_PRICE_POLICY_VERSION,
        },
        "price": {
            "price_status": price_status,
            "price_per_unit": 225.0,
            "currency": "EUR",
            "rub_price": 21375.0,
            "fx_rate_used": 95.0,
            "fx_provider": "stub",
            "price_confidence": 90,
            "source_url": source_url,
            "source_type": "other",
            "source_tier": source_tier,
            "stock_status": "in_stock",
            "offer_unit_basis": "piece",
            "offer_qty": 1,
            "lead_time_detected": False,
            "suffix_conflict": False,
            "category_mismatch": category_mismatch,
            "page_product_class": "Module",
            "brand_mismatch": brand_mismatch,
            "price_sample_size": 1,
            "pn_exact_confirmed": pn_exact_confirmed,
            "page_context_clean": page_context_clean,
            "public_price_rejection_reasons": rejection_reasons or [],
        },
    }


class TestPriceEvidenceCache:

    def test_build_cache_entry_accepts_prior_admissible_price_bundle(self):
        entry = build_cache_entry_from_bundle(
            _safe_bundle(),
            source_run_id="phase_a_v2_sanity_20260326T222242Z",
            bundle_ref="evidence_010130.10.json",
        )
        assert entry is not None
        assert entry["schema_version"] == PRICE_CACHE_SCHEMA_VERSION
        assert entry["pn_primary"] == "010130.10"
        assert entry["source_tier"] == "authorized"
        assert entry["exact_product_page"] is True

    def test_build_cache_entry_rejects_blocked_false_public_price(self):
        entry = build_cache_entry_from_bundle(
            _safe_bundle(
                source_tier="unknown",
                rejection_reasons=["source_tier_not_admissible"],
                field_price_status="INSUFFICIENT",
            ),
            source_run_id="phase_a_v2_sanity_20260326T222242Z",
            bundle_ref="evidence_1006186.json",
        )
        assert entry is None

    def test_build_cache_payload_indexes_only_safe_entries(self, tmp_path):
        run_dir = tmp_path / "phase_a_v2_sanity_20260326T222242Z"
        evidence_dir = run_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "evidence_safe.json").write_text(
            json.dumps(_safe_bundle(), ensure_ascii=False),
            encoding="utf-8",
        )
        (evidence_dir / "evidence_blocked.json").write_text(
            json.dumps(_safe_bundle(pn="1006186", source_tier="unknown", field_price_status="INSUFFICIENT"), ensure_ascii=False),
            encoding="utf-8",
        )
        payload = build_cache_payload_from_run_dirs([run_dir])
        assert payload["schema_version"] == PRICE_CACHE_SCHEMA_VERSION
        assert payload["entry_count"] == 1
        assert "010130.10" in payload["entries_by_pn"]
        assert "1006186" not in payload["entries_by_pn"]

    def test_select_cached_price_fallback_reuses_exact_url_on_quota_failure(self):
        payload = {
            "schema_version": PRICE_CACHE_SCHEMA_VERSION,
            "policy_version": CURRENT_PRICE_POLICY_VERSION,
            "entries_by_pn": {
                "010130.10": [
                    build_cache_entry_from_bundle(
                        _safe_bundle(),
                        source_run_id="phase_a_v2_sanity_20260326T222242Z",
                        bundle_ref="evidence_010130.10.json",
                    )
                ]
            },
        }
        result = select_cached_price_fallback(
            pn="010130.10",
            candidates=[
                {
                    "url": "https://example.com/product/01013010",
                    "source_tier": "authorized",
                }
            ],
            cache_payload=payload,
            failure_codes=["openai_quota"],
        )
        assert result is not None
        assert result["cache_fallback_used"] is True
        assert result["cache_source_run_id"] == "phase_a_v2_sanity_20260326T222242Z"
        assert result["price_status"] == "public_price"
        assert result["cache_fallback_reason"] == "llm_quota"
        assert result["transient_failure_codes"] == ["llm_quota"]

    def test_select_cached_price_fallback_rejects_source_url_mismatch(self):
        payload = {
            "schema_version": PRICE_CACHE_SCHEMA_VERSION,
            "policy_version": CURRENT_PRICE_POLICY_VERSION,
            "entries_by_pn": {
                "010130.10": [
                    build_cache_entry_from_bundle(
                        _safe_bundle(),
                        source_run_id="phase_a_v2_sanity_20260326T222242Z",
                        bundle_ref="evidence_010130.10.json",
                    )
                ]
            },
        }
        result = select_cached_price_fallback(
            pn="010130.10",
            candidates=[
                {
                    "url": "https://example.com/product/other",
                    "source_tier": "authorized",
                }
            ],
            cache_payload=payload,
            failure_codes=["openai_quota"],
        )
        assert result is None

    def test_select_cached_price_fallback_rejects_policy_mismatch(self):
        payload = {
            "schema_version": PRICE_CACHE_SCHEMA_VERSION,
            "policy_version": "catalog_evidence_policy_v2",
            "entries_by_pn": {
                "010130.10": [
                    build_cache_entry_from_bundle(
                        _safe_bundle(),
                        source_run_id="phase_a_v2_sanity_20260326T222242Z",
                        bundle_ref="evidence_010130.10.json",
                    )
                ]
            },
        }
        result = select_cached_price_fallback(
            pn="010130.10",
            candidates=[
                {
                    "url": "https://example.com/product/01013010",
                    "source_tier": "authorized",
                }
            ],
            cache_payload=payload,
            failure_codes=["openai_quota"],
        )
        assert result is None

    def test_select_cached_price_fallback_requires_transient_failure(self):
        payload = {
            "schema_version": PRICE_CACHE_SCHEMA_VERSION,
            "policy_version": CURRENT_PRICE_POLICY_VERSION,
            "entries_by_pn": {
                "010130.10": [
                    build_cache_entry_from_bundle(
                        _safe_bundle(),
                        source_run_id="phase_a_v2_sanity_20260326T222242Z",
                        bundle_ref="evidence_010130.10.json",
                    )
                ]
            },
        }
        result = select_cached_price_fallback(
            pn="010130.10",
            candidates=[
                {
                    "url": "https://example.com/product/01013010",
                    "source_tier": "authorized",
                }
            ],
            cache_payload=payload,
            failure_codes=["no_price_match"],
        )
        assert result is None
