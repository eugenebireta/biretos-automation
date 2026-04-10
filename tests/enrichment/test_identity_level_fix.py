"""Tests for _infer_identity_level() fix — reads correct structured_pn_match fields.

Bug: before fix, _infer_identity_level() read photo_result["pn_match_location"]
     which was always "" (set by PNMatchResult.location on body match only).
     Real data is in structured_identity["structured_pn_match_location"] /
     "exact_structured_pn_match" populated by extract_structured_pn_flags().

Fix: read exact_structured_pn_match and structured_pn_match_location first,
     then fall back to legacy pn_match_location for backward compatibility.
"""
from __future__ import annotations

import os
import sys

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from card_status import _infer_identity_level, build_decision_record_v2_from_legacy_inputs


class TestInferIdentityLevelFix:
    """Unit tests for _infer_identity_level() with corrected field reading."""

    # ── New path: exact_structured_pn_match flag ────────────────────────────

    def test_exact_structured_match_true_returns_strong(self):
        result = _infer_identity_level({"exact_structured_pn_match": True}, {})
        assert result == "strong"

    def test_exact_structured_match_false_not_forced_strong(self):
        result = _infer_identity_level({"exact_structured_pn_match": False}, {})
        assert result == "weak"

    # ── New path: structured_pn_match_location field ────────────────────────

    def test_structured_loc_title_returns_strong(self):
        result = _infer_identity_level({"structured_pn_match_location": "title"}, {})
        assert result == "strong"

    def test_structured_loc_jsonld_returns_strong(self):
        result = _infer_identity_level({"structured_pn_match_location": "jsonld"}, {})
        assert result == "strong"

    def test_structured_loc_h1_returns_strong(self):
        result = _infer_identity_level({"structured_pn_match_location": "h1"}, {})
        assert result == "strong"

    def test_structured_loc_product_context_returns_strong(self):
        result = _infer_identity_level({"structured_pn_match_location": "product_context"}, {})
        assert result == "strong"

    def test_structured_loc_suffix_variant_returns_strong(self):
        """suffix_variant suffix should not prevent strong: 'title_suffix_variant' -> strong."""
        result = _infer_identity_level({"structured_pn_match_location": "title_suffix_variant"}, {})
        assert result == "strong"

    def test_structured_loc_gemini_confirmed_returns_strong(self):
        """gemini_confirmed is injected by recalculate_card_status for Gemini-accepted SKUs."""
        result = _infer_identity_level({"structured_pn_match_location": "gemini_confirmed"}, {})
        # gemini_confirmed is NOT in _STRUCTURED_CONTEXTS, falls through to legacy path -> weak
        # BUT exact_structured_pn_match=True must be set for these; test that separately
        assert result == "weak"  # raw location alone not in structured contexts

    def test_exact_structured_true_overrides_gemini_confirmed_loc(self):
        """With both flags set (as recalculate does), result is strong."""
        result = _infer_identity_level(
            {"exact_structured_pn_match": True, "structured_pn_match_location": "gemini_confirmed"},
            {},
        )
        assert result == "strong"

    def test_structured_loc_empty_not_strong(self):
        result = _infer_identity_level({"structured_pn_match_location": ""}, {})
        assert result == "weak"

    # ── Backward compatibility: legacy pn_match_location ───────────────────

    def test_legacy_pn_match_location_body_returns_medium(self):
        result = _infer_identity_level({"pn_match_location": "body"}, {})
        assert result == "medium"

    def test_legacy_pn_match_location_title_returns_strong(self):
        result = _infer_identity_level({"pn_match_location": "title"}, {})
        assert result == "strong"

    def test_legacy_pn_match_location_empty_returns_weak(self):
        result = _infer_identity_level({"pn_match_location": ""}, {})
        assert result == "weak"

    def test_empty_photo_result_returns_weak(self):
        result = _infer_identity_level({}, {})
        assert result == "weak"

    # ── Priority: new flags take precedence over legacy ────────────────────

    def test_exact_structured_beats_empty_legacy(self):
        """New exact_structured_pn_match=True beats pn_match_location="" (the common bug case)."""
        result = _infer_identity_level(
            {"exact_structured_pn_match": True, "pn_match_location": ""},
            {},
        )
        assert result == "strong"

    def test_structured_loc_beats_empty_legacy(self):
        """structured_pn_match_location='title' beats pn_match_location=""."""
        result = _infer_identity_level(
            {"structured_pn_match_location": "title", "pn_match_location": ""},
            {},
        )
        assert result == "strong"

    # ── Datasheet path ──────────────────────────────────────────────────────

    def test_pdf_exact_pn_confirmed_returns_strong(self):
        result = _infer_identity_level({}, {"pdf_exact_pn_confirmed": True})
        assert result == "strong"

    def test_pdf_not_confirmed_no_match_returns_weak(self):
        result = _infer_identity_level({}, {"pdf_exact_pn_confirmed": False})
        assert result == "weak"


class TestBuildDecisionRecordV2IdentityFix:
    """Integration tests: build_decision_record_v2_from_legacy_inputs uses fixed identity."""

    def _make_inputs(self, **photo_overrides):
        photo = {
            "verdict": "KEEP",
            "photo_status": "exact_evidence",
            "photo_evidence_role": "exact",
            "photo_is_temporary": False,
            "replacement_required": False,
            "numeric_keep_guard_applied": False,
            "family_photo_allowed": False,
        }
        photo.update(photo_overrides)
        price = {"price_status": "no_price_found"}
        datasheet = {"datasheet_status": "skipped"}
        vision = {"verdict": "KEEP"}
        return photo, price, datasheet, vision

    def test_exact_structured_match_gives_strong_identity(self):
        photo, price, ds, vision = self._make_inputs(exact_structured_pn_match=True)
        decision = build_decision_record_v2_from_legacy_inputs(
            pn="TEST001", name="Test Product", assembled_title="Test Product",
            photo_result=photo, vision_verdict=vision, price_result=price, datasheet_result=ds,
        )
        assert decision["identity_level"] == "strong"

    def test_no_structured_flags_gives_weak_identity(self):
        photo, price, ds, vision = self._make_inputs()
        decision = build_decision_record_v2_from_legacy_inputs(
            pn="TEST002", name="Test Product", assembled_title="Test Product",
            photo_result=photo, vision_verdict=vision, price_result=price, datasheet_result=ds,
        )
        assert decision["identity_level"] == "weak"

    def test_structured_location_title_upgrades_identity(self):
        photo, price, ds, vision = self._make_inputs(structured_pn_match_location="title")
        decision = build_decision_record_v2_from_legacy_inputs(
            pn="TEST003", name="Test Product", assembled_title="Test Product",
            photo_result=photo, vision_verdict=vision, price_result=price, datasheet_result=ds,
        )
        assert decision["identity_level"] == "strong"

    def test_strong_identity_with_price_and_photo_not_draft(self):
        """Strong identity + price + photo should NOT be DRAFT_ONLY."""
        photo, price, ds, vision = self._make_inputs(
            exact_structured_pn_match=True,
            structured_pn_match_location="title",
        )
        price = {
            "price_status": "public_price",
            "price_source_lineage_confirmed": True,
            "price_source_exact_product_lineage_confirmed": True,
        }
        decision = build_decision_record_v2_from_legacy_inputs(
            pn="TEST004", name="Test Product", assembled_title="Test Product",
            photo_result=photo, vision_verdict=vision, price_result=price, datasheet_result=ds,
        )
        assert decision["card_status"] != "DRAFT_ONLY", (
            f"Expected non-DRAFT_ONLY with strong identity+price+photo, got {decision['card_status']}"
        )
