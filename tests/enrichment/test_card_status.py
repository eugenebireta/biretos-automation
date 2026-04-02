"""Deterministic tests for the Phase A v2 card status policy layer."""
import sys
import os

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

import pytest

from card_status import (
    _infer_identity_level,
    _normalize_price_status,
    calculate_card_status,
    card_status_calculator,
    build_decision_record_v2_from_legacy_inputs,
    load_catalog_evidence_policy,
    load_decision_table,
    load_enum_contract,
)


class TestArtifacts:

    def test_enum_contract_has_fixed_sets(self):
        enums = load_enum_contract()
        assert enums["field_status"] == [
            "ACCEPTED",
            "REVIEW_REQUIRED",
            "INSUFFICIENT",
            "REJECTED",
        ]
        assert enums["card_status"] == [
            "AUTO_PUBLISH",
            "REVIEW_REQUIRED",
            "DRAFT_ONLY",
        ]
        assert "ADMISSIBLE_SOURCE_NO_PRICE_CONFLICT" in enums["reason_code"]
        assert "ADMISSIBLE_SOURCE_NO_PRICE_EXACT_LINEAGE" in enums["reason_code"]
        assert "TERMINAL_WEAK_NO_PRICE_LINEAGE" in enums["reason_code"]

    def test_catalog_policy_has_versions(self):
        policy = load_catalog_evidence_policy()
        assert policy["policy_version"] == "catalog_evidence_policy_v1"
        assert policy["family_photo_policy_version"] == "family_photo_policy_v1"
        assert policy["source_matrix_version"] == "source_role_field_matrix_v1"
        assert policy["review_schema_version"] == "review_reason_schema_v1"
        assert policy["ambiguity_rules"]["weak_identity_clean_review_route_enabled"] is True
        assert policy["weak_identity_review_route"]["policy_rule_id"] == "CAP-08W"
        assert policy["ambiguity_rules"]["numeric_guarded_review_route_enabled"] is True
        assert policy["numeric_guard_review_route"]["policy_rule_id"] == "CAP-08N"
        assert policy["ambiguity_rules"]["admissible_source_conflict_no_price_disposition_enabled"] is True
        assert policy["admissible_source_conflict_no_price_route"]["policy_rule_id"] == "CAP-09A"
        assert policy["ambiguity_rules"]["admissible_source_exact_lineage_no_price_disposition_enabled"] is True
        assert policy["admissible_source_exact_lineage_no_price_route"]["policy_rule_id"] == "CAP-09B"
        assert policy["ambiguity_rules"]["terminal_weak_no_price_disposition_enabled"] is True
        assert policy["terminal_weak_no_price_route"]["policy_rule_id"] == "CAP-09T"

    def test_load_decision_table_has_rows(self):
        rows = load_decision_table()
        assert rows
        assert rows[0]["id"].startswith("CAP-")


class TestCalculateCardStatusCompatibility:

    def test_strong_exact_public_auto_publish(self):
        decision = calculate_card_status("strong", "exact", "public_price")
        assert decision.result == "AUTO_PUBLISH"
        assert decision.rule_id == "CAP-01"

    def test_medium_any_review(self):
        decision = calculate_card_status("medium", "unknown", "no_price")
        assert decision.result == "REVIEW_REQUIRED"
        assert decision.rule_id == "CAP-08"

    def test_critical_mismatch_overrides(self):
        decision = calculate_card_status(
            "strong", "exact", "public_price", mismatch="any_critical"
        )
        assert decision.result == "DRAFT_ONLY"
        assert decision.rule_id == "CAP-10"

    def test_legacy_mismatch_price_aliases_normalize_to_no_price(self):
        assert _normalize_price_status("category_mismatch_only") == "no_price"
        assert _normalize_price_status("brand_mismatch_only") == "no_price"


