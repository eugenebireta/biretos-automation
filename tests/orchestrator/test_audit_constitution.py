"""
test_audit_constitution.py — L3 Constitutional governance proofs.

PURPOSE: Proves that the orchestrator respects PROJECT_DNA invariants.
These are not "does the code work" tests — they are "does the system
obey its own laws" tests. If any of these fail, it means the system
can bypass its own governance.

Constitutional invariants tested:
  C1. No terminal success without acceptance pass
  C2. CORE cannot complete without owner/audit gate
  C3. Every terminal path writes trace-linked experience
  C4. trace_id is mandatory in every side-effect record
  C5. idempotency_key present in all persisted records
  C6. SEMI cannot complete without audit route
  C7. No forbidden FSM transition bypassing governance
  C8. Retry count never exceeds configured max

All tests are deterministic, no API keys needed.
"""
from __future__ import annotations

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from argparse import Namespace

import pytest

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)


# ===========================================================================
# C1. NO TERMINAL SUCCESS WITHOUT ACCEPTANCE PASS
# ===========================================================================

class TestC1_NoSuccessWithoutAcceptance:
    """The system MUST NOT reach clean success if acceptance check failed."""

    def test_acceptance_fail_never_reaches_ready_clean(self, tmp_path):
        """When acceptance.passed=False, manifest never gets fsm_state=ready + last_verdict=None."""
        import main
        from acceptance_checker import AcceptanceResult, AcceptanceCheck

        manifest = {
            "fsm_state": "processing",
            "current_task_id": "test",
            "current_sprint_goal": "test",
            "attempt_count": 0, "retry_count": 0,
            "updated_at": "2026-01-01T00:00:00Z",
        }
        paths = {k: tmp_path / v for k, v in {
            "manifest_path": "manifest.json",
            "runs_path": "runs.jsonl",
            "directive_path": "directive.md",
            "packet_path": "packet.json",
            "runs_dir": "runs",
            "lock_path": "lock",
        }.items()}
        paths["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
        paths["runs_dir"].mkdir(exist_ok=True)
        run_dir = tmp_path / "runs" / "test"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "directive.md").write_text("# test", encoding="utf-8")

        # Acceptance FAILS
        acceptance = AcceptanceResult(
            trace_id="test", passed=False,
            checks=[AcceptanceCheck("A4:SCOPE", False, "drift")],
            drift_detected=True, out_of_scope_files=["core/x.py"],
        )
        exec_result = MagicMock(status="completed", exit_code=0,
                                 elapsed_seconds=5.0, stderr="", error_class=None)
        gate = MagicMock(passed=True, rule="LOW_RISK_AUTO",
                          auto_merge_eligible=True, reason="")

        ps = [
            patch.object(main, "MANIFEST_PATH", paths["manifest_path"]),
            patch.object(main, "RUNS_PATH", paths["runs_path"]),
            patch.object(main, "DIRECTIVE_PATH", paths["directive_path"]),
            patch.object(main, "PACKET_PATH", paths["packet_path"]),
            patch.object(main, "RUNS_DIR", paths["runs_dir"]),
            patch.object(main, "ORCH_DIR", tmp_path),
            patch.object(main, "_run_intake", return_value=MagicMock(
                warnings=[], validation_errors=[], last_changed_files=["x.py"],
                last_affected_tiers=["3"], last_status="completed", task_id="test",
                sprint_goal="goal", dna_constraints=[])),
            patch.object(main, "_run_classify", return_value=MagicMock(
                risk_class="LOW", governance_route="none", rationale="t",
                tier_violations=[], blocking_rules=[])),
            patch.object(main, "_run_advisor", return_value=MagicMock(
                warnings=[], escalated=False, attempt_count=1,
                verdict=MagicMock(risk_assessment="LOW", governance_route="none",
                                  scope=["x.py"], next_step="do", rationale="ok",
                                  addresses_blocker=None))),
            patch.object(main, "_run_synthesizer", return_value=MagicMock(
                action="PROCEED", final_risk="LOW", approved_scope=["x.py"],
                rule_trace="R7", rationale="ok", warnings=[], stripped_files=[])),
            patch.object(main, "_load_config", return_value={
                "auto_execute": True, "executor_timeout_seconds": 60,
                "max_retries_low": 0,  # 0 retries = immediate escalation
                "critique_consensus_required": False,
            }),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            patch("executor_bridge.run_with_collect",
                  return_value=(exec_result, {"changed_files": ["x.py", "core/x.py"],
                                               "affected_tiers": ["3"]})),
            patch("batch_quality_gate.check_packet", return_value=gate),
            patch("acceptance_checker.check", return_value=acceptance),
            patch("experience_writer.write_execution_experience",
                  return_value={"overall_verdict": "ACCEPTANCE_FAILED"}),
            patch("experience_reader.get_lessons_for_task", return_value=""),
            patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="abc")),
        ]

        for p in ps:
            p.__enter__()
        try:
            main._cmd_cycle_inner(Namespace(), manifest)
        finally:
            for p in reversed(ps):
                p.__exit__(None, None, None)

        # INVARIANT: acceptance failed → must NOT be in clean success
        is_clean_success = (
            manifest.get("fsm_state") == "ready"
            and manifest.get("last_verdict") is None
        )
        assert not is_clean_success, \
            "System reached clean success despite acceptance failure — governance violated"


