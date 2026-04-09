"""
test_task_queue.py — Deterministic tests for orchestrator/task_queue.py (P2).

All tests use tempdir — no real queue file touched. Pure I/O + logic.
"""
from __future__ import annotations

import json
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)


# Patch QUEUE_PATH for all tests
@pytest.fixture(autouse=True)
def tmp_queue(tmp_path):
    """Redirect QUEUE_PATH to a temp directory for test isolation."""
    import task_queue as tq
    original = tq.QUEUE_PATH
    tq.QUEUE_PATH = tmp_path / "task_queue.json"
    yield tmp_path
    tq.QUEUE_PATH = original


# ---------------------------------------------------------------------------
# load_queue / save_queue
# ---------------------------------------------------------------------------

class TestLoadSaveQueue:
    def test_load_empty_returns_empty_list(self):
        import task_queue as tq
        assert tq.load_queue() == []

    def test_load_missing_file_returns_empty_list(self):
        import task_queue as tq
        assert not tq.QUEUE_PATH.exists()
        assert tq.load_queue() == []

    def test_save_and_reload(self):
        import task_queue as tq
        entries = [{"task_id": "t1", "sprint_goal": "goal1", "risk_class": "LOW",
                    "priority": 0, "added_at": "2026-01-01T00:00:00+00:00"}]
        tq.save_queue(entries)
        loaded = tq.load_queue()
        assert len(loaded) == 1
        assert loaded[0]["task_id"] == "t1"

    def test_load_corrupt_json_returns_empty(self):
        import task_queue as tq
        tq.QUEUE_PATH.write_text("this is not json", encoding="utf-8")
        result = tq.load_queue()
        assert result == []

    def test_load_non_list_json_returns_empty(self):
        import task_queue as tq
        tq.QUEUE_PATH.write_text('{"not": "a list"}', encoding="utf-8")
        result = tq.load_queue()
        assert result == []


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------

class TestEnqueue:
    def test_enqueue_creates_entry(self):
        import task_queue as tq
        entry = tq.enqueue("task-1", "Do the thing", risk_class="LOW")
        assert entry["task_id"] == "task-1"
        assert entry["sprint_goal"] == "Do the thing"
        assert entry["risk_class"] == "LOW"
        assert entry["priority"] == 0
        assert "added_at" in entry

    def test_enqueue_persists_to_disk(self):
        import task_queue as tq
        tq.enqueue("task-1", "Goal")
        queue = tq.load_queue()
        assert len(queue) == 1

    def test_enqueue_semi_risk(self):
        import task_queue as tq
        entry = tq.enqueue("task-semi", "SEMI task", risk_class="SEMI")
        assert entry["risk_class"] == "SEMI"

    def test_enqueue_core_risk(self):
        import task_queue as tq
        entry = tq.enqueue("task-core", "CORE task", risk_class="CORE")
        assert entry["risk_class"] == "CORE"

    def test_enqueue_invalid_risk_raises(self):
        import task_queue as tq
        with pytest.raises(ValueError, match="risk_class"):
            tq.enqueue("task-x", "Goal", risk_class="INVALID")

    def test_enqueue_empty_task_id_raises(self):
        import task_queue as tq
        with pytest.raises(ValueError, match="task_id"):
            tq.enqueue("", "Goal")

    def test_enqueue_whitespace_task_id_raises(self):
        import task_queue as tq
        with pytest.raises(ValueError, match="task_id"):
            tq.enqueue("   ", "Goal")

    def test_enqueue_preserves_priority(self):
        import task_queue as tq
        entry = tq.enqueue("t1", "G", priority=5)
        assert entry["priority"] == 5

    def test_multiple_enqueues_accumulate(self):
        import task_queue as tq
        tq.enqueue("t1", "Goal 1")
        tq.enqueue("t2", "Goal 2")
        tq.enqueue("t3", "Goal 3")
        assert tq.queue_depth() == 3


# ---------------------------------------------------------------------------
# peek_next / dequeue ordering
# ---------------------------------------------------------------------------