class TestCardStatusCalculator:

    def test_field_level_statuses_and_versions_present(self):
        decision = card_status_calculator(
            identity_level="strong",
            title_signal={
                "derived_title": "Honeywell 00020211 Temperature Sensor",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "exact",
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "public_price",
                "source_role": "authorized_distributor",
                "exact_pn_confirmed": True,
                "exact_product_page": True,
                "page_context_clean": True,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
            pdf_signal={
                "datasheet_status": "found",
                "source_role": "official_pdf_proof",
                "exact_pn_confirmed": True,
                "candidate_ids": ["cand_pdf_1"],
                "evidence_ids": ["ev_pdf_1"],
            },
        )
        assert decision.title_status == "ACCEPTED"
        assert decision.image_status == "ACCEPTED"
        assert decision.price_status == "ACCEPTED"
        assert decision.pdf_status == "ACCEPTED"
        assert decision.card_status == "AUTO_PUBLISH"
        assert decision.policy_version == "catalog_evidence_policy_v1"
        assert decision.family_photo_policy_version == "family_photo_policy_v1"
        assert decision.source_matrix_version == "source_role_field_matrix_v1"
        assert decision.review_schema_version == "review_reason_schema_v1"

    def test_family_photo_review_reason_is_replayable(self):
        decision = card_status_calculator(
            identity_level="strong",
            title_signal={
                "derived_title": "Esser IQ8 detector",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "family_photo",
                "family_photo_allowed": True,
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "rfq_only",
                "source_role": "authorized_distributor",
                "exact_pn_confirmed": True,
                "exact_product_page": True,
                "page_context_clean": True,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
            pdf_signal={
                "datasheet_status": "missing",
                "candidate_ids": ["cand_pdf_1"],
                "evidence_ids": ["ev_pdf_1"],
            },
        )
        assert decision.image_status == "REVIEW_REQUIRED"
        assert decision.card_status == "REVIEW_REQUIRED"
        family_reason = next(
            r for r in decision.review_reasons
            if r.reason_code == "FAMILY_PHOTO_POLICY_REVIEW"
        )
        assert family_reason.field == "image"
        assert family_reason.candidate_ids == ["cand_image_1"]
        assert family_reason.evidence_ids == ["ev_image_1"]
        assert family_reason.bucket == "FAMILY_PHOTO_REVIEW"

    def test_photo_status_is_canonical_over_legacy_photo_type(self):
        decision = card_status_calculator(
            identity_level="strong",
            title_signal={
                "derived_title": "Honeywell placeholder image case",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_status": "placeholder",
                "photo_type": "exact",
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "public_price",
                "source_role": "authorized_distributor",
                "exact_pn_confirmed": True,
                "exact_product_page": True,
                "page_context_clean": True,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
            pdf_signal={
                "datasheet_status": "missing",
                "candidate_ids": ["cand_pdf_1"],
                "evidence_ids": ["ev_pdf_1"],
            },
        )
        assert decision.image_status == "INSUFFICIENT"
        assert decision.card_status == "REVIEW_REQUIRED"

    def test_weak_identity_forces_draft(self):
        decision = card_status_calculator(
            identity_level="weak",
            title_signal={
                "derived_title": "Honeywell 00020211",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "exact",
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "public_price",
                "source_role": "authorized_distributor",
                "exact_pn_confirmed": True,
                "exact_product_page": True,
                "page_context_clean": True,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
        )
        assert decision.card_status == "DRAFT_ONLY"
        reason_codes = {r.reason_code for r in decision.review_reasons}
        assert "IDENTITY_WEAK" in reason_codes

    def test_weak_identity_clean_price_case_routes_to_review(self):
        decision = card_status_calculator(
            identity_level="weak",
            title_signal={
                "derived_title": "Honeywell 010130.10 Module",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "none",
                "numeric_keep_guard_applied": False,
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "public_price",
                "source_role": "authorized_distributor",
                "exact_pn_confirmed": True,
                "exact_product_page": True,
                "page_context_clean": True,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
            pdf_signal={
                "datasheet_status": "missing",
                "candidate_ids": ["cand_pdf_1"],
                "evidence_ids": ["ev_pdf_1"],
            },
        )
        assert decision.card_status == "REVIEW_REQUIRED"
        assert decision.policy_rule_id == "CAP-08W"

    def test_weak_identity_numeric_keep_guard_case_routes_to_review_when_price_is_clean(self):
        decision = card_status_calculator(
            identity_level="weak",
            title_signal={
                "derived_title": "Honeywell 1000106 Earplug",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "none",
                "numeric_keep_guard_applied": True,
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "public_price",
                "source_role": "industrial_distributor",
                "exact_pn_confirmed": True,
                "exact_product_page": True,
                "page_context_clean": True,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
            pdf_signal={
                "datasheet_status": "found",
                "source_role": "official_pdf_proof",
                "exact_pn_confirmed": False,
                "candidate_ids": ["cand_pdf_1"],
                "evidence_ids": ["ev_pdf_1"],
            },
        )
        assert decision.card_status == "REVIEW_REQUIRED"
        assert decision.policy_rule_id == "CAP-08N"

    def test_numeric_guard_without_accepted_price_stays_draft(self):
        decision = card_status_calculator(
            identity_level="weak",
            title_signal={
                "derived_title": "Honeywell 1006186 Earplug",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "none",
                "numeric_keep_guard_applied": True,
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "no_price_found",
                "source_role": "industrial_distributor",
                "exact_pn_confirmed": False,
                "exact_product_page": False,
                "page_context_clean": True,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
            pdf_signal={
                "datasheet_status": "missing",
                "candidate_ids": ["cand_pdf_1"],
                "evidence_ids": ["ev_pdf_1"],
            },
        )
        assert decision.card_status == "DRAFT_ONLY"
        assert decision.policy_rule_id == "CAP-09"

    def test_weak_identity_without_accepted_price_stays_draft(self):
        decision = card_status_calculator(
            identity_level="weak",
            title_signal={
                "derived_title": "Honeywell 1011893-RU Harness",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "none",
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "ambiguous_offer",
                "source_role": "industrial_distributor",
                "exact_pn_confirmed": True,
                "exact_product_page": True,
                "page_context_clean": True,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
            pdf_signal={
                "datasheet_status": "missing",
                "candidate_ids": ["cand_pdf_1"],
                "evidence_ids": ["ev_pdf_1"],
            },
        )
        assert decision.card_status == "DRAFT_ONLY"
        assert decision.policy_rule_id == "CAP-09"

    def test_terminal_weak_no_price_lineage_routes_to_explicit_draft_disposition(self):
        decision = card_status_calculator(
            identity_level="weak",
            title_signal={
                "derived_title": "Honeywell 1006186 Earplug",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "none",
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "no_price_found",
                "source_role": "organic_discovery",
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_terminal_weak_lineage": True,
                "price_source_admissible_replacement_confirmed": False,
                "reviewable_no_price_candidate": False,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
            pdf_signal={
                "datasheet_status": "missing",
                "candidate_ids": ["cand_pdf_1"],
                "evidence_ids": ["ev_pdf_1"],
            },
        )
        assert decision.card_status == "DRAFT_ONLY"
        assert decision.policy_rule_id == "CAP-09T"
        reason_codes = {reason.reason_code for reason in decision.review_reasons}
        assert "TERMINAL_WEAK_NO_PRICE_LINEAGE" in reason_codes
        assert "NO_PRICE_EVIDENCE" not in reason_codes

    def test_admissible_source_conflict_no_price_routes_to_explicit_draft_disposition(self):
        decision = card_status_calculator(
            identity_level="weak",
            title_signal={
                "derived_title": "Honeywell 1006186 Earplug",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "none",
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "no_price_found",
                "source_role": "authorized_distributor",
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_admissible_replacement_confirmed": True,
                "price_source_terminal_weak_lineage": False,
                "price_source_replacement_reason_code": "source_already_admissible",
                "price_source_surface_conflict_detected": True,
                "price_source_surface_conflict_reason_code": "current_surface_conflicts_with_prior",
                "reviewable_no_price_candidate": False,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
            pdf_signal={
                "datasheet_status": "missing",
                "candidate_ids": ["cand_pdf_1"],
                "evidence_ids": ["ev_pdf_1"],
            },
        )
        assert decision.card_status == "DRAFT_ONLY"
        assert decision.policy_rule_id == "CAP-09A"
        reason_codes = {reason.reason_code for reason in decision.review_reasons}
        assert "ADMISSIBLE_SOURCE_NO_PRICE_CONFLICT" in reason_codes
        assert "NO_PRICE_EVIDENCE" not in reason_codes
        price_reason = next(reason for reason in decision.review_reasons if reason.field == "price")
        assert price_reason.bucket == "PRICE_AMBIGUITY"

    def test_admissible_replacement_confirmed_conflict_routes_to_cap_09a(self):
        decision = card_status_calculator(
            identity_level="weak",
            title_signal={
                "derived_title": "Honeywell 1006186 Earplug",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "none",
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "no_price_found",
                "source_role": "other",
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_admissible_replacement_confirmed": True,
                "price_source_terminal_weak_lineage": False,
                "price_source_replacement_reason_code": "admissible_replacement_confirmed",
                "price_source_surface_conflict_detected": True,
                "price_source_surface_conflict_reason_code": "current_surface_conflicts_with_prior",
                "reviewable_no_price_candidate": False,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
            pdf_signal={
                "datasheet_status": "missing",
                "candidate_ids": ["cand_pdf_1"],
                "evidence_ids": ["ev_pdf_1"],
            },
        )
        assert decision.card_status == "DRAFT_ONLY"
        assert decision.policy_rule_id == "CAP-09A"
        reason_codes = {reason.reason_code for reason in decision.review_reasons}
        assert "ADMISSIBLE_SOURCE_NO_PRICE_CONFLICT" in reason_codes
        assert "NO_PRICE_EVIDENCE" not in reason_codes

    def test_admissible_source_exact_lineage_no_price_routes_to_explicit_draft_disposition(self):
        decision = card_status_calculator(
            identity_level="weak",
            title_signal={
                "derived_title": "Honeywell 1006186 Earplug",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "none",
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "no_price_found",
                "source_role": "authorized_distributor",
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_admissible_replacement_confirmed": True,
                "price_source_terminal_weak_lineage": False,
                "price_source_replacement_reason_code": "source_already_admissible",
                "price_source_surface_stable": True,
                "price_source_surface_seen_current_run": True,
                "price_source_surface_conflict_detected": False,
                "price_source_surface_preservation_reason_code": "current_surface_matches_prior",
                "reviewable_no_price_candidate": False,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
            pdf_signal={
                "datasheet_status": "missing",
                "candidate_ids": ["cand_pdf_1"],
                "evidence_ids": ["ev_pdf_1"],
            },
        )
        assert decision.card_status == "DRAFT_ONLY"
        assert decision.policy_rule_id == "CAP-09B"
        reason_codes = {reason.reason_code for reason in decision.review_reasons}
        assert "ADMISSIBLE_SOURCE_NO_PRICE_EXACT_LINEAGE" in reason_codes
        assert "NO_PRICE_EVIDENCE" not in reason_codes
        price_reason = next(reason for reason in decision.review_reasons if reason.field == "price")
        assert price_reason.bucket == "MISSING_MINIMUM_EVIDENCE"

    def test_admissible_replacement_confirmed_no_price_routes_to_cap_09b(self):
        decision = card_status_calculator(
            identity_level="weak",
            title_signal={
                "derived_title": "Honeywell 1006186 Earplug",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "none",
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "no_price_found",
                "source_role": "other",
                "price_source_exact_product_lineage_confirmed": True,
                "price_source_admissible_replacement_confirmed": True,
                "price_source_terminal_weak_lineage": False,
                "price_source_replacement_reason_code": "admissible_replacement_confirmed",
                "price_source_surface_conflict_detected": False,
                "reviewable_no_price_candidate": False,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
            pdf_signal={
                "datasheet_status": "missing",
                "candidate_ids": ["cand_pdf_1"],
                "evidence_ids": ["ev_pdf_1"],
            },
        )
        assert decision.card_status == "DRAFT_ONLY"
        assert decision.policy_rule_id == "CAP-09B"
        reason_codes = {reason.reason_code for reason in decision.review_reasons}
        assert "ADMISSIBLE_SOURCE_NO_PRICE_EXACT_LINEAGE" in reason_codes
        assert "NO_PRICE_EVIDENCE" not in reason_codes

    def test_non_exact_no_price_tail_stays_generic_draft(self):
        decision = card_status_calculator(
            identity_level="weak",
            title_signal={
                "derived_title": "Honeywell 1012541 Safety product",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "none",
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "no_price_found",
                "source_role": "authorized_distributor",
                "price_source_exact_product_lineage_confirmed": False,
                "price_source_admissible_replacement_confirmed": False,
                "price_source_terminal_weak_lineage": False,
                "price_source_replacement_reason_code": "source_already_admissible",
                "price_source_surface_conflict_detected": False,
                "price_source_surface_preservation_reason_code": "no_prior_surface_available",
                "reviewable_no_price_candidate": False,
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
            pdf_signal={
                "datasheet_status": "missing",
                "candidate_ids": ["cand_pdf_1"],
                "evidence_ids": ["ev_pdf_1"],
            },
        )
        assert decision.card_status == "DRAFT_ONLY"
        assert decision.policy_rule_id == "CAP-09"
        reason_codes = {reason.reason_code for reason in decision.review_reasons}
        assert "NO_PRICE_EVIDENCE" in reason_codes
        assert "ADMISSIBLE_SOURCE_NO_PRICE_EXACT_LINEAGE" not in reason_codes

    def test_price_role_not_admissible_routes_to_review(self):
        decision = card_status_calculator(
            identity_level="strong",
            title_signal={
                "derived_title": "Honeywell 00020211",
                "candidate_ids": ["cand_title_1"],
                "evidence_ids": ["ev_title_1"],
            },
            image_signal={
                "photo_type": "exact",
                "candidate_ids": ["cand_image_1"],
                "evidence_ids": ["ev_image_1"],
            },
            price_signal={
                "price_status": "public_price",
                "source_role": "organic_discovery",
                "candidate_ids": ["cand_price_1"],
                "evidence_ids": ["ev_price_1"],
            },
        )
        assert decision.price_status == "REVIEW_REQUIRED"
        reason_codes = {r.reason_code for r in decision.review_reasons}
        assert "PRICE_ROLE_NOT_ADMISSIBLE" in reason_codes

    def test_invalid_identity_raises(self):
        with pytest.raises(ValueError):
            card_status_calculator(identity_level="high")


class TestLegacyPdfIdentityAdapter:

    def test_pdf_exact_pn_confirmed_upgrades_identity_to_strong(self):
        identity = _infer_identity_level(
            photo_result={"pn_match_location": ""},
            datasheet_result={"pdf_exact_pn_confirmed": True},
        )
        assert identity == "strong"

    def test_pn_confirmed_in_pdf_with_allowed_tier_and_found_datasheet_is_strong(self):
        identity = _infer_identity_level(
            photo_result={"pn_match_location": ""},
            datasheet_result={
                "datasheet_status": "found",
                "pdf_source_tier": "authorized",
                "pn_confirmed_in_pdf": True,
            },
        )
        assert identity == "strong"

    def test_pdf_url_alone_does_not_upgrade_identity(self):
        identity = _infer_identity_level(
            photo_result={"pn_match_location": ""},
            datasheet_result={
                "datasheet_status": "found",
                "pdf_source_tier": "authorized",
                "pdf_url": "https://example.com/spec.pdf",
            },
        )
        assert identity == "weak"

    def test_pdf_text_excerpt_does_not_upgrade_identity(self):
        identity = _infer_identity_level(
            photo_result={"pn_match_location": ""},
            datasheet_result={
                "datasheet_status": "found",
                "pdf_source_tier": "authorized",
                "pdf_text_excerpt": "Part number 00020211",
            },
        )
        assert identity == "weak"

    def test_pdf_specs_do_not_upgrade_identity(self):
        identity = _infer_identity_level(
            photo_result={"pn_match_location": ""},
            datasheet_result={
                "datasheet_status": "found",
                "pdf_source_tier": "authorized",
                "pdf_specs": {"Item Code": "00020211"},
            },
        )
        assert identity == "weak"

    def test_disallowed_pdf_source_tier_does_not_upgrade_identity(self):
        identity = _infer_identity_level(
            photo_result={"pn_match_location": ""},
            datasheet_result={
                "datasheet_status": "found",
                "pdf_source_tier": "organic",
                "pn_confirmed_in_pdf": True,
            },
        )
        assert identity == "weak"

    def test_missing_found_status_does_not_upgrade_identity(self):
        identity = _infer_identity_level(
            photo_result={"pn_match_location": ""},
            datasheet_result={
                "datasheet_status": "not_found",
                "pdf_source_tier": "authorized",
                "pn_confirmed_in_pdf": True,
            },
        )
        assert identity == "weak"

    def test_adapter_materializes_strong_identity_from_safe_pdf_signal(self):
        decision = build_decision_record_v2_from_legacy_inputs(
            pn="00020211",
            name="Temperature Sensor",
            assembled_title="Honeywell 00020211 Temperature Sensor",
            photo_result={},
            vision_verdict={"verdict": "NO_PHOTO"},
            price_result={
                "price_status": "public_price",
                "source_tier": "authorized",
            },
            datasheet_result={
                "datasheet_status": "found",
                "pdf_source_tier": "authorized",
                "pn_confirmed_in_pdf": True,
            },
        )
        assert decision["identity_level"] == "strong"

    def test_adapter_routes_clean_weak_identity_case_to_review(self):
        decision = build_decision_record_v2_from_legacy_inputs(
            pn="010130.10",
            name="Module",
            assembled_title="Honeywell 010130.10 Module",
            photo_result={
                "numeric_keep_guard_applied": False,
            },
            vision_verdict={"verdict": "REJECT", "reason": "banner"},
            price_result={
                "price_status": "public_price",
                "source_tier": "authorized",
                "category_mismatch": False,
                "brand_mismatch": False,
            },
            datasheet_result={
                "datasheet_status": "no_pn_confirm",
                "pdf_source_tier": "authorized",
                "pn_confirmed_in_pdf": False,
            },
        )
        assert decision["identity_level"] == "weak"
        assert decision["price_status"] == "ACCEPTED"
        assert decision["card_status"] == "REVIEW_REQUIRED"
        assert decision["policy_rule_id"] == "CAP-08W"

    def test_adapter_routes_numeric_guarded_clean_price_case_to_review(self):
        decision = build_decision_record_v2_from_legacy_inputs(
            pn="1000106",
            name="Earplug",
            assembled_title="Honeywell 1000106 Earplug",
            photo_result={
                "numeric_keep_guard_applied": True,
            },
            vision_verdict={"verdict": "REJECT", "reason": "guarded"},
            price_result={
                "price_status": "public_price",
                "source_tier": "industrial",
                "category_mismatch": False,
                "brand_mismatch": False,
            },
            datasheet_result={
                "datasheet_status": "found",
                "pdf_source_tier": "industrial",
                "pn_confirmed_in_pdf": True,
            },
        )
        assert decision["identity_level"] == "weak"
        assert decision["card_status"] == "REVIEW_REQUIRED"
        assert decision["policy_rule_id"] == "CAP-08N"