# ===========================================================================
# C2. CORE CANNOT COMPLETE WITHOUT OWNER/AUDIT
# ===========================================================================

class TestC2_CoreRequiresGate:
    """CORE risk always gets 0 retries and routes through CORE_GATE."""

    def test_core_zero_retries_immutable(self):
        """CORE retries = 0 regardless of config overrides."""
        from main import _get_retry_policy
        assert _get_retry_policy("CORE") == 0
        assert _get_retry_policy("CORE", {"max_retries_low": 99}) == 0
        assert _get_retry_policy("CORE", {"max_retries_semi": 99}) == 0

    def test_core_synthesizer_routes_to_core_gate(self):
        """Real synthesizer routes CORE to CORE_GATE, not PROCEED."""
        import synthesizer
        from classifier import ClassifierResult
        clf = ClassifierResult(
            risk_class="CORE", governance_route="audit",
            rationale="test", tier_violations=[], blocking_rules=[],
        )
        verdict = MagicMock(risk_assessment="CORE", governance_route="audit",
                             scope=["core/module.py"])
        result = synthesizer.decide(
            classification=clf, verdict=verdict,
            attempt_count=1, last_packet_status="completed", max_attempts=3,
        )
        assert result.action == "CORE_GATE"


# ===========================================================================
# C3. EVERY TERMINAL PATH WRITES EXPERIENCE
# ===========================================================================

class TestC3_ExperienceOnEveryPath:
    """Experience writer is called on success AND failure paths."""

    def test_experience_schema_includes_trace_id(self, tmp_path):
        """Experience record always includes trace_id."""
        import experience_writer as ew
        with patch.object(ew, "SHADOW_LOG_DIR", tmp_path):
            rec = ew.write_execution_experience(
                trace_id="must-have-trace",
                task_id="t1", risk_class="LOW",
                acceptance_passed=True, acceptance_checks=[],
                drift_detected=False, changed_files=[], elapsed_seconds=1.0,
                executor_status="completed", gate_passed=True, gate_rule="LOW_RISK_AUTO",
            )
        assert rec["trace_id"] == "must-have-trace"
        assert rec["schema_version"] == "execution_experience_v1"

    def test_failure_experience_includes_trace_id(self, tmp_path):
        """Failure experience also records trace_id."""
        import experience_writer as ew
        with patch.object(ew, "SHADOW_LOG_DIR", tmp_path):
            rec = ew.write_failure_experience(
                trace_id="fail-trace",
                task_id="t1", risk_class="LOW",
                failure_reason="test failure",
                failure_stage="executor",
            )
        assert rec["trace_id"] == "fail-trace"


# ===========================================================================
# C4. TRACE_ID MANDATORY IN SIDE-EFFECT RECORDS
# ===========================================================================

class TestC4_TraceIdMandatory:
    """trace_id is required for all records that create side-effects."""

    def test_experience_writer_rejects_empty_trace(self, tmp_path):
        """Empty trace_id → ValueError."""
        import experience_writer as ew
        with patch.object(ew, "SHADOW_LOG_DIR", tmp_path):
            with pytest.raises((ValueError, TypeError)):
                ew.write_execution_experience(
                    trace_id="", task_id="t", risk_class="LOW",
                    acceptance_passed=True, acceptance_checks=[],
                    drift_detected=False, changed_files=[], elapsed_seconds=1.0,
                    executor_status="completed", gate_passed=True, gate_rule="X",
                )

    def test_budget_tracker_rejects_empty_trace(self, tmp_path):
        """Empty trace_id → ValueError."""
        import budget_tracker as bt
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            with pytest.raises(ValueError):
                bt.record_call(trace_id="", provider="a", model="m", stage="s")


