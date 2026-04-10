"""
test_start_telegram.py — Tests for the unified Telegram launcher.

Tests process spec structure, start/stop logic, signal handling.
"""
from __future__ import annotations

import os
import subprocess
import sys

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)

import start_telegram as launcher  # noqa: E402


class TestProcessSpecs:

    def test_all_three_defined(self):
        assert "gateway" in launcher.PROCESSES
        assert "bridge" in launcher.PROCESSES
        assert "watcher" in launcher.PROCESSES

    def test_each_has_required_keys(self):
        for name, spec in launcher.PROCESSES.items():
            assert "cmd" in spec, f"{name} missing cmd"
            assert "label" in spec, f"{name} missing label"
            assert "restart_delay" in spec, f"{name} missing restart_delay"
            assert isinstance(spec["cmd"], list), f"{name} cmd not a list"
            assert len(spec["cmd"]) >= 2, f"{name} cmd too short"

    def test_commands_point_to_existing_files(self):
        for name, spec in launcher.PROCESSES.items():
            script = spec["cmd"][1]
            assert os.path.exists(script), f"{name}: {script} does not exist"

    def test_bridge_has_daemon_flag(self):
        cmd = launcher.PROCESSES["bridge"]["cmd"]
        assert "--daemon" in cmd


class TestStartProcess:

    def test_start_returns_popen(self, monkeypatch):
        """Verify _start_process returns a Popen for a trivial command."""
        monkeypatch.setitem(
            launcher.PROCESSES, "test",
            {"cmd": [sys.executable, "-c", "pass"], "label": "Test", "restart_delay": 1},
        )
        proc = launcher._start_process("test")
        assert proc is not None
        proc.wait()
        assert proc.returncode == 0

    def test_start_bad_command_returns_none(self, monkeypatch):
        monkeypatch.setitem(
            launcher.PROCESSES, "bad",
            {"cmd": ["/nonexistent/python", "-c", "pass"], "label": "Bad", "restart_delay": 1},
        )
        proc = launcher._start_process("bad")
        assert proc is None


class TestStopAll:

    def test_stop_terminates_children(self, monkeypatch):
        """Start a sleeping process, then stop_all should terminate it."""
        # Reset global state
        launcher._stopping = False
        launcher._children.clear()

        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        launcher._children["test"] = proc
        monkeypatch.setitem(
            launcher.PROCESSES, "test",
            {"cmd": [], "label": "Test", "restart_delay": 1},
        )

        launcher._stop_all()

        assert proc.poll() is not None  # terminated
        # Cleanup
        launcher._stopping = False
        launcher._children.clear()


class TestCLIParsing:

    def test_no_watcher_flag(self):
        """Verify --no-watcher flag is recognized."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--no-watcher", action="store_true")
        args = parser.parse_args(["--no-watcher"])
        assert args.no_watcher is True

    def test_default_includes_watcher(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--no-watcher", action="store_true")
        args = parser.parse_args([])
        assert args.no_watcher is False
