"""Tests for 'python orchestrator/main.py status' subcommand — 6 deterministic tests."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# Match project convention: add orchestrator/ and repo root to sys.path
_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
_root = os.path.join(os.path.dirname(__file__), "..", "..")
for _p in (_root, _orch_dir):
    _p = os.path.abspath(_p)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import main as orch_main

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_MANIFEST = {
    "schema_version": "v1",
    "fsm_state": "awaiting_execution",
    "current_task_id": "TEST-001",
    "current_sprint_goal": "Implement the widget factory for production use across multiple environments",
    "trace_id": "orch_test_trace_abc",
    "attempt_count": 3,
    "retry_count": 1,
    "last_verdict": "SCOPE_APPROVED",
    "_last_risk_class": "SEMI",
    "updated_at": "2026-04-09T10:00:00+00:00",
    "last_audit_result": {
        "verdict": "SCOPE_APPROVED",
        "gate_passed": True,
    },
}

MINIMAL_MANIFEST = {
    "schema_version": "v1",
    "fsm_state": "idle",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_status_displays_all_fields(capsys):
    """Status output includes all key manifest fields."""
    with mock.patch.object(orch_main, "load_manifest", return_value=SAMPLE_MANIFEST):
        with mock.patch("task_queue.queue_depth", return_value=5):
            orch_main.cmd_status(mock.MagicMock())
    out = capsys.readouterr().out
    assert "awaiting_execution" in out
    assert "TEST-001" in out
    assert "orch_test_trace_abc" in out
    assert "3" in out           # attempt_count
    assert "1" in out           # retry_count
    assert "SCOPE_APPROVED" in out
    assert "SEMI" in out
    assert "Queue Depth:" in out
    assert "5" in out


def test_status_missing_optional_fields(capsys):
    """Status handles manifest with missing optional fields gracefully (N/A fallback)."""
    with mock.patch.object(orch_main, "load_manifest", return_value=MINIMAL_MANIFEST):
        with mock.patch("task_queue.queue_depth", return_value=0):
            orch_main.cmd_status(mock.MagicMock())
    out = capsys.readouterr().out
    assert "idle" in out
    assert "N/A" in out  # missing fields show N/A


def test_status_empty_manifest(capsys):
    """Status works with completely empty manifest dict."""
    with mock.patch.object(orch_main, "load_manifest", return_value={}):
        with mock.patch("task_queue.queue_depth", return_value=0):
            orch_main.cmd_status(mock.MagicMock())
    out = capsys.readouterr().out
    assert "FSM State:" in out
    assert "Task ID:" in out
    assert "Queue Depth:" in out
    assert "N/A" in out


def test_status_exit_code_zero():
    """Status subcommand exits with code 0 (no exception)."""
    with mock.patch.object(orch_main, "load_manifest", return_value=SAMPLE_MANIFEST):
        with mock.patch("task_queue.queue_depth", return_value=0):
            # Should not raise
            orch_main.cmd_status(mock.MagicMock())


def test_status_truncates_long_goal(capsys):
    """Sprint goal is truncated to 80 chars in status output."""
    long_goal = "A" * 200
    manifest = {**MINIMAL_MANIFEST, "current_sprint_goal": long_goal}
    with mock.patch.object(orch_main, "load_manifest", return_value=manifest):
        with mock.patch("task_queue.queue_depth", return_value=0):
            orch_main.cmd_status(mock.MagicMock())
    out = capsys.readouterr().out
    # The goal line should have at most 80 A's, not 200
    goal_line = [l for l in out.splitlines() if "Sprint Goal:" in l][0]
    a_count = goal_line.count("A")
    assert a_count == 80


def test_status_queue_unavailable(capsys):
    """Status handles task_queue import failure gracefully."""
    with mock.patch.object(orch_main, "load_manifest", return_value=SAMPLE_MANIFEST):
        with mock.patch.dict(sys.modules, {"task_queue": None}):
            orch_main.cmd_status(mock.MagicMock())
    out = capsys.readouterr().out
    assert "Queue Depth:" in out
    assert "N/A" in out or "unavailable" in out
