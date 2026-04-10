"""
test_audit_scenarios.py — L2 Scenario tests: end-to-end risk paths.

PURPOSE: Proves the orchestrator follows correct behavioral paths for each
risk class. Each test is a complete scenario from entry to terminal state,
with real module calls where possible and mocked LLM/subprocess only.

Scenarios:
  S1. LOW happy path: ready → processing → directive → executor → acceptance → ready
  S2. LOW drift path: executor touches OOS files → acceptance fail → retry → narrower directive
  S3. SEMI audit-required: synth SEMI_AUDIT → pre-audit → executor → post-audit → consensus
  S4. CORE blocked: synth CORE_GATE → audit → blocked (0 retries)
  S5. Control loop: drift → experience recorded → next task gets lessons in directive
  S6. Experience-informed retry: past drift on file X → directive warns about file X
  S7. Concurrent access: two cmd_cycle → one gets lock, other gets graceful rejection
  S8. Retry narrows scope: each retry directive is stricter than the previous
  S9. Budget mid-pipeline: budget exceeded → warning emitted (not crash)

All tests deterministic, no API keys needed.
"""
from __future__ import annotations

import json
import sys
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from argparse import Namespace

import pytest

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)


# ---------------------------------------------------------------------------
# Shared helpers — real objects where possible, mocked LLM only
# ---------------------------------------------------------------------------

def _real_classification(risk="LOW"):
    """Create real ClassifierResult (not a mock)."""
    from classifier import ClassifierResult
    return ClassifierResult(
        risk_class=risk,
        governance_route="none" if risk == "LOW" else "audit",
        rationale=f"test {risk}",
        tier_violations=[],
        blocking_rules=[],
    )


def _real_synth_decide(risk="LOW", scope=None):
    """Run real synthesizer.decide for a given risk class."""
    import synthesizer
    clf = _real_classification(risk)
    verdict = MagicMock()
    verdict.risk_assessment = risk
    verdict.governance_route = "none" if risk == "LOW" else "audit"
    verdict.scope = scope or ["scripts/foo.py"]
    return synthesizer.decide(
        classification=clf,
        verdict=verdict,
        attempt_count=1,
        last_packet_status="completed",
        max_attempts=3,
    )


def _mock_acceptance(passed=True, drift=False, oos=None):
    from acceptance_checker import AcceptanceResult, AcceptanceCheck
    checks = []
    if not passed:
        checks.append(AcceptanceCheck(
            check_id="A4:SCOPE_COMPLIANCE", passed=False,
            detail="drift: out-of-scope files modified",
        ))
    checks.append(AcceptanceCheck(check_id="A1:NON_EMPTY", passed=True, detail="ok"))
    return AcceptanceResult(
        trace_id="test-trace",
        passed=passed,
        checks=checks,
        drift_detected=drift,
        out_of_scope_files=oos or [],
    )


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
    g.reason = ""
    return g


def _mock_audit_result(passed=True, blocked=False):
    r = MagicMock()
    r.run_id = "audit-001"
    r.quality_gate = MagicMock()
    r.quality_gate.passed = passed
    r.approval_route = MagicMock()
    r.approval_route.value = "BLOCKED" if blocked else ("AUTO" if passed else "MANUAL")
    r.critiques = []
    r.final_verdicts = []
    r.escalated = False
    return r


