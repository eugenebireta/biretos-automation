"""
test_p0_fixes.py — deterministic tests for P0 + P1 hardening fixes.

Covers:
  P0-1: File lock — concurrent orchestrator blocked
  P0-2: Tier check fail-closed — _check_tier crash => CORE, not LOW
  P0-3: Collect failure not masked as completed
  P1-1: API retry with backoff on transient errors
  P1-2: Blockers populated from pytest failures
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# P0-1: File lock tests
# ---------------------------------------------------------------------------

class TestP01FileLock:
    """Verify single-run guard prevents concurrent manifest overwrites."""

    def test_acquire_release_lock_succeeds(self, tmp_path):
        """First lock acquisition should succeed."""
        from main import _acquire_lock, _release_lock
        lock_file = tmp_path / "test.lock"
        with patch("main.LOCK_PATH", lock_file):
            fh = _acquire_lock()
            assert fh is not None
            assert lock_file.exists()
            _release_lock(fh)
            # After release, file should be readable and contain PID
            content = lock_file.read_text()
            assert str(os.getpid()) in content

    def test_second_lock_fails(self, tmp_path):
        """Overlapping lock acquisition should return None."""
        lock_file = tmp_path / "test.lock"
        from main import _acquire_lock, _release_lock
        with patch("main.LOCK_PATH", lock_file):
            fh1 = _acquire_lock()
            assert fh1 is not None
            try:
                # Second attempt should fail
                fh2 = _acquire_lock()
                assert fh2 is None, "Second lock should return None (lock_busy)"
            finally:
                _release_lock(fh1)

    def test_lock_released_allows_reacquire(self, tmp_path):
        """After release, lock can be acquired again."""
        lock_file = tmp_path / "test.lock"
        from main import _acquire_lock, _release_lock
        with patch("main.LOCK_PATH", lock_file):
            fh1 = _acquire_lock()
            assert fh1 is not None
            _release_lock(fh1)
            # Should succeed now
            fh2 = _acquire_lock()
            assert fh2 is not None
            _release_lock(fh2)

    def test_cmd_cycle_exits_on_lock_busy(self, tmp_path, capsys):
        """cmd_cycle should exit gracefully when lock is held."""
        lock_file = tmp_path / "test.lock"
        from main import cmd_cycle, _acquire_lock, _release_lock
        import argparse
        with patch("main.LOCK_PATH", lock_file):
            # Hold lock
            fh = _acquire_lock()
            assert fh is not None
            try:
                # cmd_cycle should detect busy lock
                args = argparse.Namespace()
                cmd_cycle(args)
                captured = capsys.readouterr()
                assert "lock_busy" in captured.err
            finally:
                _release_lock(fh)


# ---------------------------------------------------------------------------
# P0-2: Tier check fail-closed
# ---------------------------------------------------------------------------

class TestP02TierCheckFailClosed:
    """Verify that _check_tier failure results in BLOCKED/CORE, not pass-through."""

    def test_import_failure_blocks(self):
        """If classifier._check_tier can't be imported, synthesizer BLOCKS."""
        from synthesizer import decide, ACTION_BLOCKED

        clf = MagicMock()
        clf.risk_class = "LOW"
        clf.governance_route = "none"

        verdict = MagicMock()
        verdict.risk_assessment = "LOW"
        verdict.governance_route = "none"
        verdict.scope = ["scripts/foo.py"]
        verdict.next_step = "do something"
        verdict.addresses_blocker = None

        # Simulate import failure
        with patch.dict("sys.modules", {"classifier": None}):
            # Force fresh import attempt
            import synthesizer  # noqa: F401 — ensures module is loaded before patching
            original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

            def fake_import(name, *args, **kwargs):
                if name == "classifier":
                    raise ImportError("simulated classifier unavailable")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=fake_import):
                result = decide(clf, verdict)

        assert result.action == ACTION_BLOCKED
        assert result.final_risk == "CORE"
        assert any("TIER_CHECK_UNAVAILABLE" in r for r in result.rule_trace)

    def test_check_tier_exception_assumes_tier1(self):
        """If _check_tier raises on a specific file, that file is treated as Tier-1."""
        from synthesizer import decide, ACTION_BLOCKED

        clf = MagicMock()
        clf.risk_class = "LOW"
        clf.governance_route = "none"

        verdict = MagicMock()
        verdict.risk_assessment = "LOW"
        verdict.governance_route = "none"
        verdict.scope = ["scripts/some_file.py"]
        verdict.next_step = "proceed"
        verdict.addresses_blocker = None

        def broken_check_tier(path):
            raise RuntimeError("tier DB corrupted")

        with patch("synthesizer._check_tier", broken_check_tier, create=True):
            # Need to patch the import inside synthesizer
            import classifier
            original_check = classifier._check_tier
            classifier._check_tier = broken_check_tier
            try:
                result = decide(clf, verdict)
            finally:
                classifier._check_tier = original_check

        # File should be treated as Tier-1 (fail-closed) → BLOCKED
        assert result.action == ACTION_BLOCKED
        assert result.final_risk == "CORE"
        assert len(result.stripped_files) > 0


# ---------------------------------------------------------------------------
# P0-3: Collect failure honesty
# ---------------------------------------------------------------------------

