"""Tests for orchestrator/health_check.py — 9 deterministic tests."""
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

import health_check as hc
from health_check import (
    AUDITOR_ENV_KEYS,
    REQUIRED_MANIFEST_KEYS,
    _check_auditor_keys_present,
    _check_config_loadable,
    _check_manifest_valid,
    _check_queue_readable,
    run_health_check,
)

TRACE_ID = "test_trace_001"


# --- Schema tests ---


def test_result_schema():
    """run_health_check returns {healthy: bool, checks: list}."""
    with mock.patch.object(
        hc, "MANIFEST_PATH",
        _write_tmp_json({"schema_version": "v1", "fsm_state": "x", "current_task_id": "t", "trace_id": "t"}),
    ), mock.patch.dict(os.environ, {k: "fake" for k in AUDITOR_ENV_KEYS}):
        result = run_health_check(trace_id=TRACE_ID)
    assert isinstance(result, dict)
    assert "healthy" in result
    assert "checks" in result
    assert isinstance(result["healthy"], bool)
    assert isinstance(result["checks"], list)
    for check in result["checks"]:
        assert "name" in check
        assert "ok" in check
        assert "detail" in check


# --- Individual check tests ---


def test_manifest_valid_ok(tmp_path):
    manifest = tmp_path / "manifest.json"
    data = {k: "test" for k in REQUIRED_MANIFEST_KEYS}
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with mock.patch.object(hc, "MANIFEST_PATH", manifest):
        result = _check_manifest_valid()
    assert result["ok"] is True


def test_manifest_missing(tmp_path):
    missing = tmp_path / "no_manifest.json"
    with mock.patch.object(hc, "MANIFEST_PATH", missing):
        result = _check_manifest_valid()
    assert result["ok"] is False
    assert "not found" in result["detail"]


def test_manifest_invalid_json(tmp_path):
    bad = tmp_path / "manifest.json"
    bad.write_text("{broken", encoding="utf-8")
    with mock.patch.object(hc, "MANIFEST_PATH", bad):
        result = _check_manifest_valid()
    assert result["ok"] is False
    assert "Invalid JSON" in result["detail"]


def test_manifest_missing_keys(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": "v1"}), encoding="utf-8")
    with mock.patch.object(hc, "MANIFEST_PATH", manifest):
        result = _check_manifest_valid()
    assert result["ok"] is False
    assert "Missing keys" in result["detail"]


def test_auditor_keys_all_present():
    with mock.patch.dict(os.environ, {k: "sk-fake" for k in AUDITOR_ENV_KEYS}):
        result = _check_auditor_keys_present()
    assert result["ok"] is True


def test_auditor_keys_missing():
    env = {k: "" for k in AUDITOR_ENV_KEYS}
    with mock.patch.dict(os.environ, env, clear=False):
        result = _check_auditor_keys_present()
    assert result["ok"] is False
    assert "Missing env vars" in result["detail"]


def test_queue_readable_no_file(tmp_path):
    missing = tmp_path / "task_queue.json"
    with mock.patch.object(hc, "QUEUE_PATH", missing):
        result = _check_queue_readable()
    assert result["ok"] is True
    assert "empty queue" in result["detail"]


def test_queue_readable_valid(tmp_path):
    q = tmp_path / "task_queue.json"
    q.write_text(json.dumps([{"task_id": "T1"}]), encoding="utf-8")
    with mock.patch.object(hc, "QUEUE_PATH", q):
        result = _check_queue_readable()
    assert result["ok"] is True
    assert "1 tasks" in result["detail"]


# --- Helper ---

def _write_tmp_json(data: dict) -> Path:
    """Write data to a temp file and return its Path (for use in mock.patch)."""
    import tempfile
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, f)
    f.close()
    return Path(f.name)