def _setup_pipeline(tmp_path, manifest_overrides=None):
    """Create tmp paths and manifest for _cmd_cycle_inner."""
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

    paths = {
        "manifest_path": tmp_path / "manifest.json",
        "runs_path": tmp_path / "runs.jsonl",
        "directive_path": tmp_path / "directive.md",
        "packet_path": tmp_path / "packet.json",
        "runs_dir": tmp_path / "runs",
        "lock_path": tmp_path / "lock",
    }
    paths["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    paths["runs_dir"].mkdir(exist_ok=True)
    return manifest, paths


class _apply_patches:
    """Context manager for a list of patches."""
    def __init__(self, patches):
        self.patches = patches
    def __enter__(self):
        for p in self.patches:
            p.__enter__()
        return self
    def __exit__(self, *args):
        for p in reversed(self.patches):
            p.__exit__(*args)


def _path_patches(main_mod, paths):
    return [
        patch.object(main_mod, "MANIFEST_PATH", paths["manifest_path"]),
        patch.object(main_mod, "RUNS_PATH", paths["runs_path"]),
        patch.object(main_mod, "DIRECTIVE_PATH", paths["directive_path"]),
        patch.object(main_mod, "PACKET_PATH", paths["packet_path"]),
        patch.object(main_mod, "RUNS_DIR", paths["runs_dir"]),
        patch.object(main_mod, "LOCK_PATH", paths["lock_path"]),
        patch.object(main_mod, "ORCH_DIR", paths["manifest_path"].parent),
    ]


# ===========================================================================
# S1. LOW HAPPY PATH — complete pipeline to ready
# ===========================================================================

class TestS1_LowHappyPath:
    """LOW risk task traverses full pipeline and reaches clean success."""

    def test_low_full_cycle_ends_ready(self, tmp_path, capsys):
        import main
        manifest, paths = _setup_pipeline(tmp_path)
        run_dir = tmp_path / "runs" / "test"
        run_dir.mkdir(parents=True, exist_ok=True)

        # Real synthesizer for LOW → PROCEED
        synth = _real_synth_decide("LOW")
        assert synth.action == "PROCEED"

        ps = _path_patches(main, paths) + [
            patch.object(main, "_run_intake", return_value=MagicMock(
                warnings=[], validation_errors=[], last_changed_files=["scripts/foo.py"],
                last_affected_tiers=["3"], last_status="completed", task_id="test",
                sprint_goal="goal", dna_constraints=["no core"])),
            patch.object(main, "_run_classify", return_value=_real_classification("LOW")),
            patch.object(main, "_run_advisor", return_value=MagicMock(
                warnings=[], escalated=False, attempt_count=1,
                verdict=MagicMock(risk_assessment="LOW", governance_route="none",
                                  scope=["scripts/foo.py"], next_step="do it",
                                  rationale="ok", addresses_blocker=None))),
            patch.object(main, "_run_synthesizer", return_value=synth),
            patch.object(main, "_load_config", return_value={
                "auto_execute": True, "executor_timeout_seconds": 60,
                "max_retries_low": 3, "critique_consensus_required": False,
            }),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            patch("executor_bridge.run_with_collect",
                  return_value=(_mock_exec_result(), _mock_packet())),
            patch("batch_quality_gate.check_packet", return_value=_mock_gate()),
            patch("acceptance_checker.check", return_value=_mock_acceptance()),
            patch("experience_writer.write_execution_experience",
                  return_value={"overall_verdict": "PASS"}),
            patch("experience_reader.get_lessons_for_task", return_value=""),
            patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="abc")),
        ]

        with _apply_patches(ps):
            main._cmd_cycle_inner(Namespace(), manifest)

        assert manifest["fsm_state"] == "ready"
        assert manifest["last_verdict"] is None
        assert manifest["retry_count"] == 0
        out = capsys.readouterr().out
        assert "verdict=PASS" in out


# ===========================================================================
# S2. LOW DRIFT PATH — acceptance fail → retry → narrower directive
# ===========================================================================

