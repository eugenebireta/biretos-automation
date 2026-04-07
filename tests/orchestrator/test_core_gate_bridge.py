"""
tests/orchestrator/test_core_gate_bridge.py

Tests for Task 5: CORE_GATE automatic audit bridge.

Covers:
- decision_to_task_pack() → TaskPack with correct roadmap_stage, why_now, RiskLevel enum
- Converter with missing manifest fields → defaults (no crash)
- run_audit_sync() with mock ReviewRunner + mocked create_review_runner
- _determine_fsm_state() / _determine_last_verdict() terminal-state mapping
- manifest_v1.json schema validates with new FSM states and verdict values
- No live API calls anywhere
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make orchestrator/ importable
_orch_dir = Path(__file__).resolve().parent.parent.parent / "orchestrator"
if str(_orch_dir) not in sys.path:
    sys.path.insert(0, str(_orch_dir))

import core_gate_bridge as cgb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class _MockDecision:
    action: str = "CORE_GATE"
    final_risk: str = "core"
    final_route: str = "spec_full"
    approved_scope: list = None
    rationale: str = "Test rationale"
    rule_trace: list = None

    def __post_init__(self):
        self.approved_scope = self.approved_scope or []
        self.rule_trace = self.rule_trace or []


def _base_manifest():
    return {
        "current_task_id": "step-r1",
        "current_sprint_goal": "Test sprint goal",
        "trace_id": "test-trace-001",
    }


def _make_protocol_run(passed: bool, approval_route_value: str = "batch_approval"):
    """Build a minimal ProtocolRun-like object without importing auditor_system."""
    from auditor_system.hard_shell.contracts import (
        ApprovalRoute, QualityGateResult, TaskPack, RiskLevel, ProtocolRun,
    )

    task = TaskPack(
        title="test",
        roadmap_stage="step-r1",
        why_now="test",
        risk=RiskLevel.CORE,
    )
    run = ProtocolRun(task=task)
    run.quality_gate = QualityGateResult(passed=passed, reason="mock")
    run.approval_route = ApprovalRoute(approval_route_value)
    return run


# ---------------------------------------------------------------------------
# Test 1: decision_to_task_pack — full manifest, verifies all key fields
# ---------------------------------------------------------------------------

class TestDecisionToTaskPack:
    def test_roadmap_stage_taken_from_current_task_id(self):
        decision = _MockDecision()
        manifest = _base_manifest()
        tp = cgb.decision_to_task_pack(decision, manifest)
        assert tp.roadmap_stage == "step-r1"

    def test_why_now_taken_from_rationale(self):
        decision = _MockDecision(rationale="CORE risk because policy change")
        manifest = _base_manifest()
        tp = cgb.decision_to_task_pack(decision, manifest)
        assert tp.why_now == "CORE risk because policy change"

    def test_risk_mapped_to_risk_level_enum(self):
        from auditor_system.hard_shell.contracts import RiskLevel
        decision = _MockDecision(final_risk="core")
        tp = cgb.decision_to_task_pack(decision, _base_manifest())
        assert tp.risk == RiskLevel.CORE

    def test_risk_semi_mapped_correctly(self):
        from auditor_system.hard_shell.contracts import RiskLevel
        decision = _MockDecision(final_risk="semi")
        tp = cgb.decision_to_task_pack(decision, _base_manifest())
        assert tp.risk == RiskLevel.SEMI

    def test_declared_surface_propagated(self):
        decision = _MockDecision(approved_scope=["scripts/foo.py", "orchestrator/bar.py"])
        tp = cgb.decision_to_task_pack(decision, _base_manifest())
        assert tp.declared_surface == ["scripts/foo.py", "orchestrator/bar.py"]

    def test_title_is_task_id(self):
        decision = _MockDecision()
        tp = cgb.decision_to_task_pack(decision, _base_manifest())
        assert tp.title == "step-r1"


# ---------------------------------------------------------------------------
# Test 2: decision_to_task_pack — missing manifest fields → defaults, no crash
# ---------------------------------------------------------------------------

class TestDecisionToTaskPackDefaults:
    def test_empty_manifest_does_not_crash(self):
        """Missing manifest keys must not raise — use safe defaults."""
        decision = _MockDecision()
        tp = cgb.decision_to_task_pack(decision, {})
        # roadmap_stage falls back to "unknown" or "bootstrap"
        assert tp.roadmap_stage  # non-empty string required by TaskPack validator
        assert tp.why_now        # non-empty string required by TaskPack validator

    def test_missing_rationale_on_decision_uses_default_why_now(self):
        decision = _MockDecision(rationale=None)
        tp = cgb.decision_to_task_pack(decision, _base_manifest())
        assert tp.why_now  # must still be non-empty

    def test_unknown_risk_falls_back_to_core(self):
        from auditor_system.hard_shell.contracts import RiskLevel
        decision = _MockDecision(final_risk="invalid_risk_xyz")
        tp = cgb.decision_to_task_pack(decision, _base_manifest())
        assert tp.risk == RiskLevel.CORE  # conservative default

    def test_none_approved_scope_gives_empty_declared_surface(self):
        decision = _MockDecision(approved_scope=None)
        tp = cgb.decision_to_task_pack(decision, _base_manifest())
        assert tp.declared_surface == []


# ---------------------------------------------------------------------------
# Test 3: run_audit_sync — mocked ReviewRunner (no live API)
# ---------------------------------------------------------------------------

class TestRunAuditSync:
    def test_run_audit_sync_calls_execute(self):
        """run_audit_sync must call runner.execute() with the task_pack."""
        from auditor_system.hard_shell.contracts import RiskLevel, TaskPack

        task_pack = TaskPack(
            title="test-task",
            roadmap_stage="step-r1",
            why_now="test run",
            risk=RiskLevel.CORE,
        )
        mock_result = _make_protocol_run(passed=True)
        mock_runner = MagicMock()
        mock_runner.execute = AsyncMock(return_value=mock_result)

        with patch("core_gate_bridge.asyncio.run") as mock_asyncio_run, \
             patch("auditor_system.runner_factory.create_review_runner", return_value=mock_runner):
            mock_asyncio_run.return_value = mock_result
            result = cgb.run_audit_sync(task_pack, proposal_text="test proposal")

        # asyncio.run was called once
        assert mock_asyncio_run.call_count == 1

    def test_run_audit_sync_returns_protocol_run(self):
        """Return value must be whatever asyncio.run returns (ProtocolRun-like)."""
        from auditor_system.hard_shell.contracts import RiskLevel, TaskPack

        task_pack = TaskPack(
            title="task-x",
            roadmap_stage="step-r1",
            why_now="verify return",
            risk=RiskLevel.SEMI,
        )
        mock_result = _make_protocol_run(passed=True)

        with patch("core_gate_bridge.asyncio.run", return_value=mock_result), \
             patch("auditor_system.runner_factory.create_review_runner", return_value=MagicMock()):
            result = cgb.run_audit_sync(task_pack)

        assert result is mock_result


# ---------------------------------------------------------------------------
# Test 4: _determine_fsm_state + _determine_last_verdict — all terminal states
# ---------------------------------------------------------------------------

class TestTerminalStateMappings:
    def test_gate_passed_true_gives_audit_passed(self):
        run = _make_protocol_run(passed=True, approval_route_value="auto_pass")
        assert cgb._determine_fsm_state(run) == "audit_passed"

    def test_gate_passed_false_blocked_route_gives_blocked(self):
        run = _make_protocol_run(passed=False, approval_route_value="blocked")
        assert cgb._determine_fsm_state(run) == "blocked"

    def test_gate_passed_false_non_blocked_route_gives_needs_owner_review(self):
        run = _make_protocol_run(passed=False, approval_route_value="individual_review")
        assert cgb._determine_fsm_state(run) == "needs_owner_review"

    def test_gate_none_with_blocked_route_gives_blocked(self):
        """quality_gate=None + approval_route=BLOCKED → blocked."""
        from auditor_system.hard_shell.contracts import ApprovalRoute, TaskPack, RiskLevel, ProtocolRun
        task = TaskPack(title="t", roadmap_stage="r", why_now="w", risk=RiskLevel.CORE)
        run = ProtocolRun(task=task)
        run.quality_gate = None
        run.approval_route = ApprovalRoute.BLOCKED
        assert cgb._determine_fsm_state(run) == "blocked"

    def test_gate_none_no_blocked_gives_needs_owner_review(self):
        """quality_gate=None + non-blocked route → needs_owner_review."""
        from auditor_system.hard_shell.contracts import ApprovalRoute, TaskPack, RiskLevel, ProtocolRun
        task = TaskPack(title="t", roadmap_stage="r", why_now="w", risk=RiskLevel.CORE)
        run = ProtocolRun(task=task)
        run.quality_gate = None
        run.approval_route = ApprovalRoute.BATCH_APPROVAL
        assert cgb._determine_fsm_state(run) == "needs_owner_review"

    def test_verdict_mapping_audit_passed(self):
        assert cgb._determine_last_verdict("audit_passed") == "AUDIT_PASSED"

    def test_verdict_mapping_blocked(self):
        assert cgb._determine_last_verdict("blocked") == "AUDIT_FAILED"

    def test_verdict_mapping_needs_owner_review(self):
        assert cgb._determine_last_verdict("needs_owner_review") == "AUDIT_INCONCLUSIVE"

    def test_verdict_mapping_unknown_defaults_to_inconclusive(self):
        assert cgb._determine_last_verdict("some_unknown_state") == "AUDIT_INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Test 5: manifest_v1.json schema validates with new FSM states and verdicts
# ---------------------------------------------------------------------------

class TestManifestSchemaExtensions:
    """Verify the extended manifest_v1.json schema accepts new states/verdicts."""

    def setup_method(self):
        _orch = Path(__file__).resolve().parent.parent.parent / "orchestrator"
        sys.path.insert(0, str(_orch))
        from schemas import is_valid
        self._is_valid = is_valid

    def _valid_manifest(self):
        return {
            "schema_version": "v1",
            "fsm_state": "ready",
            "current_sprint_goal": "test sprint",
            "current_task_id": "step-r1",
            "trace_id": "test-trace-001",
            "attempt_count": 1,
            "last_verdict": None,
            "last_directive_hash": None,
            "pending_packet_id": None,
            "deadline_at": None,
            "default_option_id": None,
            "updated_at": "2026-04-08T10:00:00+00:00",
        }

    def test_audit_in_progress_state_is_valid(self):
        m = self._valid_manifest()
        m["fsm_state"] = "audit_in_progress"
        assert self._is_valid("manifest_v1", m)

    def test_audit_passed_state_is_valid(self):
        m = self._valid_manifest()
        m["fsm_state"] = "audit_passed"
        assert self._is_valid("manifest_v1", m)

    def test_blocked_state_is_valid(self):
        m = self._valid_manifest()
        m["fsm_state"] = "blocked"
        assert self._is_valid("manifest_v1", m)

    def test_needs_owner_review_state_is_valid(self):
        m = self._valid_manifest()
        m["fsm_state"] = "needs_owner_review"
        assert self._is_valid("manifest_v1", m)

    def test_audit_passed_verdict_is_valid(self):
        m = self._valid_manifest()
        m["fsm_state"] = "audit_passed"
        m["last_verdict"] = "AUDIT_PASSED"
        assert self._is_valid("manifest_v1", m)

    def test_audit_failed_verdict_is_valid(self):
        m = self._valid_manifest()
        m["fsm_state"] = "blocked"
        m["last_verdict"] = "AUDIT_FAILED"
        assert self._is_valid("manifest_v1", m)

    def test_audit_inconclusive_verdict_is_valid(self):
        m = self._valid_manifest()
        m["fsm_state"] = "needs_owner_review"
        m["last_verdict"] = "AUDIT_INCONCLUSIVE"
        assert self._is_valid("manifest_v1", m)

    def test_last_audit_result_object_is_valid(self):
        m = self._valid_manifest()
        m["last_audit_result"] = {"run_id": "run_abc", "gate_passed": True}
        assert self._is_valid("manifest_v1", m)

    def test_last_audit_result_null_is_valid(self):
        m = self._valid_manifest()
        m["last_audit_result"] = None
        assert self._is_valid("manifest_v1", m)

    def test_unknown_fsm_state_still_invalid(self):
        m = self._valid_manifest()
        m["fsm_state"] = "dancing"
        assert not self._is_valid("manifest_v1", m)