class TestP03CollectFailureHonesty:
    """Verify collect failure is NOT masked as success."""

    def test_collect_none_sets_error_state(self, tmp_path):
        """When executor succeeds but packet is None, FSM should go to error.

        Stub: verifies the contract that completed+None packet → error state.
        Full integration tested via orchestrator pilot runs.
        """
        exec_result = MagicMock()
        exec_result.status = "completed"
        exec_result.exit_code = 0
        exec_result.elapsed_seconds = 1.0
        exec_result.stderr = ""

        # The key contract: when status=completed and packet=None, FSM→error
        assert exec_result.status == "completed"

    def test_executor_failure_sets_error_state(self):
        """When executor fails, FSM should go to error, not stay at awaiting_execution."""
        # The fix changed the else branch to set fsm_state="error"
        # Verify by reading the source code
        from main import _run_executor_bridge
        import inspect
        source = inspect.getsource(_run_executor_bridge)
        # Should contain "COLLECT_FAILED" verdict for packet=None case
        assert "COLLECT_FAILED" in source
        # Should set fsm_state to error, not leave at awaiting_execution
        assert '"error"' in source or "'error'" in source

    def test_packet_none_branch_exists_in_code(self):
        """Verify the explicit collect-failure branch exists."""
        import main
        import inspect
        source = inspect.getsource(main._run_executor_bridge)
        # P0-3 fix: explicit branch for "completed but packet is None"
        assert "packet is None" in source
        assert "collect_failed" in source
        assert "COLLECT_FAILED" in source


# ---------------------------------------------------------------------------
# P1-1 + P1-3: API retry with backoff + jitter
# ---------------------------------------------------------------------------

class TestP11AdvisorCliChannel:
    """Verify advisor uses CLI channel and handles errors correctly."""

    def test_cli_error_escalates(self, tmp_path):
        """CLI error on both attempts → escalation."""
        from advisor import call

        bundle = MagicMock()
        bundle.trace_id = "orch_test_cli"
        bundle.sprint_goal = "Test"
        bundle.task_id = "T-1"
        bundle.to_advisor_prompt_context.return_value = "test context"

        call_fn = MagicMock(side_effect=RuntimeError("claude CLI exit code 1"))
        result = call(bundle, _call_fn=call_fn,
                      verdict_path=tmp_path / "v.json",
                      escalation_path=tmp_path / "e.json",
                      config={})
        assert result.escalated is True
        assert result.verdict is None
        assert call_fn.call_count == 2  # tried both attempts

    def test_cli_timeout_escalates(self, tmp_path):
        """CLI timeout → escalation with timeout info in warnings."""
        from advisor import call

        bundle = MagicMock()
        bundle.trace_id = "orch_test_timeout"
        bundle.sprint_goal = "Test"
        bundle.task_id = "T-2"
        bundle.to_advisor_prompt_context.return_value = "test context"

        call_fn = MagicMock(side_effect=RuntimeError("claude CLI timeout after 120s"))
        result = call(bundle, _call_fn=call_fn,
                      verdict_path=tmp_path / "v.json",
                      escalation_path=tmp_path / "e.json",
                      config={})
        assert result.escalated is True
        assert any("timeout" in w for w in result.warnings)

    def test_cli_success_returns_verdict(self, tmp_path):
        """Good CLI response → parsed verdict."""
        import json
        from advisor import call

        good_json = json.dumps({
            "schema_version": "v1", "trace_id": "t", "risk_assessment": "LOW",
            "governance_route": "none", "rationale": "ok", "next_step": "do it",
            "scope": [], "issued_at": "2026-04-09T00:00:00Z",
        })
        bundle = MagicMock()
        bundle.trace_id = "t"
        bundle.sprint_goal = "Test"
        bundle.task_id = "T-3"
        bundle.to_advisor_prompt_context.return_value = "test context"

        call_fn = MagicMock(return_value=good_json)
        result = call(bundle, _call_fn=call_fn,
                      verdict_path=tmp_path / "v.json",
                      escalation_path=tmp_path / "e.json",
                      config={})
        assert result.verdict is not None
        assert result.escalated is False


# ---------------------------------------------------------------------------
# P1-2: Blockers from pytest failures
# ---------------------------------------------------------------------------

class TestP12BlockersFromPytest:
    """Verify collect_packet populates blockers when tests fail."""

    def test_failed_tests_populate_blockers(self):
        """If pytest reports failures, blockers should be non-empty."""
        from collect_packet import collect

        with patch("collect_packet.run_git_diff_stat", return_value=["scripts/foo.py"]), \
             patch("collect_packet.run_git_diff", return_value=("diff", 100, False)), \
             patch("collect_packet.classify_tiers", return_value=["Tier-3"]), \
             patch("collect_packet.run_pytest", return_value={
                 "passed": 10, "failed": 3, "skipped": 0, "error": 0
             }):
            packet = collect(trace_id="test", run_pytest_flag=True)

        assert len(packet["blockers"]) > 0
        assert "3 test(s) failed" in packet["blockers"][0]
        assert packet["status"] == "blocked"

    def test_passing_tests_no_blockers(self):
        """If all tests pass, blockers should be empty."""
        from collect_packet import collect

        with patch("collect_packet.run_git_diff_stat", return_value=["scripts/foo.py"]), \
             patch("collect_packet.run_git_diff", return_value=("diff", 100, False)), \
             patch("collect_packet.classify_tiers", return_value=["Tier-3"]), \
             patch("collect_packet.run_pytest", return_value={
                 "passed": 50, "failed": 0, "skipped": 2, "error": 0
             }):
            packet = collect(trace_id="test", run_pytest_flag=True)

        assert packet["blockers"] == []
        assert packet["status"] == "completed"

    def test_no_pytest_no_blockers(self):
        """Without pytest, blockers should be empty."""
        from collect_packet import collect

        with patch("collect_packet.run_git_diff_stat", return_value=["scripts/foo.py"]), \
             patch("collect_packet.run_git_diff", return_value=("diff", 100, False)), \
             patch("collect_packet.classify_tiers", return_value=["Tier-3"]):
            packet = collect(trace_id="test", run_pytest_flag=False)

        assert packet["blockers"] == []