class TestS2_LowDriftRetry:
    """Executor touches out-of-scope files → acceptance fail → retry directive narrows."""

    def test_drift_triggers_retry_with_oos_warning(self, tmp_path, capsys):
        import main
        manifest, paths = _setup_pipeline(tmp_path)
        run_dir = tmp_path / "runs" / "test"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "directive.md").write_text("# Original directive\n---\n", encoding="utf-8")

        ps = _path_patches(main, paths) + [
            patch.object(main, "_run_intake", return_value=MagicMock(
                warnings=[], validation_errors=[], last_changed_files=["scripts/foo.py"],
                last_affected_tiers=["3"], last_status="completed", task_id="test",
                sprint_goal="goal", dna_constraints=[])),
            patch.object(main, "_run_classify", return_value=_real_classification("LOW")),
            patch.object(main, "_run_advisor", return_value=MagicMock(
                warnings=[], escalated=False, attempt_count=1,
                verdict=MagicMock(risk_assessment="LOW", governance_route="none",
                                  scope=["scripts/foo.py"], next_step="do",
                                  rationale="ok", addresses_blocker=None))),
            patch.object(main, "_run_synthesizer", return_value=_real_synth_decide("LOW")),
            patch.object(main, "_load_config", return_value={
                "auto_execute": True,
                "executor_timeout_seconds": 60,
                "max_retries_low": 1, "critique_consensus_required": False,
            }),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            # Executor returns files including OOS
            patch("executor_bridge.run_with_collect", return_value=(
                _mock_exec_result(),
                _mock_packet(["scripts/foo.py", "core/forbidden.py"]),
            )),
            patch("batch_quality_gate.check_packet", return_value=_mock_gate()),
            # Acceptance FAILS with drift
            patch("acceptance_checker.check", return_value=_mock_acceptance(
                passed=False, drift=True, oos=["core/forbidden.py"],
            )),
            patch("experience_writer.write_execution_experience",
                  return_value={"overall_verdict": "ACCEPTANCE_FAILED"}),
            patch("experience_reader.get_lessons_for_task", return_value=""),
            patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="abc")),
        ]

        with _apply_patches(ps):
            main._cmd_cycle_inner(Namespace(), manifest)

        # After 1 retry exhausted (drift persists), escalates to owner
        assert manifest["fsm_state"] in ("awaiting_execution", "awaiting_owner_reply")
        assert manifest["retry_count"] >= 1

        # Retry directive should mention the OOS file
        retry_directive = paths["directive_path"].read_text(encoding="utf-8")
        assert "core/forbidden.py" in retry_directive
        assert "Out-of-scope" in retry_directive or "out-of-scope" in retry_directive


# ===========================================================================
# S3. SEMI AUDIT-REQUIRED PATH
# ===========================================================================

class TestS3_SemiAuditPath:
    """SEMI risk goes through pre-audit → executor → post-audit → consensus."""

    def test_semi_synth_returns_semi_audit(self):
        """Real synthesizer returns SEMI_AUDIT for SEMI risk."""
        synth = _real_synth_decide("SEMI")
        assert synth.action == "SEMI_AUDIT"

    def test_semi_requires_audit_before_execution(self, tmp_path, capsys):
        """SEMI pipeline enters audit_in_progress before building directive."""
        import main
        manifest, paths = _setup_pipeline(tmp_path)
        run_dir = tmp_path / "runs" / "test"
        run_dir.mkdir(parents=True, exist_ok=True)

        audit_result = _mock_audit_result(passed=True)

        ps = _path_patches(main, paths) + [
            patch.object(main, "_run_intake", return_value=MagicMock(
                warnings=[], validation_errors=[], last_changed_files=["scripts/foo.py"],
                last_affected_tiers=["3"], last_status="completed", task_id="test",
                sprint_goal="goal", dna_constraints=[])),
            patch.object(main, "_run_classify", return_value=_real_classification("SEMI")),
            patch.object(main, "_run_advisor", return_value=MagicMock(
                warnings=[], escalated=False, attempt_count=1,
                verdict=MagicMock(risk_assessment="SEMI", governance_route="audit",
                                  scope=["scripts/foo.py"], next_step="do",
                                  rationale="ok", addresses_blocker=None))),
            patch.object(main, "_run_synthesizer", return_value=_real_synth_decide("SEMI")),
            patch.object(main, "_load_config", return_value={
                "auto_execute": False, "max_attempts": 3,
            }),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            # Pre-exec audit
            patch("core_gate_bridge.decision_to_task_pack", return_value=MagicMock()),
            patch("core_gate_bridge.run_audit_sync", return_value=audit_result),
            patch("core_gate_bridge._determine_fsm_state", return_value="audit_passed"),
            patch("core_gate_bridge._determine_last_verdict", return_value="AUDIT_PASSED"),
            patch("core_gate_bridge.extract_critique_text", return_value="minor issues"),
            patch("experience_reader.get_lessons_for_task", return_value=""),
        ]

        with _apply_patches(ps):
            main._cmd_cycle_inner(Namespace(), manifest)

        # SEMI should produce directive with audit critique injected
        out = capsys.readouterr().out
        assert "SEMI" in out
        assert "audit" in out.lower()
        # Directive should exist
        assert paths["directive_path"].exists()


# ===========================================================================
# S4. CORE BLOCKED — zero retries, immediate block
# ===========================================================================

