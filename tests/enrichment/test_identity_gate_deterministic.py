"""tests/enrichment/test_identity_gate_deterministic.py — Identity gate unit tests.

Covers:
  A. Brand guard: exact/ecosystem/mismatch/unknown
  B. PN match: exact/ambiguous/unknown
  C. Category match: consistent/inconsistent/unknown
  D. Full gate: pass/review/block combinations
  E. Specs & price gating properties
  F. Regression: subbrand ecosystem, dead brand_mismatch hole
"""
import sys
import os

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from identity_gate import (
    evaluate_brand_match,
    evaluate_pn_match,
    evaluate_category_match,
    evaluate_identity_gate,
    IdentityGateResult,
    _brands_in_same_ecosystem,
)


# ══════════════════════════════════════════════════════════════════════════════
# A. Brand guard
# ══════════════════════════════════════════════════════════════════════════════

class TestBrandMatch:

    def test_exact_match(self):
        status, reasons = evaluate_brand_match("Honeywell", "Honeywell")
        assert status == "confirmed"
        assert reasons == []

    def test_exact_match_case_insensitive(self):
        status, _ = evaluate_brand_match("HONEYWELL", "honeywell")
        assert status == "confirmed"

    def test_subbrand_exact_match(self):
        """Found brand matches expected_subbrand."""
        status, _ = evaluate_brand_match("Honeywell", "PEHA", expected_subbrand="PEHA")
        assert status == "confirmed"

    def test_ecosystem_match_peha_honeywell(self):
        """PEHA found for Honeywell expected — ecosystem match, not mismatch."""
        status, reasons = evaluate_brand_match("Honeywell", "PEHA")
        assert status == "ecosystem_match"
        assert any("ecosystem_match" in r for r in reasons)

    def test_ecosystem_match_esser_honeywell(self):
        status, _ = evaluate_brand_match("Honeywell", "Esser")
        assert status == "ecosystem_match"

    def test_ecosystem_match_notifier_honeywell(self):
        status, _ = evaluate_brand_match("Honeywell", "Notifier")
        assert status == "ecosystem_match"

    def test_brand_mismatch_different_brands(self):
        """Completely different brands → mismatch."""
        status, reasons = evaluate_brand_match("Honeywell", "Siemens")
        assert status == "mismatch"
        assert any("brand_mismatch" in r for r in reasons)

    def test_unknown_no_found_brand(self):
        status, reasons = evaluate_brand_match("Honeywell", "")
        assert status == "unknown"
        assert "brand_unknown_no_found_brand" in reasons

    def test_unknown_no_expected_brand(self):
        status, reasons = evaluate_brand_match("", "Siemens")
        assert status == "unknown"
        assert "brand_unknown_no_expected_brand" in reasons

    def test_both_empty(self):
        status, _ = evaluate_brand_match("", "")
        assert status == "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# B. PN match
# ══════════════════════════════════════════════════════════════════════════════

class TestPnMatch:

    def test_identity_confirmed_true(self):
        status, _ = evaluate_pn_match(identity_confirmed=True)
        assert status == "exact"

    def test_identity_confirmed_false(self):
        status, reasons = evaluate_pn_match(identity_confirmed=False)
        assert status == "ambiguous"
        assert "pn_identity_not_confirmed" in reasons

    def test_jsonld_location(self):
        status, _ = evaluate_pn_match(None, pn_match_location="jsonld")
        assert status == "exact"

    def test_title_location(self):
        status, _ = evaluate_pn_match(None, pn_match_location="title")
        assert status == "exact"

    def test_h1_location(self):
        status, _ = evaluate_pn_match(None, pn_match_location="h1")
        assert status == "exact"

    def test_body_location_ambiguous(self):
        status, reasons = evaluate_pn_match(None, pn_match_location="body")
        assert status == "ambiguous"
        assert "pn_body_match_only" in reasons

    def test_high_confidence(self):
        status, _ = evaluate_pn_match(None, pn_confidence=0.90)
        assert status == "exact"

    def test_moderate_confidence(self):
        status, reasons = evaluate_pn_match(None, pn_confidence=0.60)
        assert status == "ambiguous"

    def test_no_data(self):
        status, reasons = evaluate_pn_match(None)
        assert status == "unknown"
        assert "pn_no_match_data" in reasons


