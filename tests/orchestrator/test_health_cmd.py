"""Tests for 'python orchestrator/main.py health' subcommand."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
_root = os.path.join(os.path.dirname(__file__), "..", "..")
for _p in (_root, _orch_dir):
    _p = os.path.abspath(_p)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import main as orch_main


def _make_result(healthy: bool, checks: list[dict]) -> dict:
    return {"healthy": healthy, "checks": checks}


ALL_PASS = _make_result(True, [
    {"name": "manifest_valid", "ok": True, "detail": "OK"},
    {"name": "config_loadable", "ok": True, "detail": "2 schemas available"},
    {"name": "auditor_keys_present", "ok": True, "detail": "All auditor keys present"},
    {"name": "queue_readable", "ok": True, "detail": "No queue file (empty queue)"},
])

ONE_FAIL = _make_result(False, [
    {"name": "manifest_valid", "ok": True, "detail": "OK"},
    {"name": "config_loadable", "ok": False, "detail": "Import failed: no module"},
    {"name": "auditor_keys_present", "ok": True, "detail": "All auditor keys present"},
    {"name": "queue_readable", "ok": True, "detail": "0 tasks in queue"},
])


class _FakeArgs:
    pass


@patch("health_check.run_health_check", return_value=ALL_PASS)
def test_health_all_pass_exits_zero(mock_hc, capsys):
    """All checks pass -> prints report, no SystemExit."""
    orch_main.cmd_health(_FakeArgs())
    out = capsys.readouterr().out
    assert "All checks passed" in out
    assert "[PASS]" in out


@patch("health_check.run_health_check", return_value=ONE_FAIL)
def test_health_one_fail_exits_one(mock_hc, capsys):
    """One check fails -> prints report and exits with code 1."""
    with pytest.raises(SystemExit) as exc_info:
        orch_main.cmd_health(_FakeArgs())
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "[FAIL]" in out
    assert "Some checks failed" in out


@patch("health_check.run_health_check", return_value=ALL_PASS)
def test_health_output_contains_check_names_and_details(mock_hc, capsys):
    """Output contains each check's name and detail string."""
    orch_main.cmd_health(_FakeArgs())
    out = capsys.readouterr().out
    for check in ALL_PASS["checks"]:
        assert check["name"] in out
        assert check["detail"] in out
