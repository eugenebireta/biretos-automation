"""
test_p6_full_cycle.py — P6: Full-cycle integration tests.

Validates the complete orchestrator pipeline _cmd_cycle_inner with all
external modules mocked:
  1. LOW happy path: intake → classify → advisor → synth → directive → executor → gate → acceptance → experience → ready
  2. SEMI with consensus: pre-audit → executor → post-audit → consensus gate
  3. CORE gate block: synth(CORE_GATE) → audit → blocked
  4. Advisor escalation: escalated → awaiting_owner_reply
  5. Synth ESCALATE/BLOCKED: deterministic gate → awaiting_owner_reply
  6. Executor failure: executor crashes → error state
  7. Collect failure: executor OK but packet None → error state
  8. Batch gate failure: gate fails → awaiting_owner_reply

All external calls mocked — no API keys, no subprocess, no file system side-effects.
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY
from argparse import Namespace

import pytest

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)


# ---------------------------------------------------------------------------
# Shared mock factories
# ---------------------------------------------------------------------------

def _mock_bundle():
    b = MagicMock()
    b.warnings = []
    b.validation_errors = []
    b.last_changed_files = ["scripts/foo.py"]
    b.last_affected_tiers = ["3"]
    b.last_status = "completed"
    b.task_id = "test-task"
    b.sprint_goal = "test sprint goal"
    b.dna_constraints = ["no core touch"]
    return b


def _mock_classification(risk="LOW", route="none"):
    c = MagicMock()
    c.risk_class = risk
    c.governance_route = route
    c.rationale = f"test rationale risk={risk}"
    c.tier_violations = []
    c.blocking_rules = []
    return c


def _mock_advisor_result(risk="LOW", route="none", escalated=False):
    ar = MagicMock()
    ar.warnings = []
    ar.escalated = escalated
    ar.escalation_reason = "test escalation" if escalated else None
    ar.attempt_count = 1
    if not escalated:
        v = MagicMock()
        v.risk_assessment = risk
        v.governance_route = route
        v.scope = ["scripts/foo.py"]
        v.next_step = "implement the thing"
        v.rationale = "advisor rationale"
        v.addresses_blocker = None
        ar.verdict = v
    else:
        ar.verdict = None
    return ar


def _mock_synth(action="PROCEED", risk="LOW", scope=None):
    s = MagicMock()
    s.action = action
    s.final_risk = risk
    s.approved_scope = scope or ["scripts/foo.py"]
    s.rule_trace = "R1_PROCEED"
    s.rationale = "test proceed"
    s.warnings = []
    s.stripped_files = []
    return s


def _mock_exec_result(status="completed", exit_code=0, elapsed=5.0):
    er = MagicMock()
    er.status = status
    er.exit_code = exit_code
    er.elapsed_seconds = elapsed
    er.stderr = ""
    er.error_class = None
    return er


def _mock_packet(files=None):
    return {
        "changed_files": files or ["scripts/foo.py"],
        "affected_tiers": ["3"],
        "test_results": {"passed": 5, "failed": 0},
    }


def _mock_gate(passed=True):
    g = MagicMock()
    g.passed = passed
    g.rule = "LOW_RISK_AUTO"
    g.auto_merge_eligible = passed
    g.reason = "" if passed else "gate failed"
    return g


def _mock_acceptance(passed=True, drift=False, oos=None):
    a = MagicMock()
    a.passed = passed
    a.drift_detected = drift
    a.out_of_scope_files = oos or []
    checks = []
    if not passed:
        c = MagicMock()
        c.check_id = "A4:SCOPE_COMPLIANCE"
        c.passed = False
        c.detail = "drift detected"
        checks.append(c)
    ok = MagicMock()
    ok.check_id = "A1:NON_EMPTY"
    ok.passed = True
    ok.detail = "ok"
    checks.append(ok)
    a.checks = checks
    return a


def _mock_audit_result(passed=True, blocked=False):
    r = MagicMock()
    r.run_id = "audit-run-001"
    r.quality_gate = MagicMock()
    r.quality_gate.passed = passed
    r.approval_route = MagicMock()
    r.approval_route.value = "BLOCKED" if blocked else ("AUTO" if passed else "MANUAL")
    r.critiques = []
    r.final_verdicts = []
    r.escalated = False
    return r


# ---------------------------------------------------------------------------
# Patch context for _cmd_cycle_inner
# ---------------------------------------------------------------------------

def _setup_cycle(tmp_path, manifest_overrides=None):
    """Create tmp manifest, runs, directive paths and return manifest dict."""
    manifest = {
        "fsm_state": "processing",
        "current_task_id": "test-task",
        "current_sprint_goal": "test sprint goal",
        "attempt_count": 0,
        "retry_count": 0,
        "updated_at": "2026-01-01T00:00:00Z",
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    runs_path = tmp_path / "runs.jsonl"
    directive_path = tmp_path / "directive.md"
    packet_path = tmp_path / "packet.json"
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(exist_ok=True)
    lock_path = tmp_path / "lock"

    return manifest, {
        "manifest_path": manifest_path,
        "runs_path": runs_path,
        "directive_path": directive_path,
        "packet_path": packet_path,
        "runs_dir": runs_dir,
        "lock_path": lock_path,
    }


def _patch_paths(main_mod, paths):
    """Return a list of patch context managers for all paths."""
    return [
        patch.object(main_mod, "MANIFEST_PATH", paths["manifest_path"]),
        patch.object(main_mod, "RUNS_PATH", paths["runs_path"]),
        patch.object(main_mod, "DIRECTIVE_PATH", paths["directive_path"]),
        patch.object(main_mod, "PACKET_PATH", paths["packet_path"]),
        patch.object(main_mod, "RUNS_DIR", paths["runs_dir"]),
        patch.object(main_mod, "LOCK_PATH", paths["lock_path"]),
        patch.object(main_mod, "ORCH_DIR", paths["manifest_path"].parent),
    ]


# ---------------------------------------------------------------------------
# Test 1: LOW happy path — full pipeline
# ---------------------------------------------------------------------------

class TestLowHappyPath:
    """LOW risk task goes through complete pipeline to ready state."""

    def test_low_full_cycle_to_ready(self, tmp_path, capsys):
        import main

        manifest, paths = _setup_cycle(tmp_path)
        bundle = _mock_bundle()
        classification = _mock_classification("LOW")
        advisor_result = _mock_advisor_result("LOW")
        synth = _mock_synth("PROCEED", "LOW")
        exec_result = _mock_exec_result()
        packet = _mock_packet()
        gate = _mock_gate(True)
        acceptance = _mock_acceptance(True)

        patches = _patch_paths(main, paths)
        patches += [
            patch.object(main, "_run_intake", return_value=bundle),
            patch.object(main, "_run_classify", return_value=classification),
            patch.object(main, "_run_advisor", return_value=advisor_result),
            patch.object(main, "_run_synthesizer", return_value=synth),
            patch.object(main, "_load_config", return_value={
                "auto_execute": True, "executor_timeout_seconds": 60,
                "max_retries_low": 3, "critique_consensus_required": False,
            }),
            patch.object(main, "_ensure_run_dir", return_value=tmp_path / "runs" / "test"),
            patch("executor_bridge.run_with_collect", return_value=(exec_result, packet)),
            patch("batch_quality_gate.check_packet", return_value=gate),
            patch("acceptance_checker.check", return_value=acceptance),
            patch("experience_writer.write_execution_experience",
                  return_value={"overall_verdict": "PASS"}),
            patch("experience_reader.get_lessons_for_task", return_value=""),
            patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="abc123")),
        ]

        # Create run dir for directive write
        (tmp_path / "runs" / "test").mkdir(parents=True, exist_ok=True)

        with _apply_patches(patches):
            main._cmd_cycle_inner(Namespace(), manifest)

        # FSM should end at ready
        assert manifest["fsm_state"] == "ready"
        assert manifest["last_verdict"] is None
        assert manifest["retry_count"] == 0

        # Directive should have been written
        assert (tmp_path / "directive.md").exists()

        output = capsys.readouterr().out
        assert "risk=LOW" in output
        assert "Experience: verdict=PASS" in output


# ---------------------------------------------------------------------------
# Test 2: SEMI with consensus
# ---------------------------------------------------------------------------

class TestSemiConsensusPath:
    """SEMI risk with consensus gate requiring 2 passes."""

    def test_semi_first_pass_triggers_consensus_retry(self, tmp_path, capsys):
        """First audit pass → consensus not met → retry scheduled."""
        import main

        manifest, paths = _setup_cycle(tmp_path)
        bundle = _mock_bundle()
        classification = _mock_classification("SEMI", "SEMI_AUDIT")
        advisor_result = _mock_advisor_result("SEMI", "SEMI_AUDIT")
        synth = _mock_synth("SEMI_AUDIT", "SEMI")
        exec_result = _mock_exec_result()
        packet = _mock_packet()
        gate = _mock_gate(True)
        acceptance = _mock_acceptance(True)
        audit_result = _mock_audit_result(passed=True)

        run_dir = tmp_path / "runs" / "test"
        run_dir.mkdir(parents=True, exist_ok=True)

        patches = _patch_paths(main, paths)
        patches += [
            patch.object(main, "_run_intake", return_value=bundle),
            patch.object(main, "_run_classify", return_value=classification),
            patch.object(main, "_run_advisor", return_value=advisor_result),
            patch.object(main, "_run_synthesizer", return_value=synth),
            patch.object(main, "_load_config", return_value={
                "auto_execute": True,  # need executor to run
                "executor_timeout_seconds": 60,
                "max_retries_semi": 3,
                "critique_consensus_required": True,
                "critique_min_approvals": 2,
            }),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            # Pre-exec SEMI audit passes
            patch("core_gate_bridge.decision_to_task_pack", return_value=MagicMock()),
            patch("core_gate_bridge.run_audit_sync", return_value=audit_result),
            patch("core_gate_bridge._determine_fsm_state", return_value="audit_passed"),
            patch("core_gate_bridge._determine_last_verdict", return_value="AUDIT_PASSED"),
            patch("core_gate_bridge.extract_critique_text", return_value="looks good"),
            # Post-exec
            patch("executor_bridge.run_with_collect", return_value=(exec_result, packet)),
            patch("batch_quality_gate.check_packet", return_value=gate),
            patch("acceptance_checker.check", return_value=acceptance),
            patch("experience_writer.write_execution_experience",
                  return_value={"overall_verdict": "PASS"}),
            # Post-exec audit
            patch("core_gate_bridge.run_post_execution_audit_sync", return_value=audit_result),
            patch("experience_reader.get_lessons_for_task", return_value=""),
            patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="abc123")),
        ]

        (run_dir / "directive.md").write_text("# test", encoding="utf-8")

        with _apply_patches(patches):
            main._cmd_cycle_inner(Namespace(), manifest)

        # First audit pass but consensus needs 2 → CONSENSUS_PENDING
        assert manifest["last_verdict"] == "CONSENSUS_PENDING"
        assert manifest["fsm_state"] == "awaiting_execution"
        assert manifest["retry_count"] == 1

        output = capsys.readouterr().out
        assert "CONSENSUS RETRY" in output


# ---------------------------------------------------------------------------
# Test 3: CORE gate block
# ---------------------------------------------------------------------------

class TestCoreGateBlock:
    """CORE risk → synth CORE_GATE → audit blocked."""

    def test_core_gate_blocks_on_audit_fail(self, tmp_path, capsys):
        import main

        manifest, paths = _setup_cycle(tmp_path)
        bundle = _mock_bundle()
        classification = _mock_classification("CORE", "CORE_GATE")
        advisor_result = _mock_advisor_result("CORE", "CORE_GATE")
        synth = _mock_synth("CORE_GATE", "CORE")
        audit_result = _mock_audit_result(passed=False, blocked=True)

        run_dir = tmp_path / "runs" / "test"
        run_dir.mkdir(parents=True, exist_ok=True)

        negotiate_result = {
            "converged": False,
            "proposal": "test proposal",
            "iterations": 3,
            "history": [{"attempt": 1, "verdict": "reject", "concerns": ["test"]}],
            "final_verdict": "reject",
            "auditor_verdicts": {"gemini": "reject"},
        }

        patches = _patch_paths(main, paths)
        patches += [
            patch.object(main, "_run_intake", return_value=bundle),
            patch.object(main, "_run_classify", return_value=classification),
            patch.object(main, "_run_advisor", return_value=advisor_result),
            patch.object(main, "_run_synthesizer", return_value=synth),
            patch.object(main, "_load_config", return_value={
                "auto_execute": False, "max_attempts": 3,
            }),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            patch("core_gate_bridge.decision_to_task_pack", return_value=MagicMock()),
            patch("core_gate_bridge.negotiate_architecture", return_value=negotiate_result),
        ]

        with _apply_patches(patches):
            main._cmd_cycle_inner(Namespace(), manifest)

        assert manifest["fsm_state"] == "blocked_by_consensus"
        assert manifest["last_verdict"] == "BLOCKED_BY_CONSENSUS"

        output = capsys.readouterr().out
        assert "CORE RISK" in output


# ---------------------------------------------------------------------------
# Test 4: Advisor escalation
# ---------------------------------------------------------------------------

class TestAdvisorEscalation:
    """Advisor escalation → awaiting_owner_reply."""

    def test_advisor_escalation(self, tmp_path, capsys):
        import main

        manifest, paths = _setup_cycle(tmp_path)
        bundle = _mock_bundle()
        classification = _mock_classification("SEMI")
        advisor_result = _mock_advisor_result(escalated=True)

        run_dir = tmp_path / "runs" / "test"
        run_dir.mkdir(parents=True, exist_ok=True)

        patches = _patch_paths(main, paths)
        patches += [
            patch.object(main, "_run_intake", return_value=bundle),
            patch.object(main, "_run_classify", return_value=classification),
            patch.object(main, "_run_advisor", return_value=advisor_result),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            patch("experience_writer.write_failure_experience", return_value=None),
        ]

        with _apply_patches(patches):
            main._cmd_cycle_inner(Namespace(), manifest)

        assert manifest["fsm_state"] == "awaiting_owner_reply"
        assert manifest["last_verdict"] == "ESCALATE"

        output = capsys.readouterr().out
        assert "ADVISOR ESCALATION" in output


# ---------------------------------------------------------------------------
# Test 5: Synth ESCALATE
# ---------------------------------------------------------------------------

class TestSynthEscalate:
    """Synthesizer blocks/escalates → awaiting_owner_reply."""

    def test_synth_escalate(self, tmp_path, capsys):
        import main

        manifest, paths = _setup_cycle(tmp_path)
        bundle = _mock_bundle()
        classification = _mock_classification("SEMI")
        advisor_result = _mock_advisor_result("SEMI")
        synth = _mock_synth("ESCALATE", "SEMI")
        synth.rationale = "too many attempts"

        run_dir = tmp_path / "runs" / "test"
        run_dir.mkdir(parents=True, exist_ok=True)

        patches = _patch_paths(main, paths)
        patches += [
            patch.object(main, "_run_intake", return_value=bundle),
            patch.object(main, "_run_classify", return_value=classification),
            patch.object(main, "_run_advisor", return_value=advisor_result),
            patch.object(main, "_run_synthesizer", return_value=synth),
            patch.object(main, "_load_config", return_value={"max_attempts": 3}),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            patch("experience_writer.write_failure_experience", return_value=None),
        ]

        with _apply_patches(patches):
            main._cmd_cycle_inner(Namespace(), manifest)

        assert manifest["fsm_state"] == "awaiting_owner_reply"
        assert manifest["last_verdict"] == "ESCALATE"

        output = capsys.readouterr().out
        assert "SYNTHESIZER: ESCALATE" in output


# ---------------------------------------------------------------------------
# Test 6: Executor failure
# ---------------------------------------------------------------------------

class TestExecutorFailure:
    """Executor fails → error state."""

    def test_executor_crash_goes_to_error(self, tmp_path, capsys):
        import main

        manifest, paths = _setup_cycle(tmp_path)
        bundle = _mock_bundle()
        classification = _mock_classification("LOW")
        advisor_result = _mock_advisor_result("LOW")
        synth = _mock_synth("PROCEED", "LOW")
        exec_result = _mock_exec_result(status="failed", exit_code=1)

        run_dir = tmp_path / "runs" / "test"
        run_dir.mkdir(parents=True, exist_ok=True)

        patches = _patch_paths(main, paths)
        patches += [
            patch.object(main, "_run_intake", return_value=bundle),
            patch.object(main, "_run_classify", return_value=classification),
            patch.object(main, "_run_advisor", return_value=advisor_result),
            patch.object(main, "_run_synthesizer", return_value=synth),
            patch.object(main, "_load_config", return_value={
                "auto_execute": True, "executor_timeout_seconds": 60,
            }),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            patch("executor_bridge.run_with_collect", return_value=(exec_result, None)),
            patch("experience_writer.write_failure_experience", return_value=None),
            patch("experience_reader.get_lessons_for_task", return_value=""),
            patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="abc123")),
        ]

        with _apply_patches(patches):
            main._cmd_cycle_inner(Namespace(), manifest)

        assert manifest["fsm_state"] == "error"
        assert manifest["last_verdict"] == "EXECUTOR_FAILED"

        output = capsys.readouterr().out
        assert "EXECUTOR FAILED" in output


# ---------------------------------------------------------------------------
# Test 7: Collect failure (executor OK but packet None)
# ---------------------------------------------------------------------------

class TestCollectFailure:
    """Executor succeeds but packet collection returns None → error."""

    def test_collect_failure(self, tmp_path, capsys):
        import main

        manifest, paths = _setup_cycle(tmp_path)
        bundle = _mock_bundle()
        classification = _mock_classification("LOW")
        advisor_result = _mock_advisor_result("LOW")
        synth = _mock_synth("PROCEED", "LOW")
        exec_result = _mock_exec_result(status="completed", exit_code=0)

        run_dir = tmp_path / "runs" / "test"
        run_dir.mkdir(parents=True, exist_ok=True)

        patches = _patch_paths(main, paths)
        patches += [
            patch.object(main, "_run_intake", return_value=bundle),
            patch.object(main, "_run_classify", return_value=classification),
            patch.object(main, "_run_advisor", return_value=advisor_result),
            patch.object(main, "_run_synthesizer", return_value=synth),
            patch.object(main, "_load_config", return_value={
                "auto_execute": True, "executor_timeout_seconds": 60,
            }),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            # Executor OK but packet is None
            patch("executor_bridge.run_with_collect", return_value=(exec_result, None)),
            patch("experience_writer.write_failure_experience", return_value=None),
            patch("experience_reader.get_lessons_for_task", return_value=""),
            patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="abc123")),
        ]

        with _apply_patches(patches):
            main._cmd_cycle_inner(Namespace(), manifest)

        assert manifest["fsm_state"] == "error"
        assert manifest["last_verdict"] == "COLLECT_FAILED"

        output = capsys.readouterr().out
        assert "COLLECT FAILED" in output


# ---------------------------------------------------------------------------
# Test 8: Batch gate failure
# ---------------------------------------------------------------------------

class TestBatchGateFailure:
    """Batch gate fails → awaiting_owner_reply."""

    def test_gate_fail_escalates(self, tmp_path, capsys):
        import main

        manifest, paths = _setup_cycle(tmp_path)
        bundle = _mock_bundle()
        classification = _mock_classification("LOW")
        advisor_result = _mock_advisor_result("LOW")
        synth = _mock_synth("PROCEED", "LOW")
        exec_result = _mock_exec_result()
        packet = _mock_packet()
        gate = _mock_gate(passed=False)
        acceptance = _mock_acceptance(True)

        run_dir = tmp_path / "runs" / "test"
        run_dir.mkdir(parents=True, exist_ok=True)

        patches = _patch_paths(main, paths)
        patches += [
            patch.object(main, "_run_intake", return_value=bundle),
            patch.object(main, "_run_classify", return_value=classification),
            patch.object(main, "_run_advisor", return_value=advisor_result),
            patch.object(main, "_run_synthesizer", return_value=synth),
            patch.object(main, "_load_config", return_value={
                "auto_execute": True, "executor_timeout_seconds": 60,
            }),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            patch("executor_bridge.run_with_collect", return_value=(exec_result, packet)),
            patch("batch_quality_gate.check_packet", return_value=gate),
            patch("acceptance_checker.check", return_value=acceptance),
            patch("experience_writer.write_execution_experience",
                  return_value={"overall_verdict": "PASS"}),
            patch("experience_reader.get_lessons_for_task", return_value=""),
            patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="abc123")),
        ]

        with _apply_patches(patches):
            main._cmd_cycle_inner(Namespace(), manifest)

        assert manifest["fsm_state"] == "awaiting_owner_reply"
        assert manifest["last_verdict"] == "BATCH_GATE_FAILED"

        output = capsys.readouterr().out
        assert "BATCH GATE FAILED" in output


# ---------------------------------------------------------------------------
# Test 9: cmd_cycle FSM entry guards
# ---------------------------------------------------------------------------

class TestCmdCycleFsmGuards:
    """cmd_cycle correctly handles parked states without running pipeline."""

    @pytest.mark.parametrize("state,expected_msg", [
        ("completed", "Task completed"),
        ("error", "In error state"),
        ("awaiting_owner_reply", "Awaiting owner reply"),
        ("blocked", "Blocked by auditor"),
        ("audit_in_progress", "Audit in progress"),
    ])
    def test_parked_states_exit_early(self, tmp_path, capsys, state, expected_msg):
        import main

        manifest = {
            "fsm_state": state,
            "current_task_id": "test",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        lock_path = tmp_path / "lock"
        runs_path = tmp_path / "runs.jsonl"

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "LOCK_PATH", lock_path), \
             patch.object(main, "RUNS_PATH", runs_path):
            main.cmd_cycle(Namespace())

        output = capsys.readouterr().out
        assert expected_msg in output


# ---------------------------------------------------------------------------
# Test 10: Experience lessons injected into directive
# ---------------------------------------------------------------------------

class TestExperienceInjection:
    """P5 experience lessons are injected into directive."""

    def test_lessons_appear_in_directive(self, tmp_path):
        import main

        manifest, paths = _setup_cycle(tmp_path)
        bundle = _mock_bundle()
        classification = _mock_classification("LOW")
        advisor_result = _mock_advisor_result("LOW")
        synth = _mock_synth("PROCEED", "LOW")

        run_dir = tmp_path / "runs" / "test"
        run_dir.mkdir(parents=True, exist_ok=True)

        lesson_text = "## Lessons from Past Runs\n- Watch for scope drift"

        patches = _patch_paths(main, paths)
        patches += [
            patch.object(main, "_run_intake", return_value=bundle),
            patch.object(main, "_run_classify", return_value=classification),
            patch.object(main, "_run_advisor", return_value=advisor_result),
            patch.object(main, "_run_synthesizer", return_value=synth),
            patch.object(main, "_load_config", return_value={
                "auto_execute": False, "max_attempts": 3,
            }),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            patch("experience_reader.get_lessons_for_task", return_value=lesson_text),
        ]

        with _apply_patches(patches):
            main._cmd_cycle_inner(Namespace(), manifest)

        directive = (tmp_path / "directive.md").read_text(encoding="utf-8")
        assert "Lessons from Past Runs" in directive
        assert "Watch for scope drift" in directive


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _apply_patches:
    """Context manager that applies a list of patch context managers."""

    def __init__(self, patches):
        self.patches = patches
        self.started = []

    def __enter__(self):
        for p in self.patches:
            self.started.append(p.__enter__())
        return self.started

    def __exit__(self, *args):
        for p in reversed(self.patches):
            p.__exit__(*args)
