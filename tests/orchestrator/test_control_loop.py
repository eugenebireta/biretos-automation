"""Tests for the closed control loop in main.py _run_executor_bridge.

Verifies that after executor completes:
1. Acceptance checker runs
2. Experience record is written with trace_id
3. Runs.jsonl entry has proper status field
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "orchestrator"))


@dataclass
class FakeExecResult:
    trace_id: str = "orch_test_loop_001"
    status: str = "completed"
    exit_code: int = 0
    stdout: str = "done"
    stderr: str = ""
    elapsed_seconds: float = 10.0
    directive_path: str = "orchestrator/orchestrator_directive.md"
    error_class: str = None
    severity: str = None
    retriable: bool = None


SAMPLE_DIRECTIVE = """\
# Orchestrator Directive
trace_id: orch_test_loop_001

## Scope (Tier-3 verified)
- scripts/foo.py
- tests/test_foo.py

## Acceptance Criteria
- All tests pass
"""

SAMPLE_PACKET = {
    "schema_version": "v1",
    "trace_id": "orch_test_loop_001",
    "status": "completed",
    "changed_files": ["scripts/foo.py", "tests/test_foo.py"],
    "affected_tiers": ["Tier-3"],
    "test_results": {"passed": 50, "failed": 0},
    "blockers": [],
}


class TestControlLoopSuccess:
    """Test the happy path: executor completes, gate passes, acceptance passes."""

    def test_experience_written_on_success(self, tmp_path):
        import main
        import experience_writer as ew

        exp_log = tmp_path / "exp.jsonl"
        runs_log = tmp_path / "runs.jsonl"

        manifest = {
            "fsm_state": "awaiting_execution",
            "current_task_id": "TEST-TASK",
            "_last_risk_class": "LOW",
            "trace_id": "orch_test_loop_001",
            "attempt_count": 1,
        }

        # Mock executor_bridge.run_with_collect
        mock_eb = MagicMock()
        mock_eb.run_with_collect.return_value = (FakeExecResult(), SAMPLE_PACKET)

        # Mock batch_quality_gate
        mock_bqg = MagicMock()
        gate_result = MagicMock()
        gate_result.passed = True
        gate_result.rule = "G6:PASS"
        gate_result.auto_merge_eligible = True
        gate_result.reason = "all checks passed"
        mock_bqg.check_packet.return_value = gate_result

        directive_path = tmp_path / "directive.md"
        directive_path.write_text(SAMPLE_DIRECTIVE, encoding="utf-8")

        saved_manifests = []
        saved_runs = []

        def mock_save(m):
            saved_manifests.append(dict(m))

        def mock_append_run(entry):
            saved_runs.append(entry)

        with patch.object(ew, "_log_path", return_value=exp_log), \
             patch.dict("sys.modules", {
                 "executor_bridge": mock_eb,
                 "batch_quality_gate": mock_bqg,
             }), \
             patch.object(main, "DIRECTIVE_PATH", directive_path), \
             patch.object(main, "PACKET_PATH", tmp_path / "packet.json"), \
             patch.object(main, "save_manifest", mock_save), \
             patch.object(main, "append_run", mock_append_run), \
             patch.object(main, "ROOT", tmp_path):

            main._run_executor_bridge(manifest, "orch_test_loop_001", {})

        # Experience log written
        assert exp_log.exists()
        lines = exp_log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["trace_id"] == "orch_test_loop_001"
        assert record["overall_verdict"] == "PASS"
        assert record["acceptance_passed"] is True
        assert record["drift_detected"] is False
        assert record["task_id"] == "TEST-TASK"

        # Runs entry has status
        assert len(saved_runs) == 1
        assert saved_runs[0]["status"] == "pass"
        assert saved_runs[0]["acceptance_passed"] is True


class TestControlLoopDrift:
    """Test when executor touches out-of-scope files."""

    def test_drift_detected_in_experience(self, tmp_path):
        import main
        import experience_writer as ew

        exp_log = tmp_path / "exp.jsonl"

        manifest = {
            "fsm_state": "awaiting_execution",
            "current_task_id": "DRIFT-TASK",
            "_last_risk_class": "LOW",
            "trace_id": "orch_drift_001",
            "attempt_count": 1,
        }

        drift_packet = dict(SAMPLE_PACKET)
        drift_packet["changed_files"] = ["scripts/foo.py", "scripts/UNRELATED.py"]
        drift_packet["trace_id"] = "orch_drift_001"

        mock_eb = MagicMock()
        exec_result = FakeExecResult(trace_id="orch_drift_001")
        mock_eb.run_with_collect.return_value = (exec_result, drift_packet)

        mock_bqg = MagicMock()
        gate_result = MagicMock()
        gate_result.passed = True
        gate_result.rule = "G6:PASS"
        gate_result.auto_merge_eligible = True
        mock_bqg.check_packet.return_value = gate_result

        directive_path = tmp_path / "directive.md"
        directive_path.write_text(SAMPLE_DIRECTIVE, encoding="utf-8")

        saved_runs = []

        with patch.object(ew, "_log_path", return_value=exp_log), \
             patch.dict("sys.modules", {
                 "executor_bridge": mock_eb,
                 "batch_quality_gate": mock_bqg,
             }), \
             patch.object(main, "DIRECTIVE_PATH", directive_path), \
             patch.object(main, "PACKET_PATH", tmp_path / "packet.json"), \
             patch.object(main, "save_manifest", lambda m: None), \
             patch.object(main, "append_run", lambda e: saved_runs.append(e)), \
             patch.object(main, "ROOT", tmp_path):

            main._run_executor_bridge(manifest, "orch_drift_001", {})

        record = json.loads(exp_log.read_text(encoding="utf-8").strip())
        assert record["overall_verdict"] == "ACCEPTANCE_FAILED"
        assert record["drift_detected"] is True
        assert "scripts/UNRELATED.py" in record["out_of_scope_files"]

        # Runs entry reflects acceptance failure
        assert saved_runs[0]["status"] == "acceptance_failed"
        assert saved_runs[0]["drift_detected"] is True


class TestB10RevertStagedFiles:
    """B10 fix: staged new files from executor must be removed after revert.

    Before fix: git reset --soft left new files staged; git checkout/clean
    did not remove them. Fix adds git restore --staged before clean.
    Verified manually 2026-04-09: after fix, staged executor files are gone
    after _revert_to_base (HEAD restored, files off disk, git status clean).
    """

    def test_revert_early_return_when_head_equals_base(self, tmp_path):
        """_revert_to_base returns True immediately when HEAD == base_commit."""
        import subprocess
        import main

        base = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=str(
                Path(__file__).resolve().parent.parent.parent
            )
        ).strip()
        # When base == HEAD, nothing to revert — should return True without error
        result = main._revert_to_base(base, "test-early-return")
        assert result is True

    def test_revert_sequence_includes_restore_staged(self, tmp_path):
        """_revert_to_base source must call git restore --staged before git clean.

        This is the B10 fix: restore --staged unstages executor new files so
        git clean can remove them from disk.
        """
        from pathlib import Path as _Path
        src_path = _Path(__file__).resolve().parent.parent.parent / "orchestrator" / "main.py"
        source = src_path.read_text(encoding="utf-8")
        func_start = source.index("def _revert_to_base(")
        func_end = source.index("\ndef ", func_start + 1)
        func_src = source[func_start:func_end]

        assert '"git", "restore"' in func_src and '"--staged"' in func_src, (
            "B10 fix missing: _revert_to_base must call 'git restore --staged' "
            "to unstage new executor files before git clean removes them"
        )
        restore_pos = func_src.index('"git", "restore"')
        clean_pos = func_src.index('"git", "clean"')
        assert restore_pos < clean_pos, (
            "git restore --staged must appear before git clean in _revert_to_base"
        )


class TestControlLoopExecutorFailed:
    """Test when executor itself fails."""

    def test_failure_experience_written(self, tmp_path):
        import main
        import experience_writer as ew

        exp_log = tmp_path / "exp.jsonl"

        manifest = {
            "fsm_state": "awaiting_execution",
            "current_task_id": "FAIL-TASK",
            "_last_risk_class": "SEMI",
            "trace_id": "orch_fail_001",
            "attempt_count": 1,
        }

        failed_result = FakeExecResult(
            trace_id="orch_fail_001",
            status="timeout",
            exit_code=-1,
            stderr="TimeoutExpired",
            error_class="TRANSIENT",
        )

        mock_eb = MagicMock()
        mock_eb.run_with_collect.return_value = (failed_result, None)

        saved_runs = []

        with patch.object(ew, "_log_path", return_value=exp_log), \
             patch.dict("sys.modules", {"executor_bridge": mock_eb}), \
             patch.object(main, "DIRECTIVE_PATH", tmp_path / "directive.md"), \
             patch.object(main, "PACKET_PATH", tmp_path / "packet.json"), \
             patch.object(main, "save_manifest", lambda m: None), \
             patch.object(main, "append_run", lambda e: saved_runs.append(e)), \
             patch.object(main, "ROOT", tmp_path):

            main._run_executor_bridge(manifest, "orch_fail_001", {})

        record = json.loads(exp_log.read_text(encoding="utf-8").strip())
        assert record["trace_id"] == "orch_fail_001"
        assert record["overall_verdict"] == "EARLY_FAILURE"
        assert record["failure_stage"] == "executor"

        assert saved_runs[0]["status"] == "executor_failed"