# ══════════════════════════════════════════════════════════════════════════════
# C. Category match
# ══════════════════════════════════════════════════════════════════════════════

class TestCategoryMatch:

    def test_exact_match(self):
        status, _ = evaluate_category_match("smoke detector", "smoke detector")
        assert status == "consistent"

    def test_substring_match(self):
        status, _ = evaluate_category_match("detector", "smoke detector")
        assert status == "consistent"

    def test_conflict(self):
        status, reasons = evaluate_category_match("cable", "smoke detector")
        assert status == "inconsistent"
        assert any("conflict" in r for r in reasons)

    def test_no_expected(self):
        """No expected category — trust resolved."""
        status, _ = evaluate_category_match("", "smoke detector")
        assert status == "consistent"

    def test_no_data_at_all(self):
        status, reasons = evaluate_category_match("", "")
        assert status == "unknown"
        assert "category_no_data" in reasons

    def test_only_expected_unreliable(self):
        """Only expected_category available — unreliable, mark unknown."""
        status, reasons = evaluate_category_match("cable", "")
        assert status == "unknown"
        assert "category_only_expected_unreliable" in reasons

    def test_product_category_takes_priority(self):
        """product_category (normalized) used over found_category."""
        status, _ = evaluate_category_match(
            "cable", "cable", product_category="smoke detector"
        )
        # resolved = product_category = "smoke detector", expected = "cable" → conflict
        assert status == "inconsistent"


# ══════════════════════════════════════════════════════════════════════════════
# D. Full gate — pass / review / block
# ══════════════════════════════════════════════════════════════════════════════

class TestFullGate:

    def test_pass_confirmed_brand_exact_pn(self):
        """Brand confirmed + PN exact → PASS."""
        result = evaluate_identity_gate(
            expected_brand="Honeywell",
            found_brand="Honeywell",
            identity_confirmed=True,
        )
        assert result.gate_result == "pass"
        assert result.identity_resolved is True
        assert result.allows_price is True
        assert result.allows_specs is True

    def test_pass_ecosystem_match_exact_pn(self):
        """Ecosystem match (PEHA/Honeywell) + PN exact → PASS."""
        result = evaluate_identity_gate(
            expected_brand="Honeywell",
            found_brand="PEHA",
            identity_confirmed=True,
        )
        assert result.gate_result == "pass"
        assert result.brand_match_status == "ecosystem_match"

    def test_review_confirmed_brand_ambiguous_pn(self):
        """Brand confirmed + PN ambiguous → REVIEW."""
        result = evaluate_identity_gate(
            expected_brand="Honeywell",
            found_brand="Honeywell",
            identity_confirmed=False,
        )
        assert result.gate_result == "review"
        assert "brand_ok_pn_ambiguous" in result.reason_codes
        assert result.allows_price is False
        assert result.allows_specs is True  # specs allowed on review

    def test_review_unknown_brand_exact_pn(self):
        """Unknown brand + exact PN → REVIEW (degraded but usable)."""
        result = evaluate_identity_gate(
            expected_brand="Honeywell",
            found_brand="",
            identity_confirmed=True,
        )
        assert result.gate_result == "review"
        assert "brand_unknown_pn_exact" in result.reason_codes

    def test_block_brand_mismatch(self):
        """Brand mismatch → hard BLOCK regardless of PN."""
        result = evaluate_identity_gate(
            expected_brand="Honeywell",
            found_brand="Siemens",
            identity_confirmed=True,
        )
        assert result.gate_result == "block"
        assert result.is_blocked is True
        assert "brand_guard_block" in result.reason_codes
        assert result.allows_price is False
        assert result.allows_specs is False

    def test_block_unknown_brand_unknown_pn(self):
        """Both unknown → BLOCK (insufficient signals)."""
        result = evaluate_identity_gate(
            expected_brand="Honeywell",
            found_brand="",
        )
        assert result.gate_result == "block"
        assert "insufficient_identity_signals" in result.reason_codes

    def test_block_unknown_brand_ambiguous_pn(self):
        """Unknown brand + ambiguous PN → BLOCK."""
        result = evaluate_identity_gate(
            expected_brand="Honeywell",
            found_brand="",
            identity_confirmed=False,
        )
        assert result.gate_result == "block"

    def test_category_conflict_advisory_on_pass(self):
        """Category inconsistency does NOT block — adds advisory code."""
        result = evaluate_identity_gate(
            expected_brand="Honeywell",
            found_brand="Honeywell",
            identity_confirmed=True,
            expected_category="cable",
            found_category="smoke detector",
        )
        assert result.gate_result == "pass"  # NOT blocked
        assert "category_advisory_conflict" in result.reason_codes