class TestQueueOrdering:
    def test_fifo_within_same_priority(self):
        import task_queue as tq
        import time
        tq.enqueue("first", "First", priority=0)
        time.sleep(0.01)
        tq.enqueue("second", "Second", priority=0)
        assert tq.peek_next()["task_id"] == "first"

    def test_higher_priority_comes_first(self):
        import task_queue as tq
        tq.enqueue("low", "Low priority", priority=0)
        tq.enqueue("high", "High priority", priority=10)
        assert tq.peek_next()["task_id"] == "high"

    def test_peek_does_not_remove(self):
        import task_queue as tq
        tq.enqueue("t1", "Goal")
        tq.peek_next()
        assert tq.queue_depth() == 1

    def test_peek_empty_returns_none(self):
        import task_queue as tq
        assert tq.peek_next() is None

    def test_dequeue_removes_from_queue(self):
        import task_queue as tq
        tq.enqueue("t1", "Goal")
        task = tq.dequeue()
        assert task is not None
        assert task["task_id"] == "t1"
        assert tq.queue_depth() == 0

    def test_dequeue_empty_returns_none(self):
        import task_queue as tq
        assert tq.dequeue() is None

    def test_dequeue_order_fifo(self):
        import task_queue as tq
        import time
        tq.enqueue("first", "First")
        time.sleep(0.01)
        tq.enqueue("second", "Second")
        t1 = tq.dequeue()
        t2 = tq.dequeue()
        assert t1["task_id"] == "first"
        assert t2["task_id"] == "second"


# ---------------------------------------------------------------------------
# remove_by_id / clear
# ---------------------------------------------------------------------------

class TestRemoveAndClear:
    def test_remove_by_id_removes_specific_task(self):
        import task_queue as tq
        tq.enqueue("t1", "G1")
        tq.enqueue("t2", "G2")
        result = tq.remove_by_id("t1")
        assert result is True
        remaining = tq.load_queue()
        assert all(t["task_id"] != "t1" for t in remaining)

    def test_remove_by_id_returns_false_if_not_found(self):
        import task_queue as tq
        tq.enqueue("t1", "G1")
        assert tq.remove_by_id("nonexistent") is False

    def test_clear_removes_all(self):
        import task_queue as tq
        tq.enqueue("t1", "G1")
        tq.enqueue("t2", "G2")
        removed = tq.clear_queue()
        assert removed == 2
        assert tq.queue_depth() == 0

    def test_clear_empty_queue_returns_zero(self):
        import task_queue as tq
        assert tq.clear_queue() == 0


# ---------------------------------------------------------------------------
# try_auto_advance
# ---------------------------------------------------------------------------

class TestAutoAdvance:
    def _ready_manifest(self):
        return {
            "fsm_state": "ready",
            "last_verdict": None,
            "attempt_count": 2,
            "retry_count": 1,
            "_retry_reason": "some reason",
        }

    def test_auto_advance_disabled_returns_none(self):
        import task_queue as tq
        tq.enqueue("t1", "Goal", risk_class="LOW")
        manifest = self._ready_manifest()
        result = tq.try_auto_advance(manifest, auto_execute=False)
        assert result is None
        assert manifest["fsm_state"] == "ready"

    def test_auto_advance_empty_queue_returns_none(self):
        import task_queue as tq
        manifest = self._ready_manifest()
        result = tq.try_auto_advance(manifest, auto_execute=True)
        assert result is None

    def test_auto_advance_wrong_state_returns_none(self):
        import task_queue as tq
        tq.enqueue("t1", "Goal", risk_class="LOW")
        manifest = {"fsm_state": "awaiting_owner_reply", "last_verdict": "ACCEPTANCE_FAILED"}
        result = tq.try_auto_advance(manifest, auto_execute=True)
        assert result is None

    def test_auto_advance_low_task_advances(self):
        import task_queue as tq
        tq.enqueue("next-task", "Do next thing", risk_class="LOW")
        manifest = self._ready_manifest()
        result = tq.try_auto_advance(manifest, auto_execute=True)
        assert result is not None
        assert result["task_id"] == "next-task"
        assert manifest["current_task_id"] == "next-task"
        assert manifest["current_sprint_goal"] == "Do next thing"
        assert manifest["attempt_count"] == 0
        assert manifest["retry_count"] == 0
        assert "_retry_reason" not in manifest

    def test_auto_advance_semi_task_skipped(self):
        """SEMI tasks should NOT be auto-advanced — need owner confirmation."""
        import task_queue as tq
        tq.enqueue("semi-task", "SEMI work", risk_class="SEMI")
        manifest = self._ready_manifest()
        result = tq.try_auto_advance(manifest, auto_execute=True)
        assert result is None  # SEMI not auto-advanced
        assert tq.queue_depth() == 1  # still in queue

    def test_auto_advance_core_task_skipped(self):
        """CORE tasks should NOT be auto-advanced."""
        import task_queue as tq
        tq.enqueue("core-task", "CORE work", risk_class="CORE")
        manifest = self._ready_manifest()
        result = tq.try_auto_advance(manifest, auto_execute=True)
        assert result is None
        assert tq.queue_depth() == 1

    def test_auto_advance_dequeues_task(self):
        """After advance, task is removed from queue."""
        import task_queue as tq
        tq.enqueue("t1", "Goal")
        tq.enqueue("t2", "Goal 2")
        manifest = self._ready_manifest()
        tq.try_auto_advance(manifest, auto_execute=True)
        assert tq.queue_depth() == 1  # t1 consumed, t2 remains

    def test_auto_advance_with_last_verdict_set_returns_none(self):
        """If last_verdict is not None, do not advance (task not cleanly completed)."""
        import task_queue as tq
        tq.enqueue("t1", "Goal")
        manifest = {"fsm_state": "ready", "last_verdict": "ACCEPTANCE_FAILED"}
        result = tq.try_auto_advance(manifest, auto_execute=True)
        assert result is None

    def test_auto_advance_prioritizes_high_priority(self):
        """High-priority LOW task should be advanced before low-priority."""
        import task_queue as tq
        import time
        tq.enqueue("low-prio", "Low", priority=0)
        time.sleep(0.01)
        tq.enqueue("high-prio", "High", priority=5)
        manifest = self._ready_manifest()
        result = tq.try_auto_advance(manifest, auto_execute=True)
        assert result["task_id"] == "high-prio"


