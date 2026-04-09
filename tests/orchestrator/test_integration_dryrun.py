"""
test_integration_dryrun.py — P2 integration: dry-run cycle validation.

Validates the full orchestrator flow with mocked external dependencies:
  1. SEMI audit path: acceptance pass → post-exec audit → retry on audit fail
  2. Queue auto-advance: LOW task completes → next LOW dequeued
  3. Retry directive: correction block injected on acceptance fail

All external calls mocked — no API keys needed.
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

import pytest

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)


# ---------------------------------------------------------------------------
# Mock fixtures
# ---------------------------------------------------------------------------

def _mock_audit_result(passed=True, blocked=False):
    """Create a mock ProtocolRun."""
    result = MagicMock()
    result.run_id = "test-run-001"
    result.quality_gate = MagicMock()
    result.quality_gate.passed = passed
    if blocked:
        route = MagicMock()
        route.value = "BLOCKED"
        result.approval_route = route
    else:
        route = MagicMock()
        route.value = "AUTO" if passed else "MANUAL"
        result.approval_route = route
    result.critiques = []
    result.final_verdicts = []
    result.escalated = False
    return result


def _mock_acceptance(passed=True, drift=False, out_of_scope=None):
    """Create a mock AcceptanceResult."""
    result = MagicMock()
    result.passed = passed
    result.drift_detected = drift
    result.out_of_scope_files = out_of_scope or []
    checks = []
    if not passed:
        check = MagicMock()
        check.check_id = "A4:SCOPE_COMPLIANCE"
        check.passed = False
        check.detail = "drift detected"
        checks.append(check)
    ok_check = MagicMock()
    ok_check.check_id = "A1:NON_EMPTY"
    ok_check.passed = True
    ok_check.detail = "ok"
    checks.append(ok_check)
    result.checks = checks
    return result


# ---------------------------------------------------------------------------
# Test: SEMI post-execution audit flow
# ---------------------------------------------------------------------------

class TestSemiAuditFlow:
    """Validate SEMI post-execution audit is called when acceptance passes."""

    def test_semi_acceptance_pass_triggers_audit(self, tmp_path, capsys):
        """SEMI + acceptance pass → post-exec audit called."""
        import main

        manifest = {
            "fsm_state": "awaiting_execution",
            "current_task_id": "semi-test",
            "current_sprint_goal": "test semi flow",
            "_last_risk_class": "SEMI",
            "_run_dir": str(tmp_path / "run"),
            "retry_count": 0,
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        runs_path = tmp_path / "runs.jsonl"

        # Create run dir with directive
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "directive.md").write_text("# Test directive", encoding="utf-8")

        # Mock executor result
        exec_result = MagicMock()
        exec_result.status = "completed"
        exec_result.exit_code = 0
        exec_result.elapsed_seconds = 10.0
        exec_result.stderr = ""
        exec_result.error_class = None

        packet = {"changed_files": ["scripts/test.py"], "affected_tiers": ["3"],
                  "test_results": {"passed": 5, "failed": 0}}

        gate_result = MagicMock()
        gate_result.passed = True
        gate_result.rule = "LOW_RISK_AUTO"
        gate_result.auto_merge_eligible = True
        gate_result.reason = ""

        acceptance = _mock_acceptance(passed=True)
        audit_result = _mock_audit_result(passed=True)

        # Track if post-exec audit was called
        audit_called = [False]
        original_run_post = None
        def fake_audit(*args, **kwargs):
            audit_called[0] = True
            return audit_result

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "RUNS_PATH", runs_path), \
             patch.object(main, "PACKET_PATH", tmp_path / "packet.json"), \
             patch.object(main, "DIRECTIVE_PATH", tmp_path / "directive.md"), \
             patch("executor_bridge.run_with_collect", return_value=(exec_result, packet)), \
             patch("batch_quality_gate.check_packet", return_value=gate_result), \
             patch("acceptance_checker.check", return_value=acceptance), \
             patch("experience_writer.write_execution_experience", return_value={"overall_verdict": "PASS"}), \
             patch("core_gate_bridge.run_post_execution_audit_sync", side_effect=fake_audit), \
             patch("core_gate_bridge.extract_critique_text", return_value=""), \
             patch("core_gate_bridge._determine_fsm_state", return_value="audit_passed"), \
             patch("core_gate_bridge._determine_last_verdict", return_value="AUDIT_PASSED"):

            cfg = {"auto_execute": False, "executor_timeout_seconds": 60}
            main._run_executor_bridge(manifest, "test-trace", cfg)

        assert audit_called[0], "Post-execution audit should be called for SEMI"
        # Manifest should be set to ready (audit passed)
        assert manifest["fsm_state"] == "ready"

    def test_semi_audit_fail_triggers_retry(self, tmp_path, capsys):
        """SEMI + acceptance pass + audit fail → retry directive written."""
        import main

        manifest = {
            "fsm_state": "awaiting_execution",
            "current_task_id": "semi-retry",
            "current_sprint_goal": "test retry",
            "_last_risk_class": "SEMI",
            "_run_dir": str(tmp_path / "run"),
            "retry_count": 0,
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        runs_path = tmp_path / "runs.jsonl"

        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "directive.md").write_text("# Directive\nDo the thing.\n---\nScope: x.py",
                                              encoding="utf-8")

        exec_result = MagicMock()
        exec_result.status = "completed"
        exec_result.exit_code = 0
        exec_result.elapsed_seconds = 10.0
        exec_result.stderr = ""
        exec_result.error_class = None

        packet = {"changed_files": ["scripts/test.py"], "affected_tiers": ["3"],
                  "test_results": {"passed": 5, "failed": 0}}

        gate_result = MagicMock()
        gate_result.passed = True
        gate_result.rule = "LOW_RISK_AUTO"
        gate_result.auto_merge_eligible = True
        gate_result.reason = ""

        acceptance = _mock_acceptance(passed=True)
        audit_result = _mock_audit_result(passed=False)

        directive_path = tmp_path / "directive.md"
        directive_path.write_text("# Directive\nDo the thing.\n---\nScope: x.py",
                                  encoding="utf-8")

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "RUNS_PATH", runs_path), \
             patch.object(main, "PACKET_PATH", tmp_path / "packet.json"), \
             patch.object(main, "DIRECTIVE_PATH", directive_path), \
             patch("executor_bridge.run_with_collect", return_value=(exec_result, packet)), \
             patch("batch_quality_gate.check_packet", return_value=gate_result), \
             patch("acceptance_checker.check", return_value=acceptance), \
             patch("experience_writer.write_execution_experience", return_value={"overall_verdict": "PASS"}), \
             patch("core_gate_bridge.run_post_execution_audit_sync", return_value=audit_result), \
             patch("core_gate_bridge.extract_critique_text", return_value="[critic] Too broad scope"), \
             patch("core_gate_bridge._determine_fsm_state", return_value="needs_owner_review"), \
             patch("core_gate_bridge._determine_last_verdict", return_value="AUDIT_INCONCLUSIVE"):

            cfg = {"auto_execute": False, "executor_timeout_seconds": 60}
            main._run_executor_bridge(manifest, "test-trace", cfg)

        # Should have scheduled retry (SEMI gets 1 retry)
        assert manifest["fsm_state"] == "awaiting_execution"
        assert manifest["last_verdict"] == "AUDIT_RETRY_SCHEDULED"
        assert manifest["retry_count"] == 1

        # Retry directive should contain critique
        retry_text = directive_path.read_text(encoding="utf-8")
        assert "Auditor Critique" in retry_text
        assert "Too broad scope" in retry_text


# ---------------------------------------------------------------------------
# Test: Queue auto-advance after clean LOW completion
# ---------------------------------------------------------------------------

class TestQueueAutoAdvance:
    """Queue auto-advance after clean task completion."""

    def test_advance_on_clean_low_completion(self, tmp_path):
        import main
        import task_queue as tq

        manifest = {
            "fsm_state": "ready",
            "last_verdict": None,
            "current_task_id": "completed-task",
            "current_sprint_goal": "completed goal",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        runs_path = tmp_path / "runs.jsonl"
        qpath = tmp_path / "q.json"

        with patch.object(tq, "QUEUE_PATH", qpath):
            tq.enqueue("next-task", "Next goal", risk_class="LOW")

        cfg = {"auto_execute": True}

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "RUNS_PATH", runs_path), \
             patch.object(main, "_load_config", return_value=cfg), \
             patch.object(tq, "QUEUE_PATH", qpath):
            main._try_queue_advance(manifest)

        reloaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert reloaded["current_task_id"] == "next-task"
        assert reloaded["current_sprint_goal"] == "Next goal"

    def test_no_advance_for_semi_in_queue(self, tmp_path):
        import main
        import task_queue as tq

        manifest = {
            "fsm_state": "ready",
            "last_verdict": None,
            "current_task_id": "done",
            "current_sprint_goal": "done",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        runs_path = tmp_path / "runs.jsonl"
        qpath = tmp_path / "q.json"

        with patch.object(tq, "QUEUE_PATH", qpath):
            tq.enqueue("semi-task", "Semi goal", risk_class="SEMI")

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "RUNS_PATH", runs_path), \
             patch.object(main, "_load_config", return_value={"auto_execute": True}), \
             patch.object(tq, "QUEUE_PATH", qpath):
            main._try_queue_advance(manifest)

        reloaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert reloaded["current_task_id"] == "done"  # NOT advanced


# ---------------------------------------------------------------------------
# Test: Retry directive injection
# ---------------------------------------------------------------------------

class TestRetryDirectiveInjection:
    """Full flow: acceptance fail → retry directive with corrections."""

    def test_low_acceptance_fail_retries_with_corrections(self, tmp_path):
        import main

        manifest = {
            "fsm_state": "awaiting_execution",
            "current_task_id": "retry-test",
            "current_sprint_goal": "test retry",
            "_last_risk_class": "LOW",
            "_run_dir": str(tmp_path / "run"),
            "retry_count": 0,
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        runs_path = tmp_path / "runs.jsonl"

        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "directive.md").write_text("# Directive\nFix widget.\n---\nScope: scripts/widget.py",
                                              encoding="utf-8")

        exec_result = MagicMock()
        exec_result.status = "completed"
        exec_result.exit_code = 0
        exec_result.elapsed_seconds = 10.0
        exec_result.stderr = ""
        exec_result.error_class = None

        packet = {"changed_files": ["scripts/widget.py", "core/bad.py"],
                  "affected_tiers": ["1", "3"],
                  "test_results": {"passed": 5, "failed": 0}}

        gate_result = MagicMock()
        gate_result.passed = True
        gate_result.rule = "LOW_RISK_AUTO"
        gate_result.auto_merge_eligible = True
        gate_result.reason = ""

        # Acceptance fails — drift detected
        acceptance = _mock_acceptance(passed=False, drift=True,
                                      out_of_scope=["core/bad.py"])

        directive_path = tmp_path / "directive.md"
        directive_path.write_text("# Directive\nFix widget.\n---\nScope: scripts/widget.py",
                                  encoding="utf-8")

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "RUNS_PATH", runs_path), \
             patch.object(main, "PACKET_PATH", tmp_path / "packet.json"), \
             patch.object(main, "DIRECTIVE_PATH", directive_path), \
             patch("executor_bridge.run_with_collect", return_value=(exec_result, packet)), \
             patch("batch_quality_gate.check_packet", return_value=gate_result), \
             patch("acceptance_checker.check", return_value=acceptance), \
             patch("experience_writer.write_execution_experience", return_value={"overall_verdict": "ACCEPTANCE_FAILED"}):

            cfg = {"auto_execute": False, "executor_timeout_seconds": 60}
            main._run_executor_bridge(manifest, "test-trace", cfg)

        assert manifest["retry_count"] == 1
        assert manifest["last_verdict"] == "RETRY_SCHEDULED"
        assert manifest["fsm_state"] == "awaiting_execution"

        # Directive should have corrections injected
        retry_text = directive_path.read_text(encoding="utf-8")
        assert "Previous Attempt Failed" in retry_text
        assert "core/bad.py" in retry_text
        assert "Do NOT touch" in retry_text