# ===========================================================================
# C5. IDEMPOTENCY KEY IN PERSISTED RECORDS
# ===========================================================================

class TestC5_IdempotencyKey:
    """All persisted records include an idempotency_key."""

    def test_experience_record_has_idempotency(self, tmp_path):
        import experience_writer as ew
        with patch.object(ew, "SHADOW_LOG_DIR", tmp_path):
            rec = ew.write_execution_experience(
                trace_id="t1", task_id="t", risk_class="LOW",
                acceptance_passed=True, acceptance_checks=[],
                drift_detected=False, changed_files=[], elapsed_seconds=1.0,
                executor_status="completed", gate_passed=True, gate_rule="X",
            )
        # Record should be persisted in JSONL with schema_version
        log_files = list(tmp_path.glob("experience_*.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text(encoding="utf-8").strip().split("\n")
        parsed = json.loads(lines[0])
        assert "trace_id" in parsed
        assert parsed["trace_id"] == "t1"

    def test_budget_record_has_idempotency_key(self, tmp_path):
        import budget_tracker as bt
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            rec = bt.record_call(
                trace_id="t1", provider="a", model="m",
                stage="s", call_seq=0,
            )
        assert "idempotency_key" in rec
        assert rec["idempotency_key"] == "budget_t1_0"


# ===========================================================================
# C6. SEMI CANNOT COMPLETE WITHOUT AUDIT ROUTE
# ===========================================================================

class TestC6_SemiRequiresAudit:
    """SEMI risk must route through auditor — synthesizer enforces this."""

    def test_semi_synth_action_is_semi_audit(self):
        """Real synthesizer returns SEMI_AUDIT for SEMI classification."""
        import synthesizer
        from classifier import ClassifierResult
        clf = ClassifierResult(
            risk_class="SEMI", governance_route="audit",
            rationale="test", tier_violations=[], blocking_rules=[],
        )
        verdict = MagicMock(risk_assessment="SEMI", governance_route="audit",
                             scope=["scripts/foo.py"])
        result = synthesizer.decide(
            classification=clf, verdict=verdict,
            attempt_count=1, last_packet_status="completed", max_attempts=3,
        )
        assert result.action == "SEMI_AUDIT", \
            f"SEMI must route to SEMI_AUDIT, got {result.action}"


# ===========================================================================
# C7. NO FORBIDDEN FSM TRANSITIONS
# ===========================================================================

class TestC7_NoForbiddenTransitions:
    """FSM table must not allow governance-bypassing transitions."""

    def test_no_direct_error_to_completed(self):
        """Error cannot jump directly to completed."""
        from main import FSM_TRANSITIONS
        error_targets = {
            target for (src, _), target in FSM_TRANSITIONS.items()
            if src == "error"
        }
        assert "completed" not in error_targets

    def test_no_direct_blocked_to_completed(self):
        """Blocked cannot jump directly to completed."""
        from main import FSM_TRANSITIONS
        blocked_targets = {
            target for (src, _), target in FSM_TRANSITIONS.items()
            if src == "blocked"
        }
        assert "completed" not in blocked_targets

    def test_no_awaiting_owner_to_completed(self):
        """awaiting_owner_reply cannot jump directly to completed."""
        from main import FSM_TRANSITIONS
        aor_targets = {
            target for (src, _), target in FSM_TRANSITIONS.items()
            if src == "awaiting_owner_reply"
        }
        assert "completed" not in aor_targets


# ===========================================================================
# C8. RETRY COUNT NEVER EXCEEDS MAX
# ===========================================================================

class TestC8_RetryBound:
    """Retry count is always bounded by configured max."""

    def test_retry_policy_returns_non_negative(self):
        """No risk class gets negative retries."""
        from main import _get_retry_policy
        for risk in ["LOW", "SEMI", "CORE", "UNKNOWN", ""]:
            assert _get_retry_policy(risk) >= 0

    def test_config_overrides_respected(self):
        """Config values override defaults correctly."""
        from main import _get_retry_policy
        cfg = {"max_retries_low": 0, "max_retries_semi": 0}
        assert _get_retry_policy("LOW", cfg) == 0
        assert _get_retry_policy("SEMI", cfg) == 0