# ══════════════════════════════════════════════════════════════════════════════
# E. Properties: allows_price, allows_specs, is_blocked
# ══════════════════════════════════════════════════════════════════════════════

class TestGateProperties:

    def test_pass_allows_both(self):
        r = IdentityGateResult(gate_result="pass")
        assert r.allows_price is True
        assert r.allows_specs is True
        assert r.is_blocked is False

    def test_review_allows_specs_not_price(self):
        r = IdentityGateResult(gate_result="review")
        assert r.allows_price is False
        assert r.allows_specs is True
        assert r.is_blocked is False

    def test_block_allows_nothing(self):
        r = IdentityGateResult(gate_result="block")
        assert r.allows_price is False
        assert r.allows_specs is False
        assert r.is_blocked is True


# ══════════════════════════════════════════════════════════════════════════════
# F. Regression — P0 holes that this gate closes
# ══════════════════════════════════════════════════════════════════════════════

class TestRegressionP0:

    def test_p0_1_brand_mismatch_no_longer_dead_code(self):
        """P0-1: brand_mismatch was always False in confidence.py.
        Now identity_gate evaluates it deterministically.
        Siemens found for Honeywell expected MUST block."""
        result = evaluate_identity_gate(
            expected_brand="Honeywell",
            found_brand="Siemens",
            identity_confirmed=True,
            pn_confidence=0.99,
        )
        assert result.gate_result == "block"
        assert result.brand_match_status == "mismatch"

    def test_p0_1_subbrand_not_false_positive(self):
        """Legitimate subbrand (PEHA under Honeywell) must NOT trigger mismatch."""
        result = evaluate_identity_gate(
            expected_brand="Honeywell",
            found_brand="PEHA",
            identity_confirmed=True,
        )
        assert result.gate_result == "pass"
        assert result.brand_match_status == "ecosystem_match"

    def test_p0_2_specs_blocked_without_identity(self):
        """P0-2: specs must NOT be accepted when identity is unresolved."""
        result = evaluate_identity_gate(
            expected_brand="Honeywell",
            found_brand="Siemens",  # mismatch
            identity_confirmed=True,
        )
        assert result.allows_specs is False

    def test_ecosystem_symmetry(self):
        """Ecosystem check is symmetric: PEHA→Honeywell same as Honeywell→PEHA."""
        assert _brands_in_same_ecosystem("PEHA", "Honeywell") is True
        assert _brands_in_same_ecosystem("Honeywell", "PEHA") is True

    def test_ecosystem_esser_notifier(self):
        """Esser and Notifier are both Honeywell sub-brands."""
        assert _brands_in_same_ecosystem("Esser", "Notifier") is True
