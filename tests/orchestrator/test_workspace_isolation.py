"""
test_workspace_isolation.py — P1: workspace isolation tests.

Covers:
  1. "processing" FSM state prevents concurrent cycle starts
  2. Per-run directory creation and artifact isolation
  3. Narrow lock scope: lock released before slow work
  4. _save_manifest_atomic works correctly
  5. cycle_busy vs lock_busy distinction
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "orchestrator"))


class TestProcessingState:
    """Verify "processing" FSM state prevents concurrent cycles."""

    def test_processing_state_returns_cycle_busy(self, tmp_path, capsys):
        """When state is 'processing', cmd_cycle exits with cycle_busy."""
        import main

        manifest = {
            "fsm_state": "processing",
            "current_task_id": "TEST",
            "current_sprint_goal": "test",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        lock_path = tmp_path / "test.lock"
        runs_path = tmp_path / "runs.jsonl"

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "LOCK_PATH", lock_path), \
             patch.object(main, "RUNS_PATH", runs_path):
            main.cmd_cycle(argparse.Namespace())

        captured = capsys.readouterr()
        assert "cycle_busy" in captured.err

        # Verify runs.jsonl entry
        assert runs_path.exists()
        entry = json.loads(runs_path.read_text(encoding="utf-8").strip())
        assert entry["status"] == "cycle_busy"

    def test_ready_transitions_to_processing(self, tmp_path):
        """When state is 'ready', cmd_cycle sets 'processing' before work."""
        import main

        manifest = {
            "fsm_state": "ready",
            "current_task_id": "TEST",
            "current_sprint_goal": "test goal",
            "trace_id": "",
            "attempt_count": 0,
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        lock_path = tmp_path / "test.lock"

        saved_states = []

        original_save = main.save_manifest

        def tracking_save(m):
            saved_states.append(m.get("fsm_state"))
            original_save(m)

        # Mock _cmd_cycle_inner to avoid running the full cycle
        def fake_inner(args, m):
            pass  # Just return — we only care about the state transition

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "LOCK_PATH", lock_path), \
             patch.object(main, "save_manifest", tracking_save), \
             patch.object(main, "_cmd_cycle_inner", fake_inner):
            main.cmd_cycle(argparse.Namespace())

        # First save should be "processing" (the claim)
        assert saved_states[0] == "processing"


class TestPerRunDirectory:
    """Verify per-run directory creation and artifact placement."""

    def test_ensure_run_dir_creates_directory(self, tmp_path):
        import main

        with patch.object(main, "RUNS_DIR", tmp_path / "runs"):
            run_dir = main._ensure_run_dir("orch_test_001")
            assert run_dir.exists()
            assert run_dir.is_dir()
            assert run_dir.name == "orch_test_001"

    def test_ensure_run_dir_idempotent(self, tmp_path):
        import main

        with patch.object(main, "RUNS_DIR", tmp_path / "runs"):
            dir1 = main._ensure_run_dir("orch_test_002")
            dir2 = main._ensure_run_dir("orch_test_002")
            assert dir1 == dir2
            assert dir1.exists()


class TestSaveManifestAtomic:
    """Verify _save_manifest_atomic acquires lock and saves."""

    def test_atomic_save_updates_manifest(self, tmp_path):
        import main

        manifest = {
            "fsm_state": "processing",
            "current_task_id": "TEST",
            "updated_at": "",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        lock_path = tmp_path / "test.lock"

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "LOCK_PATH", lock_path):
            main._save_manifest_atomic({
                "fsm_state": "error",
                "last_verdict": "CYCLE_ERROR",
            })

        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert saved["fsm_state"] == "error"
        assert saved["last_verdict"] == "CYCLE_ERROR"
        # Original fields preserved
        assert saved["current_task_id"] == "TEST"


class TestNarrowLockScope:
    """Verify lock is released before slow cycle work starts."""

    def test_lock_released_during_cycle_inner(self, tmp_path):
        """Lock should NOT be held when _cmd_cycle_inner executes."""
        import main

        manifest = {
            "fsm_state": "ready",
            "current_task_id": "TEST",
            "current_sprint_goal": "test",
            "trace_id": "",
            "attempt_count": 0,
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        lock_path = tmp_path / "test.lock"

        lock_held_during_inner = []

        def spy_inner(args, m):
            # Try to acquire lock — if it's released, this should succeed
            fh = main._acquire_lock()
            lock_held_during_inner.append(fh is not None)
            if fh:
                main._release_lock(fh)

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "LOCK_PATH", lock_path), \
             patch.object(main, "_cmd_cycle_inner", spy_inner):
            main.cmd_cycle(argparse.Namespace())

        # Lock should have been acquirable during _cmd_cycle_inner
        assert len(lock_held_during_inner) == 1
        assert lock_held_during_inner[0] is True, \
            "Lock was still held during _cmd_cycle_inner — narrow lock scope failed"

    def test_exception_in_inner_sets_error_state(self, tmp_path):
        """If _cmd_cycle_inner raises, manifest should go to error state."""
        import main

        manifest = {
            "fsm_state": "ready",
            "current_task_id": "TEST",
            "current_sprint_goal": "test",
            "trace_id": "",
            "attempt_count": 0,
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        lock_path = tmp_path / "test.lock"
        runs_path = tmp_path / "runs.jsonl"

        def failing_inner(args, m):
            raise RuntimeError("simulated cycle failure")

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "LOCK_PATH", lock_path), \
             patch.object(main, "RUNS_PATH", runs_path), \
             patch.object(main, "_cmd_cycle_inner", failing_inner):
            # Should not propagate the exception
            main.cmd_cycle(argparse.Namespace())

        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert saved["fsm_state"] == "error"
        assert saved["last_verdict"] == "CYCLE_ERROR"


class TestCycleBusyVsLockBusy:
    """Verify distinction between lock_busy and cycle_busy."""

    def test_lock_busy_when_file_locked(self, tmp_path, capsys):
        """lock_busy: file lock held by another process."""
        import main

        lock_path = tmp_path / "test.lock"

        with patch.object(main, "LOCK_PATH", lock_path):
            fh = main._acquire_lock()
            assert fh is not None
            try:
                main.cmd_cycle(argparse.Namespace())
            finally:
                main._release_lock(fh)

        captured = capsys.readouterr()
        assert "lock_busy" in captured.err

    def test_cycle_busy_when_processing(self, tmp_path, capsys):
        """cycle_busy: no file lock, but FSM is 'processing'."""
        import main

        manifest = {
            "fsm_state": "processing",
            "current_task_id": "TEST",
            "current_sprint_goal": "test",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        lock_path = tmp_path / "test.lock"
        runs_path = tmp_path / "runs.jsonl"

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "LOCK_PATH", lock_path), \
             patch.object(main, "RUNS_PATH", runs_path):
            main.cmd_cycle(argparse.Namespace())

        captured = capsys.readouterr()
        assert "cycle_busy" in captured.err
        # NOT lock_busy
        assert "lock_busy" not in captured.err
