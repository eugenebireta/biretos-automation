from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from price_source_surface_stability import (  # noqa: E402
    PRICE_SOURCE_SURFACE_STABILITY_SCHEMA_VERSION,
    build_source_surface_cache_payload_from_run_dirs,
    materialize_source_surface_stability,
    select_prior_admissible_surface_candidate,
    should_reuse_prior_admissible_surface,
)


class TestPriceSourceSurfaceStability:
    def _payload(self, entry: dict) -> dict:
        return {
            "schema_version": PRICE_SOURCE_SURFACE_STABILITY_SCHEMA_VERSION,
            "generated_at": "2026-03-31T00:00:00Z",
            "policy_version": "catalog_evidence_policy_v1",
            "runs_indexed": ["phase_a_v2_sanity_older"],
            "entry_count": 1,
            "entries_by_pn": {
                entry["pn_primary"]: [entry],
            },
        }

    def test_preserves_compatible_prior_surface_when_current_run_drops_it(self):
        entry = {
            "pn_primary": "1011894-RU",
            "policy_version": "catalog_evidence_policy_v1",
            "source_url": "https://www.etm.ru/cat/nn/1840352",
            "source_domain": "etm.ru",
            "source_type": "other",
            "source_tier": "ru_b2b",
            "source_engine": "serpapi",
            "price_source_exact_title_pn_match": True,
            "price_source_exact_h1_pn_match": True,
            "price_source_exact_jsonld_pn_match": False,
            "price_source_exact_product_context_match": True,
            "price_source_structured_match_location": "title+h1",
            "price_source_clean_product_page": True,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_lineage_reason_code": "structured_exact_product_page_weak_tier",
            "price_lineage_schema_version": "price_lineage_v1",
            "price_no_price_reason_code": "quote_required",
            "no_price_coverage_schema_version": "no_price_coverage_v1",
            "source_run_id": "phase_a_v2_sanity_20260327T083642Z",
            "bundle_ref": "evidence_1011894-RU.json",
        }
        result = materialize_source_surface_stability(
            {
                "price_status": "no_price_found",
                "price_no_price_reason_code": "no_source_candidates",
            },
            pn="1011894-RU",
            surface_cache_payload=self._payload(entry),
        )
        assert result["price_source_surface_stable"] is True
        assert result["price_source_surface_preserved_from_prior_run"] is True
        assert result["price_source_surface_drop_detected"] is True
        assert result["price_source_surface_preservation_reason_code"] == "preserved_compatible_prior_surface"
        assert result["price_source_surface_drop_reason_code"] == "current_run_surface_missing_prior_surface_preserved"
        assert result["price_source_url"] == "https://www.etm.ru/cat/nn/1840352"
        assert result["price_source_exact_product_lineage_confirmed"] is True
        assert result["price_source_lineage_reason_code"] == "structured_exact_product_page_weak_tier"
        assert result["price_source_surface_preserved_source_run_id"] == "phase_a_v2_sanity_20260327T083642Z"

    def test_marks_conflict_when_current_observed_surface_is_incompatible(self):
        entry = {
            "pn_primary": "1011894-RU",
            "policy_version": "catalog_evidence_policy_v1",
            "source_url": "https://www.etm.ru/cat/nn/1840352",
            "source_domain": "etm.ru",
            "source_type": "other",
            "source_tier": "ru_b2b",
            "source_engine": "serpapi",
            "price_source_exact_product_lineage_confirmed": True,
        }
        result = materialize_source_surface_stability(
            {
                "price_status": "no_price_found",
                "price_no_price_reason_code": "source_seen_no_exact_page",
            },
            pn="1011894-RU",
            surface_cache_payload=self._payload(entry),
            observed_candidate={
                "url": "https://example.com/listing/1011894-RU",
                "source_type": "other",
                "engine": "serpapi",
            },
        )
        assert result["price_source_surface_preserved_from_prior_run"] is False
        assert result["price_source_surface_conflict_detected"] is True
        assert result["price_source_surface_drop_detected"] is True
        assert result["price_source_surface_conflict_reason_code"] == "current_observed_surface_incompatible_with_prior"

    def test_current_surface_matching_prior_is_stable_without_preservation(self):
        entry = {
            "pn_primary": "00020211",
            "policy_version": "catalog_evidence_policy_v1",
            "source_url": "https://tameson.com/products/00020211",
            "source_domain": "tameson.com",
            "source_type": "other",
            "source_tier": "weak",
            "source_engine": "serpapi",
            "price_source_exact_product_lineage_confirmed": True,
        }
        result = materialize_source_surface_stability(
            {
                "price_status": "no_price_found",
                "price_source_seen": True,
                "price_source_url": "https://tameson.com/products/00020211",
                "price_source_type": "other",
                "price_source_tier": "weak",
                "price_source_engine": "serpapi",
            },
            pn="00020211",
            surface_cache_payload=self._payload(entry),
        )
        assert result["price_source_surface_seen_current_run"] is True
        assert result["price_source_surface_stable"] is True
        assert result["price_source_surface_preserved_from_prior_run"] is False
        assert result["price_source_surface_preservation_reason_code"] == "current_surface_matches_prior"

    def test_selects_stronger_prior_admissible_surface_candidate(self):
        weak_entry = {
            "pn_primary": "1006186",
            "policy_version": "catalog_evidence_policy_v1",
            "source_url": "https://www.alive-sr.com/products/honeywell-howard-leight-1006186-bilsom-303l-earplugs-refill-bag-200-pairs",
            "source_domain": "alive-sr.com",
            "source_type": "other",
            "source_tier": "unknown",
            "source_engine": "google_us",
            "price_source_exact_title_pn_match": True,
            "price_source_exact_h1_pn_match": True,
            "price_source_exact_jsonld_pn_match": False,
            "price_source_exact_product_context_match": True,
            "price_source_structured_match_location": "title+h1",
            "price_source_clean_product_page": True,
            "price_source_exact_product_lineage_confirmed": True,
            "source_run_id": "older_weak",
            "bundle_ref": "evidence_weak.json",
            "bundle_generated_at": "2026-03-27T12:10:12Z",
        }
        strong_entry = {
            "pn_primary": "1006186",
            "policy_version": "catalog_evidence_policy_v1",
            "source_url": "https://twen.rs-online.com/web/p/ear-plugs/1040922",
            "source_domain": "twen.rs-online.com",
            "source_type": "authorized_distributor",
            "source_tier": "authorized",
            "source_engine": "google_us",
            "price_source_exact_title_pn_match": True,
            "price_source_exact_h1_pn_match": False,
            "price_source_exact_jsonld_pn_match": True,
            "price_source_exact_product_context_match": False,
            "price_source_structured_match_location": "jsonld",
            "price_source_clean_product_page": True,
            "price_source_exact_product_lineage_confirmed": True,
            "source_run_id": "newer_strong",
            "bundle_ref": "evidence_strong.json",
            "bundle_generated_at": "2026-03-30T21:56:11Z",
        }
        payload = {
            "schema_version": PRICE_SOURCE_SURFACE_STABILITY_SCHEMA_VERSION,
            "generated_at": "2026-03-31T00:00:00Z",
            "policy_version": "catalog_evidence_policy_v1",
            "runs_indexed": ["older_weak", "newer_strong"],
            "entry_count": 2,
            "entries_by_pn": {
                "1006186": [weak_entry, strong_entry],
            },
        }
        candidate = select_prior_admissible_surface_candidate(
            pn="1006186",
            current_price_result={
                "price_status": "no_price_found",
                "price_source_url": weak_entry["source_url"],
                "price_source_tier": "unknown",
                "price_source_exact_product_lineage_confirmed": True,
            },
            surface_cache_payload=payload,
        )
        assert candidate is not None
        assert candidate["price_source_url"] == strong_entry["source_url"]
        assert candidate["price_source_tier"] == "authorized"
        assert candidate["price_source_replacement_from_prior_surface_cache"] is True

    def test_reuses_prior_admissible_surface_for_stable_weak_exact_no_price(self):
        assert should_reuse_prior_admissible_surface(
            {
                "price_status": "no_price_found",
                "price_source_tier": "unknown",
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page_weak_tier",
                "price_source_surface_stable": True,
                "price_source_surface_conflict_detected": False,
                "price_reviewable_no_price_candidate": False,
            },
            transient_failure_detected=False,
        ) is True

    def test_prior_admissible_surface_reuse_requires_explicit_safe_conditions(self):
        assert should_reuse_prior_admissible_surface(
            {
                "price_status": "no_price_found",
                "price_source_tier": "unknown",
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page_weak_tier",
                "price_source_surface_stable": False,
                "price_source_surface_conflict_detected": False,
                "price_reviewable_no_price_candidate": False,
            },
            transient_failure_detected=False,
        ) is False
        assert should_reuse_prior_admissible_surface(
            {
                "price_status": "no_price_found",
                "price_source_tier": "authorized",
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page",
                "price_source_surface_stable": True,
                "price_source_surface_conflict_detected": False,
                "price_reviewable_no_price_candidate": False,
            },
            transient_failure_detected=False,
        ) is False

    def test_build_surface_cache_payload_indexes_lineage_bundles(self, tmp_path: Path):
        run_dir = tmp_path / "phase_a_v2_sanity_older"
        evidence_dir = run_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        bundle = {
            "pn": "1011894-RU",
            "generated_at": "2026-03-27T08:36:42Z",
            "policy_decision_v2": {"policy_version": "catalog_evidence_policy_v1"},
            "price": {
                "price_status": "no_price_found",
                "price_source_seen": True,
                "price_source_url": "https://www.etm.ru/cat/nn/1840352",
                "price_source_tier": "ru_b2b",
                "price_source_type": "other",
                "price_source_engine": "serpapi",
                "price_source_exact_title_pn_match": True,
                "price_source_exact_h1_pn_match": True,
                "price_source_exact_product_context_match": True,
                "price_source_structured_match_location": "title+h1",
                "price_source_clean_product_page": True,
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page_weak_tier",
                "price_lineage_schema_version": "price_lineage_v1",
                "price_no_price_reason_code": "quote_required",
                "no_price_coverage_schema_version": "no_price_coverage_v1",
            },
        }
        (evidence_dir / "evidence_1011894-RU.json").write_text(json.dumps(bundle), encoding="utf-8")
        payload = build_source_surface_cache_payload_from_run_dirs([run_dir])
        assert payload["entry_count"] == 1
        entry = payload["entries_by_pn"]["1011894-RU"][0]
        assert entry["source_domain"] == "etm.ru"
        assert entry["price_source_exact_product_lineage_confirmed"] is True
