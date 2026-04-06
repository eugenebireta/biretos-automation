"""
test_executor_bridge.py — deterministic unit tests for orchestrator/executor_bridge.py

All tests are pure — no subprocess, no file I/O, no LLM.
subprocess.run is mocked; collect_packet.collect is mocked.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "orchestrator"))

import pytest
from executor_bridge import (
    run,
    run_with_collect,
    ExecutorResult,
    DEFAULT_TIMEOUT,
    DEFAULT_PERMISSION_MODE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(returncode=0, stdout="ok", stderr=""):
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def _fake_directive(tmp_path: Path) -> Path:
    d = tmp_path / "orchestrator_directive.md"
    d.write_text("# Directive\ntrace_id: test\n")
    return d


def _fake_packet(trace_id="orch_test"):
    return {
        "schema_version": "v1",
        "trace_id": trace_id,
        "status": "completed",
        "changed_files": ["scripts/foo.py"],
        "diff_summary": "1 file changed",
        "diff_char_count": 100,
        "diff_truncated": False,
        "test_results": None,
        "affected_tiers": ["Tier-3"],
        "executor_notes": None,
        "questions": [],
        "blockers": [],
        "artifacts_produced": [],
        "collected_by": "collect_packet.py",
        "collected_at": "2026-04-07T00:00:00+00:00",
        "base_commit": None,
    }


# ---------------------------------------------------------------------------
# ExecutorResult dataclass
# ---------------------------------------------------------------------------
class TestExecutorResultDataclass:
    def test_fields_present(self):
        r = ExecutorResult(
            trace_id="t1", status="completed", exit_code=0,
            stdout="out", stderr="", elapsed_seconds=1.0,
            directive_path="/tmp/dir.md"
        )
        assert r.trace_id == "t1"
        assert r.status == "completed"
        assert r.exit_code == 0
        assert r.stdout == "out"
        assert r.stderr == ""
        assert r.elapsed_seconds == 1.0
        assert r.directive_path == "/tmp/dir.md"
        assert r.error_class is None
        assert r.severity is None
        assert r.retriable is None

    def test_failure_fields(self):
        r = ExecutorResult(
            trace_id="t2", status="failed", exit_code=1,
            stdout="", stderr="err", elapsed_seconds=0.5,
            directive_path="/tmp/dir.md",
            error_class="TRANSIENT", severity="ERROR", retriable=True
        )
        assert r.error_class == "TRANSIENT"
        assert r.severity == "ERROR"
        assert r.retriable is True


# ---------------------------------------------------------------------------
# run() — subprocess success
# ---------------------------------------------------------------------------
class TestRunSuccess:
    def test_status_completed_on_exit_0(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0, "done")), \
             patch("builtins.open", mock_open(read_data="# directive")):
            result = run(directive, "orch_1")
        assert result.status == "completed"

    def test_exit_code_0(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0)), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.exit_code == 0

    def test_stdout_captured(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0, stdout="output text")), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.stdout == "output text"

    def test_trace_id_preserved(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0)), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_test_42")
        assert result.trace_id == "orch_test_42"

    def test_directive_path_in_result(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0)), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert str(directive) in result.directive_path

    def test_no_error_class_on_success(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0)), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.error_class is None
        assert result.severity is None
        assert result.retriable is None

    def test_elapsed_seconds_non_negative(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0)), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.elapsed_seconds >= 0.0

    def test_subprocess_called_with_print_flag(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_sp, \
             patch("builtins.open", mock_open(read_data="")):
            run(directive, "orch_1")
        cmd = mock_sp.call_args[0][0]
        assert "--print" in cmd

    def test_subprocess_called_with_permission_mode(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_sp, \
             patch("builtins.open", mock_open(read_data="")):
            run(directive, "orch_1", permission_mode="bypassPermissions")
        cmd = mock_sp.call_args[0][0]
        assert "--permission-mode" in cmd
        assert "bypassPermissions" in cmd

    def test_subprocess_called_with_no_session_persistence(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_sp, \
             patch("builtins.open", mock_open(read_data="")):
            run(directive, "orch_1")
        cmd = mock_sp.call_args[0][0]
        assert "--no-session-persistence" in cmd


# ---------------------------------------------------------------------------
# run() — subprocess failure
# ---------------------------------------------------------------------------
class TestRunFailure:
    def test_nonzero_exit_is_failed(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(1, stderr="err")), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.status == "failed"

    def test_nonzero_exit_code_preserved(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(2)), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.exit_code == 2

    def test_failure_error_class_transient(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(1)), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.error_class == "TRANSIENT"

    def test_failure_severity_error(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(1)), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.severity == "ERROR"

    def test_failure_retriable_true(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(1)), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.retriable is True


# ---------------------------------------------------------------------------
# run() — PERMANENT errors (permission + encoding)
# ---------------------------------------------------------------------------
class TestRunPermanentErrors:
    def test_permission_error_status(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("builtins.open", side_effect=PermissionError("denied")):
            result = run(directive, "orch_perm")
        assert result.status == "permission_denied"

    def test_permission_error_class_permanent(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("builtins.open", side_effect=PermissionError("denied")):
            result = run(directive, "orch_perm")
        assert result.error_class == "PERMANENT"

    def test_permission_error_not_retriable(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("builtins.open", side_effect=PermissionError("denied")):
            result = run(directive, "orch_perm")
        assert result.retriable is False

    def test_unicode_error_status(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("builtins.open", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "bad")):
            result = run(directive, "orch_enc")
        assert result.status == "encoding_error"

    def test_unicode_error_class_permanent(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("builtins.open", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "bad")):
            result = run(directive, "orch_enc")
        assert result.error_class == "PERMANENT"

    def test_unicode_error_not_retriable(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("builtins.open", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "bad")):
            result = run(directive, "orch_enc")
        assert result.retriable is False


# ---------------------------------------------------------------------------
# run() — timeout
# ---------------------------------------------------------------------------
class TestRunTimeout:
    def test_timeout_status(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=600)), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1", timeout=600)
        assert result.status == "timeout"

    def test_timeout_exit_code_minus_1(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=600)), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.exit_code == -1

    def test_timeout_error_class_transient(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=600)), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.error_class == "TRANSIENT"

    def test_timeout_retriable(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=600)), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.retriable is True


# ---------------------------------------------------------------------------
# run() — claude not found
# ---------------------------------------------------------------------------
class TestRunNotFound:
    def test_not_found_status(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", side_effect=FileNotFoundError("claude not found")), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.status == "not_found"

    def test_not_found_exit_code_minus_2(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", side_effect=FileNotFoundError()), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.exit_code == -2

    def test_not_found_error_class_permanent(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", side_effect=FileNotFoundError()), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.error_class == "PERMANENT"

    def test_not_found_not_retriable(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", side_effect=FileNotFoundError()), \
             patch("builtins.open", mock_open(read_data="")):
            result = run(directive, "orch_1")
        assert result.retriable is False


# ---------------------------------------------------------------------------
# run_with_collect() — success + collect
# ---------------------------------------------------------------------------
class TestRunWithCollect:
    def test_returns_tuple(self, tmp_path):
        directive = _fake_directive(tmp_path)
        mock_packet = _fake_packet("orch_wc1")
        with patch("subprocess.run", return_value=_make_proc(0)), \
             patch("builtins.open", mock_open(read_data="")), \
             patch("collect_packet.collect", return_value=mock_packet):
            out = run_with_collect(directive, "orch_wc1", packet_path=tmp_path / "pkt.json")
        assert isinstance(out, tuple)
        assert len(out) == 2

    def test_result_is_executor_result(self, tmp_path):
        directive = _fake_directive(tmp_path)
        mock_packet = _fake_packet("orch_wc1")
        with patch("subprocess.run", return_value=_make_proc(0)), \
             patch("builtins.open", mock_open(read_data="")), \
             patch("collect_packet.collect", return_value=mock_packet):
            result, _ = run_with_collect(directive, "orch_wc1", packet_path=tmp_path / "pkt.json")
        assert isinstance(result, ExecutorResult)

    def test_packet_returned_on_success(self, tmp_path):
        directive = _fake_directive(tmp_path)
        mock_packet = _fake_packet("orch_wc1")
        with patch("subprocess.run", return_value=_make_proc(0)), \
             patch("builtins.open", mock_open(read_data="")), \
             patch("collect_packet.collect", return_value=mock_packet):
            _, packet = run_with_collect(directive, "orch_wc1", packet_path=tmp_path / "pkt.json")
        assert packet is not None
        assert packet["trace_id"] == "orch_wc1"

    def test_packet_none_on_failure(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(1)), \
             patch("builtins.open", mock_open(read_data="")):
            result, packet = run_with_collect(directive, "orch_wc1")
        assert result.status == "failed"
        assert packet is None

    def test_packet_none_on_timeout(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=600)), \
             patch("builtins.open", mock_open(read_data="")):
            result, packet = run_with_collect(directive, "orch_wc1")
        assert result.status == "timeout"
        assert packet is None

    def test_collect_called_with_trace_id(self, tmp_path):
        directive = _fake_directive(tmp_path)
        mock_packet = _fake_packet("orch_wc2")
        with patch("subprocess.run", return_value=_make_proc(0)), \
             patch("builtins.open", mock_open(read_data="")), \
             patch("collect_packet.collect", return_value=mock_packet) as mock_cp:
            run_with_collect(directive, "orch_wc2", packet_path=tmp_path / "pkt.json")
        mock_cp.assert_called_once()
        assert mock_cp.call_args.kwargs.get("trace_id") == "orch_wc2" or \
               mock_cp.call_args.args[0] == "orch_wc2"

    def test_collect_failure_returns_result_with_no_packet(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0, stdout="out")), \
             patch("builtins.open", mock_open(read_data="")), \
             patch("collect_packet.collect", side_effect=RuntimeError("collect exploded")):
            result, packet = run_with_collect(directive, "orch_wc3", packet_path=tmp_path / "pkt.json")
        assert result.status == "completed"
        assert packet is None
        assert "collect_packet error" in result.stderr

    def test_packet_written_to_custom_path(self, tmp_path):
        directive = _fake_directive(tmp_path)
        mock_packet = _fake_packet("orch_wc4")
        pkt_path = tmp_path / "custom_packet.json"
        with patch("subprocess.run", return_value=_make_proc(0)), \
             patch("builtins.open", mock_open(read_data="")), \
             patch("collect_packet.collect", return_value=mock_packet):
            run_with_collect(directive, "orch_wc4", packet_path=pkt_path)
        assert pkt_path.exists()
        written = json.loads(pkt_path.read_text())
        assert written["trace_id"] == "orch_wc4"

    def test_run_pytest_passed_to_collect(self, tmp_path):
        directive = _fake_directive(tmp_path)
        mock_packet = _fake_packet("orch_wc5")
        with patch("subprocess.run", return_value=_make_proc(0)), \
             patch("builtins.open", mock_open(read_data="")), \
             patch("collect_packet.collect", return_value=mock_packet) as mock_cp:
            run_with_collect(directive, "orch_wc5", run_pytest=True, packet_path=tmp_path / "pkt.json")
        # Check run_pytest_flag=True was passed
        kwargs = mock_cp.call_args.kwargs
        args = mock_cp.call_args.args
        pytest_flag = kwargs.get("run_pytest_flag", args[2] if len(args) > 2 else False)
        assert pytest_flag is True

    def test_base_commit_passed_to_collect(self, tmp_path):
        directive = _fake_directive(tmp_path)
        mock_packet = _fake_packet("orch_wc6")
        with patch("subprocess.run", return_value=_make_proc(0)), \
             patch("builtins.open", mock_open(read_data="")), \
             patch("collect_packet.collect", return_value=mock_packet) as mock_cp:
            run_with_collect(directive, "orch_wc6", base_commit="abc123", packet_path=tmp_path / "pkt.json")
        kwargs = mock_cp.call_args.kwargs
        args = mock_cp.call_args.args
        base = kwargs.get("base_commit", args[1] if len(args) > 1 else None)
        assert base == "abc123"


# ---------------------------------------------------------------------------
# Custom permission_mode
# ---------------------------------------------------------------------------
class TestCustomPermissionMode:
    def test_custom_permission_mode_in_cmd(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_sp, \
             patch("builtins.open", mock_open(read_data="")):
            run(directive, "orch_pm1", permission_mode="default")
        cmd = mock_sp.call_args[0][0]
        assert "default" in cmd

    def test_default_permission_mode_is_bypass(self, tmp_path):
        directive = _fake_directive(tmp_path)
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_sp, \
             patch("builtins.open", mock_open(read_data="")):
            run(directive, "orch_pm2")
        cmd = mock_sp.call_args[0][0]
        assert DEFAULT_PERMISSION_MODE in cmd
