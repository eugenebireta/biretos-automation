"""Tests for 'python orchestrator/main.py health' subcommand — 3 deterministic tests."""
from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
_root = os.path.join(os.path.dirname(__file__), "..", "..")
for _p in (_root, _orch_dir):
    _p = os.path.abspath(_p)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import health_check as _hc  # noqa: E402 — preload for patching
import main as orch_main  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_health_result(all_pass: bool) -> dict:
    """Build a fake run_health_check return value."""
    checks = [
        {"name": "manifest_valid", "ok": True, "detail": "OK"},
        {"name": "config_loadable", "ok": True, "detail": "2 schemas available"},
        {"name": "auditor_keys_present", "ok": all_pass, "detail": "All auditor keys present" if all_pass else "Missing env vars: ['GEMINI_API_KEY']"},
        {"name": "queue_readable", "ok": True, "detail": "No queue file (empty queue)"},
    ]
    return {"healthy": all_pass, "checks": checks}


# We need to patch at the module path used by cmd_health's lazy import.
# cmd_health does: from orchestrator.health_check import run_health_check
# So we patch on the health_check module object which is the same as orchestrator.health_check.
_PATCH_TARGET = "health_check.run_health_check"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_health_all_pass_exits_zero(capsys):
    """When all checks pass, health prints report and exits 0 (no exception)."""
    result = _make_health_result(all_pass=True)
    with mock.patch(_PATCH_TARGET, return_value=result):
        orch_main.cmd_health(mock.MagicMock())
    out = capsys.readouterr().out
    assert "HEALTHY" in out
    assert "FAIL" not in out
    assert "[PASS]" in out


def test_health_one_fail_exits_one(capsys):
    """When any check fails, health exits with code 1."""
    result = _make_health_result(all_pass=False)
    with mock.patch(_PATCH_TARGET, return_value=result):
        with pytest.raises(SystemExit) as exc_info:
            orch_main.cmd_health(mock.MagicMock())
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "UNHEALTHY" in out
    assert "[FAIL]" in out


def test_health_output_contains_check_names_and_details(capsys):
    """Output includes each check's name and detail string."""
    result = _make_health_result(all_pass=True)
    with mock.patch(_PATCH_TARGET, return_value=result):
        orch_main.cmd_health(mock.MagicMock())
    out = capsys.readouterr().out
    for check in result["checks"]:
        assert check["name"] in out
        assert check["detail"] in out