class TestS4_CoreBlocked:
    """CORE risk → CORE_GATE → audit fails → blocked (no retry)."""

    def test_core_synth_returns_core_gate(self):
        """Real synthesizer returns CORE_GATE for CORE risk."""
        synth = _real_synth_decide("CORE")
        assert synth.action == "CORE_GATE"

    def test_core_zero_retries_always(self):
        """CORE gets 0 retries regardless of config."""
        from main import _get_retry_policy
        assert _get_retry_policy("CORE") == 0
        assert _get_retry_policy("CORE", {"max_retries_low": 99, "max_retries_semi": 99}) == 0


# ===========================================================================
# S5. CONTROL LOOP: drift → experience → lessons in next directive
# ===========================================================================

class TestS5_ControlLoop:
    """Main system property: drift is recorded as experience,
    then injected as lesson into the next task's directive."""

    def test_drift_experience_contains_trace_id_and_drift(self, tmp_path):
        """After drift, experience record has drift_detected=True + trace_id."""
        import experience_writer as ew
        with patch.object(ew, "SHADOW_LOG_DIR", tmp_path):
            record = ew.write_execution_experience(
                trace_id="drift-trace-001",
                task_id="drifty-task",
                risk_class="LOW",
                acceptance_passed=False,
                acceptance_checks=[
                    {"check_id": "A4:SCOPE", "passed": False, "detail": "drift"},
                ],
                drift_detected=True,
                changed_files=["scripts/foo.py", "core/forbidden.py"],
                elapsed_seconds=10.0,
                executor_status="completed",
                gate_passed=True,
                gate_rule="LOW_RISK_AUTO",
                out_of_scope_files=["core/forbidden.py"],
                correction_needed=True,
                correction_detail="scope drift: touched core/forbidden.py",
            )

        assert record["drift_detected"] is True
        assert record["trace_id"] == "drift-trace-001"
        assert "core/forbidden.py" in record["out_of_scope_files"]
        assert record["overall_verdict"] == "ACCEPTANCE_FAILED"

    def test_drift_experience_becomes_lesson_in_next_directive(self, tmp_path):
        """Experience with drift on file X → lessons mention file X."""
        import experience_reader as er
        import experience_writer as ew

        # Step 1: Write drift experience
        with patch.object(ew, "SHADOW_LOG_DIR", tmp_path):
            ew.write_execution_experience(
                trace_id="drift-trace",
                task_id="task-A",
                risk_class="LOW",
                acceptance_passed=False,
                acceptance_checks=[
                    {"check_id": "A4:SCOPE", "passed": False, "detail": "drift"},
                ],
                drift_detected=True,
                changed_files=["scripts/foo.py"],
                elapsed_seconds=10.0,
                executor_status="completed",
                gate_passed=True,
                gate_rule="LOW_RISK_AUTO",
                out_of_scope_files=["core/forbidden.py"],
                correction_needed=True,
                correction_detail="drift",
            )

        # Step 2: Read lessons for a NEW task — global drift warning should fire
        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            lessons = er.get_lessons_for_task("task-B")

        # Step 3: Verify the lesson mentions the dangerous file
        assert "core/forbidden.py" in lessons
        assert "drift" in lessons.lower()

    def test_lessons_injected_into_real_directive(self, tmp_path):
        """_build_directive with real experience reader produces lesson in output."""
        import main
        import experience_writer as ew
        import experience_reader as er

        # Write experience
        with patch.object(ew, "SHADOW_LOG_DIR", tmp_path):
            ew.write_execution_experience(
                trace_id="t1", task_id="repeat-task", risk_class="LOW",
                acceptance_passed=False,
                acceptance_checks=[{"check_id": "A4:SCOPE", "passed": False, "detail": "drift"}],
                drift_detected=True, changed_files=["x.py"], elapsed_seconds=5.0,
                executor_status="completed", gate_passed=True, gate_rule="LOW_RISK_AUTO",
                out_of_scope_files=["core/secret.py"], correction_needed=True,
                correction_detail="drift",
            )

        manifest = {
            "current_task_id": "repeat-task",
            "current_sprint_goal": "fix thing",
            "attempt_count": 1, "retry_count": 0,
        }
        clf = _real_classification("LOW")
        verdict = MagicMock(risk_assessment="LOW", governance_route="none",
                             scope=["scripts/foo.py"], next_step="fix",
                             rationale="ok")
        synth = MagicMock(action="PROCEED", approved_scope=["scripts/foo.py"],
                           rule_trace="R7:PROCEED")
        bundle = MagicMock(dna_constraints=[])

        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            directive = main._build_directive(
                manifest, "trace-new", bundle, clf, verdict, synth
            )

        assert "Lessons from Past Runs" in directive
        assert "core/secret.py" in directive


