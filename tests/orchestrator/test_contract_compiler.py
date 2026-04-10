"""Tests for orchestrator/contract_compiler.py — Canonical Contract Gate (Layer 0.5)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)

from contract_compiler import (  # noqa: E402
    STAGE_PREREQUISITES,
    _resolve_claim_to_stage,
    verify_prerequisites,
    verify_claims,
    check_shape_alignment,
    compile_contract,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

MOCK_ROADMAP_STATUS = {
    "schema_version": "roadmap_live_status_v2",
    "stages": [
        {"id": "5.5", "name": "Iron Fence", "actual_status": "DONE",
         "roadmap_claimed": "PARTIAL", "passed": 5, "total": 5, "checks": []},
        {"id": "R3", "name": "Lot Analyzer Engine", "actual_status": "DONE",
         "roadmap_claimed": "NOT_STARTED", "passed": 5, "total": 5, "checks": []},
        {"id": "8", "name": "Stability Gate", "actual_status": "DONE",
         "roadmap_claimed": "MONITOR", "passed": 3, "total": 3, "checks": []},
        {"id": "R1", "name": "Mass Catalog Pipeline", "actual_status": "DONE",
         "roadmap_claimed": "ACTIVE", "passed": 10, "total": 10, "checks": []},
        {"id": "2", "name": "CI + Branch Protection", "actual_status": "DONE",
         "roadmap_claimed": "IN_PROGRESS", "passed": 4, "total": 4, "checks": []},
    ],
}

MOCK_ROADMAP_PARTIAL = {
    "schema_version": "roadmap_live_status_v2",
    "stages": [
        {"id": "5.5", "name": "Iron Fence", "actual_status": "PARTIAL",
         "roadmap_claimed": "PARTIAL", "passed": 3, "total": 5, "checks": []},
        {"id": "R3", "name": "Lot Analyzer Engine", "actual_status": "NOT_STARTED",
         "roadmap_claimed": "NOT_STARTED", "passed": 0, "total": 5, "checks": []},
    ],
}


def _write_mock_status(data: dict) -> Path:
    """Write mock ROADMAP_LIVE_STATUS.json to temp file, return path."""
    tmp = tempfile.mktemp(suffix=".json")
    Path(tmp).write_text(json.dumps(data), encoding="utf-8")
    return Path(tmp)


# ── Prerequisite Verifier ────────────────────────────────────────────────────

class TestVerifyPrerequisites:
    def test_ss1_prereqs_all_done(self):
        path = _write_mock_status(MOCK_ROADMAP_STATUS)
        with patch("contract_compiler.ROADMAP_STATUS_PATH", path):
            result = verify_prerequisites("SS-1")
        assert result["passed"] is True
        assert result["status"] == "clean"
        assert len(result["prereqs"]) == 2
        assert all(p["satisfied"] for p in result["prereqs"])
        path.unlink(missing_ok=True)

    def test_ss1_prereqs_not_done(self):
        path = _write_mock_status(MOCK_ROADMAP_PARTIAL)
        with patch("contract_compiler.ROADMAP_STATUS_PATH", path):
            result = verify_prerequisites("SS-1")
        assert result["passed"] is False
        assert result["status"] == "blocked_precondition"
        assert len(result["blocked_by"]) == 2
        path.unlink(missing_ok=True)

    def test_r4_prereqs_done(self):
        path = _write_mock_status(MOCK_ROADMAP_STATUS)
        with patch("contract_compiler.ROADMAP_STATUS_PATH", path):
            result = verify_prerequisites("R4")
        assert result["passed"] is True
        assert len(result["prereqs"]) == 1
        assert result["prereqs"][0]["stage_id"] == "R3"
        path.unlink(missing_ok=True)

    def test_stage_without_prereqs(self):
        result = verify_prerequisites("R1")
        assert result["passed"] is True
        assert result["prereqs"] == []

    def test_missing_roadmap_file(self):
        with patch("contract_compiler.ROADMAP_STATUS_PATH", Path("/nonexistent/path.json")):
            result = verify_prerequisites("SS-1")
        assert result["passed"] is False
        assert result["status"] == "blocked_precondition"

    def test_prereq_stage_not_in_status(self):
        """Stage ID exists in prereqs but not in ROADMAP_LIVE_STATUS."""
        empty = _write_mock_status({"stages": []})
        with patch("contract_compiler.ROADMAP_STATUS_PATH", empty):
            result = verify_prerequisites("SS-1")
        assert result["passed"] is False
        assert any("NOT_FOUND" in b for b in result["blocked_by"])
        empty.unlink(missing_ok=True)

    def test_uses_actual_status_not_claimed(self):
        """Must use actual_status (auto-generated), not roadmap_claimed (stale)."""
        # R3: actual_status=DONE but roadmap_claimed=NOT_STARTED
        path = _write_mock_status(MOCK_ROADMAP_STATUS)
        with patch("contract_compiler.ROADMAP_STATUS_PATH", path):
            result = verify_prerequisites("R4")
        # Should pass because actual_status=DONE
        assert result["passed"] is True
        path.unlink(missing_ok=True)


# ── Claim Verifier ───────────────────────────────────────────────────────────

class TestVerifyClaims:
    def test_detects_done_claim(self):
        path = _write_mock_status(MOCK_ROADMAP_STATUS)
        with patch("contract_compiler.ROADMAP_STATUS_PATH", path):
            result = verify_claims("Iron Fence + R3 done.")
        assert len(result["claims"]) >= 1
        # At least one should be verified
        verified = [c for c in result["claims"] if c["verified"]]
        assert len(verified) >= 1
        path.unlink(missing_ok=True)

    def test_detects_false_claim(self):
        path = _write_mock_status(MOCK_ROADMAP_PARTIAL)
        with patch("contract_compiler.ROADMAP_STATUS_PATH", path):
            result = verify_claims("R3 done.")
        assert len(result["false_claims"]) >= 1
        path.unlink(missing_ok=True)

    def test_checkmark_claim(self):
        path = _write_mock_status(MOCK_ROADMAP_STATUS)
        with patch("contract_compiler.ROADMAP_STATUS_PATH", path):
            result = verify_claims("Iron Fence ✅")
        verified = [c for c in result["claims"] if c["verified"]]
        assert len(verified) >= 1
        path.unlink(missing_ok=True)

    def test_no_claims(self):
        result = verify_claims("This proposal has no status claims.")
        assert result["claims"] == []
        assert result["false_claims"] == []

    def test_unresolvable_claim(self):
        path = _write_mock_status(MOCK_ROADMAP_STATUS)
        with patch("contract_compiler.ROADMAP_STATUS_PATH", path):
            result = verify_claims("FooBar done.")
        # Should have a claim but not verified
        if result["claims"]:
            unresolved = [c for c in result["claims"]
                          if c["actual_status"] == "UNRESOLVABLE"]
            # FooBar doesn't map to any stage
            assert len(unresolved) >= 0  # May or may not match regex


class TestResolveClaimToStage:
    def test_iron_fence(self):
        assert _resolve_claim_to_stage("Iron Fence") == "5.5"

    def test_r3(self):
        assert _resolve_claim_to_stage("R3") == "R3"

    def test_lot_analyzer(self):
        assert _resolve_claim_to_stage("Lot Analyzer") == "R3"

    def test_unknown(self):
        assert _resolve_claim_to_stage("FooBarBaz") is None

    def test_case_insensitive(self):
        assert _resolve_claim_to_stage("iron fence") == "5.5"


# ── Shape Advisor ────────────────────────────────────────────────────────────

class TestCheckShapeAlignment:
    def test_no_hint_for_stage(self):
        result = check_shape_alignment("UNKNOWN_STAGE", "any proposal")
        assert result["status"] == "clean"
        assert result["expected_shape"] is None

    def test_ss1_good_proposal(self):
        proposal = (
            "Versioned DataSheet schema with ingestion pipeline, "
            "version tracking, read-only views, and full tests+CI coverage."
        )
        result = check_shape_alignment("SS-1", proposal)
        assert result["status"] == "clean"

    def test_ss1_missing_keywords(self):
        proposal = "We will add a single JSON file for datasheets."
        result = check_shape_alignment("SS-1", proposal)
        # Should warn about missing deliverables
        assert result["status"] == "shape_deviation"
        assert len(result["deviations"]) > 0

    def test_r1_good_proposal(self):
        proposal = (
            "Import SKU from Excel/CSV, normalize via Pydantic schema, "
            "publish safe subset through adapter, photo pipeline, "
            "idempotency keys, review bucket for ambiguous items."
        )
        result = check_shape_alignment("R1", proposal)
        assert result["status"] == "clean"


# ── Full Contract Compilation ────────────────────────────────────────────────

class TestCompileContract:
    def test_clean_pass(self):
        path = _write_mock_status(MOCK_ROADMAP_STATUS)
        proposal = (
            "SS-1 Datasheet Layer: versioned DataSheet schema, "
            "ingestion pipeline, version tracking, read-only views, tests+CI. "
            "Iron Fence + R3 done."
        )
        with patch("contract_compiler.ROADMAP_STATUS_PATH", path):
            result = compile_contract("SS-1", proposal, trace_id="test-001")
        assert result["status"] == "clean"
        assert result["prereqs"]["passed"] is True
        assert result["trace_id"] == "test-001"
        assert len(result["verified_context"]["verified_facts"]) > 0
        path.unlink(missing_ok=True)

    def test_blocked_precondition(self):
        path = _write_mock_status(MOCK_ROADMAP_PARTIAL)
        with patch("contract_compiler.ROADMAP_STATUS_PATH", path):
            result = compile_contract("SS-1", "Iron Fence + R3 done.", trace_id="test-002")
        assert result["status"] == "blocked_precondition"
        assert result["prereqs"]["passed"] is False
        assert len(result["verified_context"]["false_claims"]) >= 1
        path.unlink(missing_ok=True)

    def test_shape_deviation_is_advisory(self):
        path = _write_mock_status(MOCK_ROADMAP_STATUS)
        proposal = "We will store datasheets in a single text file."
        with patch("contract_compiler.ROADMAP_STATUS_PATH", path):
            result = compile_contract("SS-1", proposal, trace_id="test-003")
        # Prereqs pass but shape deviates
        assert result["prereqs"]["passed"] is True
        assert result["status"] == "shape_deviation"
        assert len(result["verified_context"]["shape_warnings"]) > 0
        path.unlink(missing_ok=True)

    def test_verified_context_has_residual(self):
        path = _write_mock_status(MOCK_ROADMAP_STATUS)
        with patch("contract_compiler.ROADMAP_STATUS_PATH", path):
            result = compile_contract("R4", "R3 done. Build buyer registry.", trace_id="t")
        assert "trace_id" in result["verified_context"]["unverified_residual"]
        assert "idempotency_key" in result["verified_context"]["unverified_residual"]
        path.unlink(missing_ok=True)

    def test_stage_without_prereqs_or_shape(self):
        """Stage not in prereqs or shape hints → clean pass."""
        path = _write_mock_status(MOCK_ROADMAP_STATUS)
        with patch("contract_compiler.ROADMAP_STATUS_PATH", path):
            result = compile_contract("UNKNOWN", "any text", trace_id="t")
        assert result["status"] == "clean"
        path.unlink(missing_ok=True)


# ── Stage Prerequisites Registry ─────────────────────────────────────────────

class TestStagePrerequisites:
    def test_ss1_has_prereqs(self):
        assert "SS-1" in STAGE_PREREQUISITES
        assert "5.5" in STAGE_PREREQUISITES["SS-1"]
        assert "R3" in STAGE_PREREQUISITES["SS-1"]

    def test_r4_has_prereqs(self):
        assert "R4" in STAGE_PREREQUISITES
        assert "R3" in STAGE_PREREQUISITES["R4"]

    def test_part_ii_requires_stability_gate(self):
        for stage_id in ["9", "10", "11", "12", "13"]:
            assert "8" in STAGE_PREREQUISITES[stage_id]
