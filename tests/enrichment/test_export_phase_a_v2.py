"""Tests for additive v2 decision materialization in export bundles."""
import csv
import sys
import os
from pathlib import Path

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from export_pipeline import build_evidence_bundle, write_insales_export


class TestExportBundleV2:

    def test_bundle_contains_policy_decision_v2(self):
        bundle = build_evidence_bundle(
            pn="00020211",
            name="Temperature Sensor",
            brand="Honeywell",
            photo_result={
                "path": "downloads/photos/00020211.jpg",
                "sha1": "abc12345def67890",
                "width": 400,
                "height": 400,
                "size_kb": 42,
                "source": "https://example.com/image",
                "pn_match_location": "jsonld",
                "mpn_confirmed": True,
            },
            vision_verdict={"verdict": "KEEP", "reason": "ok"},
            price_result={
                "price_status": "public_price",
                "source_tier": "authorized",
                "source_url": "https://example.com/price",
                "stock_status": "in_stock",
            },
            datasheet_result={
                "datasheet_status": "found",
                "pdf_exact_pn_confirmed": True,
            },
            run_ts="2026-03-26T00:00:00Z",
        )
        decision = bundle["policy_decision_v2"]
        assert decision["policy_version"] == "catalog_evidence_policy_v1"
        assert decision["family_photo_policy_version"] == "family_photo_policy_v1"
        assert decision["source_matrix_version"] == "source_role_field_matrix_v1"
        assert decision["review_schema_version"] == "review_reason_schema_v1"
        assert "title_status" in decision
        assert "image_status" in decision
        assert "price_status" in decision
        assert "pdf_status" in decision
        assert bundle["field_statuses_v2"]["title_status"] == decision["title_status"]
        assert bundle["review_reasons_v2"] == decision["review_reasons"]
        assert bundle["structured_identity"]["exact_jsonld_pn_match"] is False
        assert bundle["structured_identity"]["exact_structured_pn_match"] is False
        assert bundle["verifier_shadow"]["schema_version"] == "catalog_verifier_shadow_record_v1"
        assert bundle["verifier_shadow"]["decision_merger"]["decision_effect"] == "none"
        assert bundle["price"]["price_observed_at"] == "2026-03-26T00:00:00Z"
        assert bundle["price"]["price_observed_date"] == "2026-03-26"
        assert bundle["price"]["price_date"] == "2026-03-26"
        assert bundle["price"]["price_observation_origin"] == "current_run"
        assert bundle["evidence_paths"]["photo"]["local_artifact_path"] == "downloads/photos/00020211.jpg"
        assert bundle["evidence_paths"]["price"]["observed_page_url"] == "https://example.com/price"
        assert bundle["card_status"] == decision["card_status"]
        assert bundle["review_reasons"] == [
            reason["reason_code"] for reason in decision["review_reasons"]
        ]
        assert bundle["photo"]["photo_status"] == "exact_evidence"
        assert bundle["photo"]["photo_evidence_role"] == "exact"
        assert bundle["photo"]["photo_is_temporary"] is False
        assert bundle["photo"]["replacement_required"] is False

    def test_bundle_materializes_placeholder_photo_contract_and_blocks_auto_publish(self):
        bundle = build_evidence_bundle(
            pn="00020211",
            name="Temperature Sensor",
            brand="Honeywell",
            photo_result={
                "path": "downloads/photos/00020211_placeholder.jpg",
                "sha1": "abc12345def67890",
                "width": 400,
                "height": 400,
                "size_kb": 42,
                "source": "https://example.com/image",
                "photo_status": "placeholder",
                "photo_type": "exact",
            },
            vision_verdict={"verdict": "KEEP", "reason": "usable placeholder"},
            price_result={
                "price_status": "public_price",
                "source_tier": "authorized",
                "source_url": "https://example.com/price",
                "stock_status": "in_stock",
                "offer_unit_basis": "piece",
                "offer_qty": 1,
            },
            datasheet_result={},
            run_ts="2026-03-26T00:00:00Z",
        )
        assert bundle["photo"]["photo_status"] == "placeholder"
        assert bundle["photo"]["photo_evidence_role"] == "merch_only"
        assert bundle["photo"]["photo_is_temporary"] is True
        assert bundle["photo"]["replacement_required"] is True
        assert bundle["card_status"] == "REVIEW_REQUIRED"
        assert bundle["card_status"] == bundle["policy_decision_v2"]["card_status"]
        assert bundle["review_reasons"] == [
            reason["reason_code"] for reason in bundle["policy_decision_v2"]["review_reasons"]
        ]

    def test_bundle_materializes_split_photo_and_price_evidence_paths(self):
        bundle = build_evidence_bundle(
            pn="00020211",
            name="Temperature Sensor",
            brand="Honeywell",
            photo_result={
                "path": "downloads/photos/00020211.jpg",
                "sha1": "abc12345def67890",
                "source": "jsonld:https://example.com/product/00020211",
            },
            vision_verdict={"verdict": "KEEP", "reason": "ok"},
            price_result={
                "price_status": "no_price_found",
                "source_url": "https://example.com/offer/00020211",
                "quote_cta_url": "https://example.com/quote/00020211",
                "price_source_url": "https://example.com/product/00020211",
                "price_source_replacement_url": "https://official.example.com/product/00020211",
                "cache_bundle_ref": "evidence_00020211.json",
                "price_source_surface_preserved_bundle_ref": "evidence_00020211_prior.json",
            },
            datasheet_result={},
            run_ts="2026-03-26T00:00:00Z",
        )
        assert bundle["evidence_paths"]["photo"] == {
            "local_artifact_path": "downloads/photos/00020211.jpg",
            "canonical_filename": "HONEYWELL_00020211_abc12345.jpg",
            "public_url": None,
            "origin_ref": "jsonld:https://example.com/product/00020211",
            "origin_page_url": "https://example.com/product/00020211",
            "origin_kind": "jsonld_page",
        }
        assert bundle["evidence_paths"]["price"] == {
            "observed_page_url": "https://example.com/offer/00020211",
            "quote_cta_url": "https://example.com/quote/00020211",
            "lineage_source_url": "https://example.com/product/00020211",
            "replacement_url": "https://official.example.com/product/00020211",
            "cache_bundle_ref": "evidence_00020211.json",
            "preserved_surface_bundle_ref": "evidence_00020211_prior.json",
        }

    def test_bundle_uses_peha_family_naming_override(self):
        bundle = build_evidence_bundle(
            pn="189791",
            name="D 20.673.244.192",
            brand="PEHA",
            photo_result={},
            vision_verdict={"verdict": "NO_PHOTO", "reason": "missing"},
            price_result={"price_status": "no_price_found"},
            datasheet_result={},
            run_ts="2026-03-31T00:00:00Z",
        )
        assert bundle["assembled_title"] == "Рамка 3-постовая PEHA NOVA, 189791"

    def test_bundle_uses_safe_pdf_identity_expansion(self):
        bundle = build_evidence_bundle(
            pn="00020211",
            name="Temperature Sensor",
            brand="Honeywell",
            photo_result={
                "path": "downloads/photos/00020211.jpg",
                "sha1": "abc12345def67890",
                "width": 400,
                "height": 400,
                "size_kb": 42,
                "source": "https://example.com/image",
            },
            vision_verdict={"verdict": "NO_PHOTO", "reason": "missing"},
            price_result={
                "price_status": "public_price",
                "source_tier": "authorized",
                "source_url": "https://example.com/price",
                "stock_status": "in_stock",
            },
            datasheet_result={
                "datasheet_status": "found",
                "pdf_source_tier": "authorized",
                "pn_confirmed_in_pdf": True,
            },
            run_ts="2026-03-26T00:00:00Z",
        )
        assert bundle["policy_decision_v2"]["identity_level"] == "strong"

    def test_bundle_does_not_use_raw_pdf_fields_as_identity_proof(self):
        bundle = build_evidence_bundle(
            pn="00020211",
            name="Temperature Sensor",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "NO_PHOTO", "reason": "missing"},
            price_result={
                "price_status": "public_price",
                "source_tier": "authorized",
            },
            datasheet_result={
                "datasheet_status": "found",
                "pdf_source_tier": "authorized",
                "pdf_url": "https://example.com/spec.pdf",
                "pdf_text_excerpt": "Part number 00020211",
                "pdf_specs": {"Item Code": "00020211"},
            },
            run_ts="2026-03-26T00:00:00Z",
        )
        assert bundle["policy_decision_v2"]["identity_level"] == "weak"

    def test_bundle_materializes_explicit_structured_identity_flags(self):
        bundle = build_evidence_bundle(
            pn="00020211",
            name="Temperature Sensor",
            brand="Honeywell",
            photo_result={
                "exact_jsonld_pn_match": True,
                "exact_title_pn_match": False,
                "exact_h1_pn_match": False,
                "exact_product_context_pn_match": False,
                "exact_structured_pn_match": True,
                "structured_pn_match_location": "jsonld",
            },
            vision_verdict={"verdict": "KEEP", "reason": "ok"},
            price_result={},
            datasheet_result={},
            run_ts="2026-03-26T00:00:00Z",
        )
        assert bundle["structured_identity"] == {
            "exact_jsonld_pn_match": True,
            "exact_title_pn_match": False,
            "exact_h1_pn_match": False,
            "exact_product_context_pn_match": False,
            "exact_structured_pn_match": True,
            "structured_pn_match_location": "jsonld",
        }
        assert bundle["trace"]["exact_structured_pn_match"] is True
        assert bundle["trace"]["structured_pn_match_location"] == "jsonld"

    def test_bundle_materializes_shadow_verifier_packet_for_routed_case(self):
        bundle = build_evidence_bundle(
            pn="00020211",
            name="Temperature Sensor",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "NO_PHOTO", "reason": "missing"},
            price_result={
                "price_status": "public_price",
                "source_tier": "authorized",
            },
            datasheet_result={},
            run_ts="2026-03-26T00:00:00Z",
        )
        shadow = bundle["verifier_shadow"]
        assert shadow["router"]["should_route"] is True
        assert "IDENTITY_NOT_STRONG" in shadow["router"]["trigger_codes"]
        assert shadow["packet"]["pn_primary"] == "00020211"
        assert shadow["packet"]["policy_versions"]["policy_version"] == "catalog_evidence_policy_v1"

    def test_bundle_downgrades_unknown_tier_public_price(self):
        bundle = build_evidence_bundle(
            pn="1006186",
            name="Earplugs",
            brand="Honeywell",
            photo_result={"exact_structured_pn_match": True, "structured_pn_match_location": "jsonld"},
            vision_verdict={"verdict": "KEEP", "reason": "ok"},
            price_result={
                "price_status": "public_price",
                "source_tier": "unknown",
                "offer_unit_basis": "piece",
                "offer_qty": 1,
            },
            datasheet_result={},
            run_ts="2026-03-26T00:00:00Z",
        )
        assert bundle["price"]["price_status"] == "ambiguous_offer"
        assert bundle["card_status"] == "DRAFT_ONLY"
        assert bundle["card_status"] == bundle["policy_decision_v2"]["card_status"]
        assert "source_tier_not_admissible" in bundle["price"]["public_price_rejection_reasons"]

    def test_bundle_rejects_numeric_keep_without_structured_identity(self):
        bundle = build_evidence_bundle(
            pn="033588.17",
            name="Mount",
            brand="Honeywell",
            photo_result={"pn_match_location": ""},
            vision_verdict={"verdict": "KEEP", "reason": "looks right"},
            price_result={"price_status": "no_price_found"},
            datasheet_result={},
            run_ts="2026-03-26T00:00:00Z",
        )
        assert bundle["photo"]["verdict"] == "REJECT"
        assert bundle["photo"]["numeric_keep_guard_applied"] is True
        assert "missing_exact_structured_context" in bundle["photo"]["numeric_keep_guard_reasons"]

    def test_bundle_routes_clean_weak_identity_case_to_review(self):
        bundle = build_evidence_bundle(
            pn="010130.10",
            name="Module",
            brand="Honeywell",
            photo_result={"numeric_keep_guard_applied": False},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "public_price",
                "source_tier": "authorized",
                "pn_exact_confirmed": True,
                "page_context_clean": True,
                "offer_unit_basis": "piece",
                "offer_qty": 1,
                "category_mismatch": False,
                "brand_mismatch": False,
            },
            datasheet_result={
                "datasheet_status": "no_pn_confirm",
                "pdf_source_tier": "authorized",
            },
            run_ts="2026-03-27T00:00:00Z",
        )
        assert bundle["policy_decision_v2"]["identity_level"] == "weak"
        assert bundle["field_statuses_v2"]["price_status"] == "ACCEPTED"
        assert bundle["policy_decision_v2"]["card_status"] == "REVIEW_REQUIRED"
        assert bundle["policy_decision_v2"]["policy_rule_id"] == "CAP-08W"

    def test_bundle_materializes_cache_fallback_price_lineage(self):
        bundle = build_evidence_bundle(
            pn="010130.10",
            name="Module",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "public_price",
                "source_tier": "authorized",
                "source_url": "https://example.com/product/01013010",
                "pn_exact_confirmed": True,
                "page_context_clean": True,
                "cache_fallback_used": True,
                "cache_fallback_reason": "openai_quota",
                "cache_schema_version": "price_evidence_cache_v1",
                "cache_policy_version": "catalog_evidence_policy_v1",
                "cache_source_run_id": "phase_a_v2_sanity_20260326T222242Z",
                "cache_bundle_ref": "evidence_010130.10.json",
                "transient_failure_detected": True,
                "transient_failure_codes": ["openai_quota"],
            },
            datasheet_result={},
            run_ts="2026-03-27T00:00:00Z",
        )
        assert bundle["price"]["cache_fallback_used"] is True
        assert bundle["price"]["cache_source_run_id"] == "phase_a_v2_sanity_20260326T222242Z"
        assert bundle["price"]["cache_schema_version"] == "price_evidence_cache_v1"
        assert bundle["price"]["transient_failure_codes"] == ["openai_quota"]
        assert bundle["price"]["price_observed_at"] == "2026-03-26T22:22:42Z"
        assert bundle["price"]["price_observed_date"] == "2026-03-26"
        assert bundle["price"]["price_date"] == "2026-03-26"
        assert bundle["price"]["price_observation_origin"] == "cache_fallback"

    def test_bundle_keeps_numeric_guarded_cache_price_case_as_draft(self):
        bundle = build_evidence_bundle(
            pn="1006186",
            name="Earplug",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "KEEP", "reason": "looks right"},
            price_result={
                "price_status": "no_price_found",
                "source_tier": None,
                "source_url": None,
                "pn_exact_confirmed": False,
                "page_context_clean": True,
            },
            datasheet_result={},
            run_ts="2026-03-27T00:00:00Z",
        )
        assert bundle["photo"]["numeric_keep_guard_applied"] is True
        assert bundle["policy_decision_v2"]["card_status"] == "DRAFT_ONLY"
        assert bundle["policy_decision_v2"]["policy_rule_id"] == "CAP-09"

    def test_bundle_routes_numeric_guarded_clean_price_case_to_review(self):
        bundle = build_evidence_bundle(
            pn="1000106",
            name="Earplug",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "KEEP", "reason": "looks right"},
            price_result={
                "price_status": "public_price",
                "source_tier": "industrial",
                "source_url": "https://example.com/product/1000106",
                "pn_exact_confirmed": True,
                "page_context_clean": True,
                "offer_unit_basis": "piece",
                "offer_qty": 1,
                "cache_fallback_used": True,
                "cache_fallback_reason": "openai_quota",
            },
            datasheet_result={},
            run_ts="2026-03-27T00:00:00Z",
        )
        assert bundle["photo"]["numeric_keep_guard_applied"] is True
        assert bundle["field_statuses_v2"]["price_status"] == "ACCEPTED"
        assert bundle["policy_decision_v2"]["card_status"] == "REVIEW_REQUIRED"
        assert bundle["policy_decision_v2"]["policy_rule_id"] == "CAP-08N"

    def test_bundle_materializes_no_price_source_lineage(self):
        bundle = build_evidence_bundle(
            pn="00020211",
            name="Sensor",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "hidden_price",
                "source_tier": "authorized",
                "source_url": "https://example.com/product/00020211",
                "source_type": "authorized_distributor",
                "source_engine": "google_us",
                "pn_exact_confirmed": True,
                "page_context_clean": True,
                "price_source_exact_title_pn_match": True,
                "price_source_exact_h1_pn_match": True,
                "price_source_exact_jsonld_pn_match": False,
                "price_source_exact_product_context_match": False,
                "price_source_clean_product_page": True,
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page",
                "price_lineage_schema_version": "price_lineage_v1",
                "price_source_replacement_candidate_found": True,
                "price_source_replacement_url": "https://official.example/product/00020211",
                "price_source_replacement_tier": "official",
                "price_source_replacement_exact_lineage_confirmed": True,
                "price_source_admissible_replacement_confirmed": True,
                "price_source_terminal_weak_lineage": False,
                "price_source_replacement_reason_code": "admissible_replacement_confirmed",
                "price_source_replacement_schema_version": "price_source_replacement_v1",
                "quote_cta_url": "https://example.com/quote/00020211",
                "stock_status": "rfq",
            },
            datasheet_result={},
            run_ts="2026-03-27T00:00:00Z",
        )
        assert bundle["price"]["price_source_seen"] is True
        assert bundle["price"]["price_source_lineage_confirmed"] is True
        assert bundle["price"]["price_source_exact_title_pn_match"] is True
        assert bundle["price"]["price_source_exact_h1_pn_match"] is True
        assert bundle["price"]["price_source_exact_product_lineage_confirmed"] is True
        assert bundle["price"]["price_source_lineage_reason_code"] == "structured_exact_product_page"
        assert bundle["price"]["price_lineage_schema_version"] == "price_lineage_v1"
        assert bundle["price"]["price_source_admissible_replacement_confirmed"] is True
        assert bundle["price"]["price_source_replacement_reason_code"] == "admissible_replacement_confirmed"
        assert bundle["price"]["price_source_replacement_schema_version"] == "price_source_replacement_v1"
        assert bundle["price"]["price_exact_product_page"] is True
        assert bundle["price"]["price_quote_required"] is True
        assert bundle["price"]["price_no_price_reason_code"] == "quote_required"
        assert bundle["price"]["price_reviewable_no_price_candidate"] is True
        assert bundle["policy_decision_v2"]["card_status"] == "DRAFT_ONLY"

    def test_bundle_observed_only_no_price_surface_stays_non_reviewable(self):
        bundle = build_evidence_bundle(
            pn="1011893-RU",
            name="Harness",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "no_price_found",
                "price_source_seen": True,
                "price_source_url": "https://example.com/listing/1011893-RU",
                "price_source_domain": "example.com",
                "price_source_tier": "unknown",
                "price_source_type": "other",
                "price_source_lineage_confirmed": False,
                "price_exact_product_page": False,
                "price_page_context_clean": True,
                "price_no_price_reason_code": "source_seen_no_exact_page",
                "price_reviewable_no_price_candidate": False,
            },
            datasheet_result={},
            run_ts="2026-03-27T00:00:00Z",
        )
        assert bundle["price"]["price_source_seen"] is True
        assert bundle["price"]["price_source_url"] == "https://example.com/listing/1011893-RU"
        assert bundle["price"]["price_reviewable_no_price_candidate"] is False
        assert bundle["policy_decision_v2"]["card_status"] == "DRAFT_ONLY"

    def test_bundle_routes_terminal_weak_no_price_lineage_to_explicit_draft_rule(self):
        bundle = build_evidence_bundle(
            pn="1006186",
            name="Earplug",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "no_price_found",
                "price_source_seen": True,
                "price_source_url": "https://example.com/product/1006186",
                "price_source_domain": "example.com",
                "price_source_tier": "unknown",
                "price_source_type": "other",
                "price_source_exact_title_pn_match": True,
                "price_source_exact_h1_pn_match": True,
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page_weak_tier",
                "price_source_terminal_weak_lineage": True,
                "price_source_admissible_replacement_confirmed": False,
                "price_source_replacement_reason_code": "weak_exact_lineage_no_admissible_replacement",
                "price_reviewable_no_price_candidate": False,
                "price_exact_product_page": False,
                "page_context_clean": True,
                "pn_exact_confirmed": False,
            },
            datasheet_result={},
            run_ts="2026-03-27T00:00:00Z",
        )
        assert bundle["price"]["price_source_exact_product_lineage_confirmed"] is True
        assert bundle["price"]["price_source_terminal_weak_lineage"] is True
        assert bundle["policy_decision_v2"]["card_status"] == "DRAFT_ONLY"
        assert bundle["policy_decision_v2"]["policy_rule_id"] == "CAP-09T"
        assert any(
            reason["reason_code"] == "TERMINAL_WEAK_NO_PRICE_LINEAGE"
            for reason in bundle["policy_decision_v2"]["review_reasons"]
        )

    def test_bundle_routes_admissible_source_conflict_no_price_to_explicit_draft_rule(self):
        bundle = build_evidence_bundle(
            pn="1006186",
            name="Earplug",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "no_price_found",
                "price_source_seen": True,
                "price_source_url": "https://twen.rs-online.com/web/p/ear-plugs/1040922",
                "price_source_domain": "twen.rs-online.com",
                "price_source_tier": "authorized",
                "price_source_type": "authorized_distributor",
                "price_source_engine": "google_us",
                "price_source_exact_title_pn_match": True,
                "price_source_exact_jsonld_pn_match": True,
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page",
                "price_source_admissible_replacement_confirmed": True,
                "price_source_terminal_weak_lineage": False,
                "price_source_replacement_reason_code": "source_already_admissible",
                "price_source_surface_seen_current_run": True,
                "price_source_surface_stable": False,
                "price_source_surface_preserved_from_prior_run": False,
                "price_source_surface_drop_detected": False,
                "price_source_surface_conflict_detected": True,
                "price_source_surface_preservation_reason_code": "current_surface_conflicts_with_prior",
                "price_source_surface_conflict_reason_code": "current_surface_conflicts_with_prior",
                "price_reviewable_no_price_candidate": False,
                "price_exact_product_page": False,
                "page_context_clean": True,
                "pn_exact_confirmed": False,
                "price_no_price_reason_code": "transient_failure_before_lineage",
            },
            datasheet_result={},
            run_ts="2026-03-31T00:00:00Z",
        )
        assert bundle["price"]["price_source_surface_conflict_detected"] is True
        assert bundle["price"]["price_source_admissible_replacement_confirmed"] is True
        assert bundle["policy_decision_v2"]["card_status"] == "DRAFT_ONLY"
        assert bundle["policy_decision_v2"]["policy_rule_id"] == "CAP-09A"
        assert any(
            reason["reason_code"] == "ADMISSIBLE_SOURCE_NO_PRICE_CONFLICT"
            for reason in bundle["policy_decision_v2"]["review_reasons"]
        )

    def test_bundle_routes_admissible_replacement_confirmed_conflict_to_cap_09a(self):
        bundle = build_evidence_bundle(
            pn="1006186",
            name="Earplug",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "no_price_found",
                "price_source_seen": True,
                "price_source_url": "https://export.rsdelivers.com/product/honeywell-safety/1006186/honeywell-safety-white-yellow-disposable-uncorded/1040922",
                "price_source_domain": "export.rsdelivers.com",
                "price_source_tier": "unknown",
                "price_source_type": "other",
                "price_source_engine": "google_us",
                "price_source_exact_title_pn_match": True,
                "price_source_exact_jsonld_pn_match": True,
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page_weak_tier",
                "price_source_admissible_replacement_confirmed": True,
                "price_source_terminal_weak_lineage": False,
                "price_source_replacement_reason_code": "admissible_replacement_confirmed",
                "price_source_replacement_candidate_found": True,
                "price_source_replacement_url": "https://twen.rs-online.com/web/p/ear-plugs/1040922",
                "price_source_replacement_tier": "authorized",
                "price_source_replacement_exact_lineage_confirmed": True,
                "price_source_surface_seen_current_run": True,
                "price_source_surface_stable": False,
                "price_source_surface_preserved_from_prior_run": False,
                "price_source_surface_drop_detected": False,
                "price_source_surface_conflict_detected": True,
                "price_source_surface_preservation_reason_code": "current_surface_conflicts_with_prior",
                "price_source_surface_conflict_reason_code": "current_surface_conflicts_with_prior",
                "price_reviewable_no_price_candidate": False,
                "price_exact_product_page": False,
                "page_context_clean": True,
                "pn_exact_confirmed": False,
                "price_no_price_reason_code": "source_seen_no_exact_page",
            },
            datasheet_result={},
            run_ts="2026-03-31T00:00:00Z",
        )
        assert bundle["policy_decision_v2"]["card_status"] == "DRAFT_ONLY"
        assert bundle["policy_decision_v2"]["policy_rule_id"] == "CAP-09A"
        assert any(
            reason["reason_code"] == "ADMISSIBLE_SOURCE_NO_PRICE_CONFLICT"
            for reason in bundle["policy_decision_v2"]["review_reasons"]
        )

    def test_bundle_routes_admissible_source_exact_lineage_no_price_to_explicit_draft_rule(self):
        bundle = build_evidence_bundle(
            pn="1011994",
            name="Safety product",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "no_price_found",
                "price_source_seen": True,
                "price_source_url": "https://example-authorized.test/p/1011994",
                "price_source_domain": "example-authorized.test",
                "price_source_tier": "authorized",
                "price_source_type": "authorized_distributor",
                "price_source_engine": "google_us",
                "price_source_exact_title_pn_match": True,
                "price_source_exact_jsonld_pn_match": True,
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page",
                "price_source_admissible_replacement_confirmed": True,
                "price_source_terminal_weak_lineage": False,
                "price_source_replacement_reason_code": "source_already_admissible",
                "price_source_surface_seen_current_run": False,
                "price_source_surface_stable": False,
                "price_source_surface_preserved_from_prior_run": False,
                "price_source_surface_drop_detected": False,
                "price_source_surface_conflict_detected": False,
                "price_source_surface_preservation_reason_code": "no_prior_surface_available",
                "price_source_surface_conflict_reason_code": "",
                "price_reviewable_no_price_candidate": False,
                "price_exact_product_page": False,
                "page_context_clean": True,
                "pn_exact_confirmed": False,
                "price_no_price_reason_code": "transient_failure_before_lineage",
            },
            datasheet_result={},
            run_ts="2026-03-31T00:00:00Z",
        )
        assert bundle["price"]["price_source_surface_conflict_detected"] is False
        assert bundle["price"]["price_source_admissible_replacement_confirmed"] is True
        assert bundle["policy_decision_v2"]["card_status"] == "DRAFT_ONLY"
        assert bundle["policy_decision_v2"]["policy_rule_id"] == "CAP-09B"
        assert any(
            reason["reason_code"] == "ADMISSIBLE_SOURCE_NO_PRICE_EXACT_LINEAGE"
            for reason in bundle["policy_decision_v2"]["review_reasons"]
        )

    def test_bundle_routes_prior_admissible_replacement_confirmed_no_price_to_cap_09b(self):
        bundle = build_evidence_bundle(
            pn="1006186",
            name="Earplug",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "no_price_found",
                "price_source_seen": True,
                "price_source_url": "https://www.alive-sr.com/products/honeywell-howard-leight-1006186-bilsom-303l-earplugs-refill-bag-200-pairs",
                "price_source_domain": "alive-sr.com",
                "price_source_tier": "unknown",
                "price_source_type": "other",
                "price_source_engine": "google_us",
                "price_source_exact_title_pn_match": True,
                "price_source_exact_h1_pn_match": True,
                "price_source_exact_product_context_match": True,
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page_weak_tier",
                "price_source_admissible_replacement_confirmed": True,
                "price_source_terminal_weak_lineage": False,
                "price_source_replacement_reason_code": "admissible_replacement_confirmed",
                "price_source_replacement_candidate_found": True,
                "price_source_replacement_url": "https://twen.rs-online.com/web/p/ear-plugs/1040922",
                "price_source_replacement_tier": "authorized",
                "price_source_replacement_exact_lineage_confirmed": True,
                "price_source_surface_stable": True,
                "price_source_surface_seen_current_run": True,
                "price_source_surface_preserved_from_prior_run": False,
                "price_source_surface_drop_detected": False,
                "price_source_surface_conflict_detected": False,
                "price_source_surface_preservation_reason_code": "current_surface_matches_prior",
                "price_reviewable_no_price_candidate": False,
                "price_exact_product_page": False,
                "page_context_clean": True,
                "pn_exact_confirmed": False,
                "price_no_price_reason_code": "transient_failure_before_lineage",
                "transient_failure_detected": True,
                "transient_failure_codes": ["openai_quota"],
            },
            datasheet_result={},
            run_ts="2026-03-31T00:00:00Z",
        )
        assert bundle["policy_decision_v2"]["card_status"] == "DRAFT_ONLY"
        assert bundle["policy_decision_v2"]["policy_rule_id"] == "CAP-09B"
        assert bundle["price"]["price_source_replacement_reason_code"] == "admissible_replacement_confirmed"
        assert any(
            reason["reason_code"] == "ADMISSIBLE_SOURCE_NO_PRICE_EXACT_LINEAGE"
            for reason in bundle["policy_decision_v2"]["review_reasons"]
        )

    def test_bundle_routes_stable_weak_surface_with_prior_admissible_replacement_to_cap_09b(self):
        bundle = build_evidence_bundle(
            pn="1006186",
            name="Earplug",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "no_price_found",
                "price_source_seen": True,
                "price_source_url": "https://export.rsdelivers.com/product/honeywell-safety/1006186/honeywell-safety-white-yellow-disposable-uncorded/1040922",
                "price_source_domain": "export.rsdelivers.com",
                "price_source_tier": "unknown",
                "price_source_type": "other",
                "price_source_engine": "google_us",
                "price_source_exact_title_pn_match": True,
                "price_source_exact_jsonld_pn_match": True,
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page_weak_tier",
                "price_source_admissible_replacement_confirmed": True,
                "price_source_terminal_weak_lineage": False,
                "price_source_replacement_reason_code": "admissible_replacement_confirmed",
                "price_source_replacement_candidate_found": True,
                "price_source_replacement_url": "https://twen.rs-online.com/web/p/ear-plugs/1040922",
                "price_source_replacement_tier": "authorized",
                "price_source_replacement_exact_lineage_confirmed": True,
                "price_source_surface_stable": True,
                "price_source_surface_seen_current_run": True,
                "price_source_surface_preserved_from_prior_run": False,
                "price_source_surface_drop_detected": False,
                "price_source_surface_conflict_detected": False,
                "price_source_surface_preservation_reason_code": "current_surface_matches_prior",
                "price_reviewable_no_price_candidate": False,
                "price_exact_product_page": False,
                "page_context_clean": True,
                "pn_exact_confirmed": False,
                "price_no_price_reason_code": "source_seen_no_exact_page",
                "transient_failure_detected": False,
                "transient_failure_codes": [],
            },
            datasheet_result={},
            run_ts="2026-03-31T00:00:00Z",
        )
        assert bundle["policy_decision_v2"]["card_status"] == "DRAFT_ONLY"
        assert bundle["policy_decision_v2"]["policy_rule_id"] == "CAP-09B"
        assert bundle["price"]["price_source_surface_stable"] is True
        assert bundle["price"]["price_source_replacement_reason_code"] == "admissible_replacement_confirmed"
        assert any(
            reason["reason_code"] == "ADMISSIBLE_SOURCE_NO_PRICE_EXACT_LINEAGE"
            for reason in bundle["policy_decision_v2"]["review_reasons"]
        )

    def test_bundle_routes_current_admissible_official_article_no_price_to_cap_09b(self):
        bundle = build_evidence_bundle(
            pn="1012541",
            name="Earmuff",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "no_price_found",
                "price_source_seen": True,
                "price_source_url": "https://sps-support.honeywell.com/s/article/1012541-Leightning-L3Hs-Helmet-Earmuff-3711-3712-3721-Adapter-Data-Sheet-Spanish",
                "price_source_domain": "sps-support.honeywell.com",
                "price_source_tier": "official",
                "price_source_type": "other",
                "price_source_engine": "google_us",
                "price_source_exact_title_pn_match": False,
                "price_source_exact_h1_pn_match": False,
                "price_source_exact_jsonld_pn_match": False,
                "price_source_exact_product_context_match": False,
                "price_source_structured_match_location": "official_article_url",
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "official_article_url_exact_match",
                "price_source_clean_product_page": False,
                "price_source_admissible_replacement_confirmed": True,
                "price_source_terminal_weak_lineage": False,
                "price_source_replacement_reason_code": "source_already_admissible",
                "price_source_surface_conflict_detected": False,
                "price_source_surface_preservation_reason_code": "no_prior_surface_available",
                "price_reviewable_no_price_candidate": False,
                "price_exact_product_page": False,
                "page_context_clean": False,
                "pn_exact_confirmed": False,
                "price_no_price_reason_code": "exact_page_context_not_clean",
            },
            datasheet_result={},
            run_ts="2026-03-31T00:00:00Z",
        )
        assert bundle["price"]["price_source_structured_match_location"] == "official_article_url"
        assert bundle["price"]["price_source_lineage_confirmed"] is True
        assert bundle["price"]["price_source_admissible_replacement_confirmed"] is True
        assert bundle["price"]["price_no_price_reason_code"] == "exact_page_context_not_clean"
        assert bundle["price"]["price_source_observed_only"] is False
        assert bundle["policy_decision_v2"]["card_status"] == "DRAFT_ONLY"
        assert bundle["policy_decision_v2"]["policy_rule_id"] == "CAP-09B"
        assert any(
            reason["reason_code"] == "ADMISSIBLE_SOURCE_NO_PRICE_EXACT_LINEAGE"
            for reason in bundle["policy_decision_v2"]["review_reasons"]
        )

    def test_bundle_persists_preserved_source_surface_fields(self):
        bundle = build_evidence_bundle(
            pn="1011894-RU",
            name="Safety product",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "no_price_found",
                "price_source_seen": True,
                "price_source_url": "https://www.etm.ru/cat/nn/1840352",
                "price_source_domain": "etm.ru",
                "price_source_tier": "ru_b2b",
                "price_source_type": "other",
                "price_source_engine": "serpapi",
                "price_source_exact_title_pn_match": True,
                "price_source_exact_h1_pn_match": True,
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_lineage_reason_code": "structured_exact_product_page_weak_tier",
                "price_source_surface_stable": True,
                "price_source_surface_preserved_from_prior_run": True,
                "price_source_surface_drop_detected": True,
                "price_source_surface_conflict_detected": False,
                "price_source_surface_preservation_reason_code": "preserved_compatible_prior_surface",
                "price_source_surface_drop_reason_code": "current_run_surface_missing_prior_surface_preserved",
                "price_source_surface_preserved_source_run_id": "phase_a_v2_sanity_20260327T083642Z",
                "price_source_surface_preserved_bundle_ref": "evidence_1011894-RU.json",
                "price_source_terminal_weak_lineage": True,
                "price_source_replacement_reason_code": "weak_exact_lineage_no_admissible_replacement",
                "price_reviewable_no_price_candidate": False,
                "page_context_clean": True,
                "pn_exact_confirmed": False,
            },
            datasheet_result={},
            run_ts="2026-03-31T00:00:00Z",
        )
        assert bundle["price"]["price_source_surface_preserved_from_prior_run"] is True
        assert bundle["price"]["price_source_surface_drop_detected"] is True
        assert bundle["price"]["price_source_surface_preserved_source_run_id"] == "phase_a_v2_sanity_20260327T083642Z"
        assert bundle["price"]["price_observed_at"] == "2026-03-27T08:36:42Z"
        assert bundle["price"]["price_observed_date"] == "2026-03-27"
        assert bundle["price"]["price_date"] == "2026-03-27"
        assert bundle["price"]["price_observation_origin"] == "preserved_surface"
        assert bundle["trace"]["price_source_surface_preserved_from_prior_run"] is True
        assert bundle["trace"]["price_source_surface_preservation_reason_code"] == "preserved_compatible_prior_surface"

    def test_bundle_materializes_photo_negative_evidence(self):
        bundle = build_evidence_bundle(
            pn="033588.17",
            name="Mount",
            brand="Honeywell",
            photo_result={"stock_photo_flag": True},
            vision_verdict={"verdict": "KEEP", "reason": "looks right"},
            price_result={"price_status": "no_price_found"},
            datasheet_result={},
            run_ts="2026-03-31T00:00:00Z",
        )
        assert {"class": "stock_photo", "code": "stock_photo_flag", "source_field": "photo.stock_photo_flag"} in bundle["negative_evidence"]["photo"]
        assert {
            "class": "numeric_keep_guard",
            "code": "missing_exact_structured_context",
            "source_field": "photo.numeric_keep_guard_reasons",
        } in bundle["negative_evidence"]["photo"]

    def test_bundle_materializes_price_and_identity_negative_evidence(self):
        bundle = build_evidence_bundle(
            pn="1006186",
            name="Earplug",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "no_price_found",
                "category_mismatch": True,
                "brand_mismatch": True,
                "suffix_conflict": True,
                "public_price_rejection_reasons": ["source_tier_not_admissible"],
                "price_no_price_reason_code": "source_seen_no_exact_page",
                "price_source_surface_conflict_detected": True,
                "price_source_surface_conflict_reason_code": "prior_surface_mismatch",
                "price_source_terminal_weak_lineage": True,
                "price_source_replacement_reason_code": "weak_exact_lineage_no_admissible_replacement",
            },
            datasheet_result={},
            run_ts="2026-03-31T00:00:00Z",
        )
        assert {
            "class": "public_price_rejection",
            "code": "source_tier_not_admissible",
            "source_field": "price.public_price_rejection_reasons",
        } in bundle["negative_evidence"]["price"]
        assert {
            "class": "no_price_reason",
            "code": "no_source_candidates",
            "source_field": "price.price_no_price_reason_code",
        } in bundle["negative_evidence"]["price"]
        assert {
            "class": "source_surface_conflict",
            "code": "prior_surface_mismatch",
            "source_field": "price.price_source_surface_conflict_reason_code",
        } in bundle["negative_evidence"]["price"]
        assert {
            "class": "terminal_weak_lineage",
            "code": "weak_exact_lineage_no_admissible_replacement",
            "source_field": "price.price_source_replacement_reason_code",
        } in bundle["negative_evidence"]["price"]
        assert {
            "class": "identity_mismatch",
            "code": "category_mismatch",
            "source_field": "price.category_mismatch",
        } in bundle["negative_evidence"]["identity"]
        assert {
            "class": "identity_mismatch",
            "code": "brand_mismatch",
            "source_field": "price.brand_mismatch",
        } in bundle["negative_evidence"]["identity"]
        assert {
            "class": "suffix_conflict",
            "code": "suffix_conflict",
            "source_field": "price.suffix_conflict",
        } in bundle["negative_evidence"]["identity"]

    def test_bundle_materializes_source_seen_no_exact_page_negative_evidence(self):
        bundle = build_evidence_bundle(
            pn="1012541",
            name="Earmuff",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "no_price_found",
                "price_source_seen": True,
                "price_source_url": "https://example.com/1012541",
                "price_source_domain": "example.com",
                "price_source_tier": "official",
                "price_source_type": "other",
                "price_source_engine": "google_us",
                "price_source_exact_product_lineage_confirmed": False,
                "price_source_lineage_reason_code": "structured_exact_match_missing",
                "price_no_price_reason_code": "source_seen_no_exact_page",
            },
            datasheet_result={},
            run_ts="2026-03-31T00:00:00Z",
        )
        assert {
            "class": "no_price_reason",
            "code": "source_seen_no_exact_page",
            "source_field": "price.price_no_price_reason_code",
        } in bundle["negative_evidence"]["price"]

    def test_bundle_leaves_price_observation_blank_without_price_surface(self):
        bundle = build_evidence_bundle(
            pn="00020211",
            name="Sensor",
            brand="Honeywell",
            photo_result={},
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={"price_status": "no_price_found"},
            datasheet_result={},
            run_ts="2026-03-31T00:00:00Z",
        )
        assert bundle["price"]["price_observed_at"] == ""
        assert bundle["price"]["price_observed_date"] == ""
        assert bundle["price"]["price_date"] == ""
        assert bundle["price"]["price_observation_origin"] == ""
        assert bundle["evidence_paths"]["photo"] == {
            "local_artifact_path": "",
            "canonical_filename": "",
            "public_url": None,
            "origin_ref": "",
            "origin_page_url": "",
            "origin_kind": "",
        }
        assert bundle["evidence_paths"]["price"] == {
            "observed_page_url": "",
            "quote_cta_url": "",
            "lineage_source_url": "",
            "replacement_url": "",
            "cache_bundle_ref": "",
            "preserved_surface_bundle_ref": "",
        }

    def test_export_does_not_fallback_to_raw_rejected_photo(self, tmp_path: Path):
        bundle = build_evidence_bundle(
            pn="010130.10",
            name="Module",
            brand="Honeywell",
            photo_result={
                "path": r"D:\BIRETOS\projects\biretos-automation\downloads\photos\010130.10.jpg",
                "photo_status": "rejected",
            },
            vision_verdict={"verdict": "REJECT", "reason": "wrong image"},
            price_result={"price_status": "public_price", "price_usd": 225.0, "currency": "EUR"},
            datasheet_result={},
            run_ts="2026-03-31T00:00:00Z",
        )
        bundle["card_status"] = "REVIEW_REQUIRED"
        out_path = tmp_path / "insales_export.csv"

        exported = write_insales_export([bundle], out_path)

        assert exported == 1
        rows = list(csv.DictReader(out_path.open(encoding="utf-8-sig")))
        assert rows[0]["Изображение"] == ""