# ---------------------------------------------------------------------------
# main.py wiring: _try_queue_advance
# ---------------------------------------------------------------------------

class TestMainQueueWiring:
    """_try_queue_advance in main.py integrates with task_queue module."""

    def test_try_queue_advance_noop_on_empty_queue(self, tmp_path):
        import main
        import task_queue as tq

        manifest = {
            "fsm_state": "ready",
            "last_verdict": None,
            "current_task_id": "done-task",
            "current_sprint_goal": "done",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        runs_path = tmp_path / "runs.jsonl"

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "RUNS_PATH", runs_path), \
             patch.object(main, "_load_config", return_value={"auto_execute": True}):
            main._try_queue_advance(manifest)

        # manifest unchanged
        reloaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert reloaded["current_task_id"] == "done-task"

    def test_try_queue_advance_advances_low_task(self, tmp_path):
        import main
        import task_queue as tq

        manifest = {
            "fsm_state": "ready",
            "last_verdict": None,
            "current_task_id": "old",
            "current_sprint_goal": "old goal",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        runs_path = tmp_path / "runs.jsonl"

        tq.enqueue("new-task", "New goal", risk_class="LOW")

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "RUNS_PATH", runs_path), \
             patch.object(main, "_load_config", return_value={"auto_execute": True}):
            main._try_queue_advance(manifest)

        reloaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert reloaded["current_task_id"] == "new-task"
        assert reloaded["current_sprint_goal"] == "New goal"

    def test_try_queue_advance_skips_not_ready(self, tmp_path):
        import main
        import task_queue as tq

        manifest = {
            "fsm_state": "error",
            "last_verdict": "CYCLE_ERROR",
            "current_task_id": "old",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        runs_path = tmp_path / "runs.jsonl"

        tq.enqueue("new-task", "New goal")

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "RUNS_PATH", runs_path), \
             patch.object(main, "_load_config", return_value={"auto_execute": True}):
            main._try_queue_advance(manifest)

        reloaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert reloaded["current_task_id"] == "old"  # unchanged

    def test_try_queue_advance_logs_run(self, tmp_path):
        import main
        import task_queue as tq

        manifest = {
            "fsm_state": "ready",
            "last_verdict": None,
            "current_task_id": "old",
            "current_sprint_goal": "old",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        runs_path = tmp_path / "runs.jsonl"

        tq.enqueue("new-task", "New goal", risk_class="LOW")

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "RUNS_PATH", runs_path), \
             patch.object(main, "_load_config", return_value={"auto_execute": True}):
            main._try_queue_advance(manifest)

        assert runs_path.exists()
        entry = json.loads(runs_path.read_text(encoding="utf-8").strip())
        assert entry["event"] == "queue_auto_advance"
        assert entry["new_task_id"] == "new-task"