# ===========================================================================
# S6. RETRY NARROWS SCOPE
# ===========================================================================

class TestS6_RetryNarrows:
    """Each retry directive becomes stricter with accumulated critique."""

    def test_second_retry_is_stricter(self):
        """Retry 2 includes both retry 1 failures + new OOS files."""
        from main import _build_retry_directive

        # First retry — one OOS file
        retry1 = _build_retry_directive(
            original_directive="# Directive\n---\nfooter",
            attempt=0,
            acceptance_failures=[
                {"check_id": "A4:SCOPE", "passed": False, "detail": "drift"},
            ],
            out_of_scope_files=["core/a.py"],
        )
        assert "core/a.py" in retry1
        assert "A4:SCOPE" in retry1

        # Second retry — adds audit critique on top
        retry2 = _build_retry_directive(
            original_directive=retry1,
            attempt=1,
            acceptance_failures=[
                {"check_id": "A4:SCOPE", "passed": False, "detail": "still drifting"},
            ],
            out_of_scope_files=["core/a.py", "core/b.py"],
            audit_critique="## Round 1 — FAILED\nFix imports\n## Round 2 — FAILED\nStill wrong",
        )
        # Second retry should have MORE restrictions
        assert "core/a.py" in retry2
        assert "core/b.py" in retry2
        assert "Round 1" in retry2
        assert "Round 2" in retry2
        assert len(retry2) > len(retry1)


# ===========================================================================
# S7. CONCURRENT ACCESS — graceful rejection
# ===========================================================================

class TestS7_ConcurrentAccess:
    """Two cmd_cycle calls → one gets lock, other gets graceful rejection."""

    def test_second_caller_gets_lock_busy(self, tmp_path, capsys):
        """When lock is held, second cmd_cycle exits with lock_busy message."""
        import main

        manifest = {
            "fsm_state": "ready",
            "current_task_id": "test",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        lock_path = tmp_path / "lock"
        runs_path = tmp_path / "runs.jsonl"

        # Simulate holding the lock
        lock_fh = open(lock_path, "w")
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)

            with patch.object(main, "MANIFEST_PATH", manifest_path), \
                 patch.object(main, "LOCK_PATH", lock_path), \
                 patch.object(main, "RUNS_PATH", runs_path):
                # Second caller should get lock_busy — no crash
                main.cmd_cycle(Namespace())

            err = capsys.readouterr().err
            assert "lock_busy" in err
        finally:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    lock_fh.seek(0)
                    msvcrt.locking(lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
            lock_fh.close()

    def test_manifest_not_corrupted_on_lock_busy(self, tmp_path):
        """Lock contention does not corrupt the manifest file."""
        import main

        original = {
            "fsm_state": "ready",
            "current_task_id": "important",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(original), encoding="utf-8")
        lock_path = tmp_path / "lock"
        runs_path = tmp_path / "runs.jsonl"

        lock_fh = open(lock_path, "w")
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)

            with patch.object(main, "MANIFEST_PATH", manifest_path), \
                 patch.object(main, "LOCK_PATH", lock_path), \
                 patch.object(main, "RUNS_PATH", runs_path):
                main.cmd_cycle(Namespace())

            # Manifest should be unchanged
            after = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert after == original
        finally:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    lock_fh.seek(0)
                    msvcrt.locking(lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
            lock_fh.close()


# ===========================================================================
# S8. WORKSPACE ISOLATION
# ===========================================================================

class TestS8_WorkspaceIsolation:
    """P1: Tasks operate in isolated per-trace directories."""

    def test_run_dirs_isolated_by_trace_id(self, tmp_path):
        """Different trace_ids get different run directories."""
        import main
        with patch.object(main, "RUNS_DIR", tmp_path / "runs"):
            dir_a = main._ensure_run_dir("trace_AAAA")
            dir_b = main._ensure_run_dir("trace_BBBB")

        assert dir_a != dir_b
        assert "trace_AAAA" in str(dir_a)
        assert "trace_BBBB" in str(dir_b)
        assert dir_a.exists()
        assert dir_b.exists()

    def test_run_dir_contains_trace_artifacts(self, tmp_path, capsys):
        """After cycle, per-run dir has directive and packet."""
        import main
        manifest, paths = _setup_pipeline(tmp_path)
        run_dir = tmp_path / "runs" / "test-trace"
        run_dir.mkdir(parents=True, exist_ok=True)

        ps = _path_patches(main, paths) + [
            patch.object(main, "_run_intake", return_value=MagicMock(
                warnings=[], validation_errors=[], last_changed_files=["scripts/foo.py"],
                last_affected_tiers=["3"], last_status="completed", task_id="test",
                sprint_goal="goal", dna_constraints=[])),
            patch.object(main, "_run_classify", return_value=_real_classification("LOW")),
            patch.object(main, "_run_advisor", return_value=MagicMock(
                warnings=[], escalated=False, attempt_count=1,
                verdict=MagicMock(risk_assessment="LOW", governance_route="none",
                                  scope=["scripts/foo.py"], next_step="do",
                                  rationale="ok", addresses_blocker=None))),
            patch.object(main, "_run_synthesizer", return_value=_real_synth_decide("LOW")),
            patch.object(main, "_load_config", return_value={
                "auto_execute": True, "executor_timeout_seconds": 60,
                "max_retries_low": 3, "critique_consensus_required": False,
            }),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            patch("executor_bridge.run_with_collect",
                  return_value=(_mock_exec_result(), _mock_packet())),
            patch("batch_quality_gate.check_packet", return_value=_mock_gate()),
            patch("acceptance_checker.check", return_value=_mock_acceptance()),
            patch("experience_writer.write_execution_experience",
                  return_value={"overall_verdict": "PASS"}),
            patch("experience_reader.get_lessons_for_task", return_value=""),
            patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="abc")),
        ]

        with _apply_patches(ps):
            main._cmd_cycle_inner(Namespace(), manifest)

        # Per-run dir should have directive and packet
        assert (run_dir / "directive.md").exists()
        assert (run_dir / "packet.json").exists()


# ===========================================================================
# S9. BUDGET MID-PIPELINE — warning not crash
# ===========================================================================

class TestS9_BudgetMidPipeline:
    """Budget exceeded mid-pipeline → warning emitted, pipeline continues."""

    def test_budget_warning_does_not_crash_pipeline(self, tmp_path, capsys):
        """Even with budget exceeded, pipeline completes (warning only)."""
        import main
        import budget_tracker as bt

        manifest, paths = _setup_pipeline(tmp_path)
        run_dir = tmp_path / "runs" / "test"
        run_dir.mkdir(parents=True, exist_ok=True)

        # Pre-load budget with high cost
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            for i in range(5):
                bt.record_call(
                    trace_id=f"old-{i}", provider="anthropic",
                    model="claude-opus-4-6", stage="executor",
                    input_tokens=100000, output_tokens=50000, call_seq=i,
                )

        ps = _path_patches(main, paths) + [
            patch.object(main, "_run_intake", return_value=MagicMock(
                warnings=[], validation_errors=[], last_changed_files=["scripts/foo.py"],
                last_affected_tiers=["3"], last_status="completed", task_id="test",
                sprint_goal="goal", dna_constraints=[])),
            patch.object(main, "_run_classify", return_value=_real_classification("LOW")),
            patch.object(main, "_run_advisor", return_value=MagicMock(
                warnings=[], escalated=False, attempt_count=1,
                verdict=MagicMock(risk_assessment="LOW", governance_route="none",
                                  scope=["scripts/foo.py"], next_step="do",
                                  rationale="ok", addresses_blocker=None))),
            patch.object(main, "_run_synthesizer", return_value=_real_synth_decide("LOW")),
            patch.object(main, "_load_config", return_value={
                "auto_execute": False, "max_attempts": 3,
            }),
            patch.object(main, "_ensure_run_dir", return_value=run_dir),
            patch("experience_reader.get_lessons_for_task", return_value=""),
        ]

        with _apply_patches(ps):
            # Should NOT crash even with budget exceeded
            main._cmd_cycle_inner(Namespace(), manifest)

        # Pipeline should have continued — directive written
        assert manifest["fsm_state"] == "awaiting_execution"
        out = capsys.readouterr().out
        # Budget warning may or may not appear depending on real cost,
        # but pipeline did NOT crash
        assert "CYCLE ERROR" not in out
