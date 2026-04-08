"""
tests/test_acceptance_checker_a5.py — deterministic unit tests for A5 check.

Covers:
  - Passing case: no task_id token conflict in changed/created files
  - Violation case: created file contains a different task_id token → raises ValueError
  - Directive without task_id: A5 is skipped (passed=True)
  - created_files and changed_files both scanned

No live API, no unmocked time/randomness — fully deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "orchestrator"))

import pytest

import acceptance_checker as ac
from acceptance_checker import check, AcceptanceResult

# Minimal directive with task_id header
_DIRECTIVE_WITH_TASK_ID = """\
trace_id: orch_test_001
task_id: A5-TASK-ID-CHECK
attempt: 1

## Scope (Tier-3 verified)
- orchestrator/acceptance_checker.py
- tests/test_acceptance_checker_a5.py
"""

_DIRECTIVE_NO_TASK_ID = """\
trace_id: orch_test_002
attempt: 1

## Scope (Tier-3 verified)
- orchestrator/acceptance_checker.py
"""

_BASE_PACKET = {
    "changed_files": [],
    "created_files": [],
    "test_results": {"passed": 5, "failed": 0},
    "affected_tiers": [],
}


# ---------------------------------------------------------------------------
# Passing case: files whose names contain no task_id token at all
# ---------------------------------------------------------------------------

def test_a5_passes_when_no_task_id_token_in_filenames():
    packet = {
        **_BASE_PACKET,
        "changed_files": ["orchestrator/acceptance_checker.py"],
        "created_files": ["tests/test_acceptance_checker_a5.py"],
    }
    result: AcceptanceResult = check(
        packet=packet,
        directive_text=_DIRECTIVE_WITH_TASK_ID,
        trace_id="orch_test_001",
        idempotency_key="test_a5_pass",
    )
    a5 = _find_check(result, "A5:TASK_ID_INTEGRITY")
    assert a5.passed is True
    assert "A5-TASK-ID-CHECK" in a5.detail
    assert result.passed is True


# ---------------------------------------------------------------------------
# Passing case: files that contain the *correct* task_id token
# ---------------------------------------------------------------------------

def test_a5_passes_when_filename_contains_correct_task_id():
    packet = {
        **_BASE_PACKET,
        "changed_files": ["orchestrator/acceptance_checker.py"],
        "created_files": ["tests/task_A5-TASK-ID-CHECK_result.json"],
    }
    result: AcceptanceResult = check(
        packet=packet,
        directive_text=_DIRECTIVE_WITH_TASK_ID,
        trace_id="orch_test_001",
        idempotency_key="test_a5_pass_correct_id",
    )
    a5 = _find_check(result, "A5:TASK_ID_INTEGRITY")
    assert a5.passed is True


# ---------------------------------------------------------------------------
# Violation case: created file carries a DIFFERENT task_id token
# ---------------------------------------------------------------------------

def test_a5_raises_on_wrong_task_id_in_created_file():
    packet = {
        **_BASE_PACKET,
        "changed_files": ["orchestrator/acceptance_checker.py"],
        # This file name contains RECLASSIFY-PEHA-8SKU — wrong task_id
        "created_files": ["catalog/RECLASSIFY-PEHA-8SKU_output.json"],
    }
    with pytest.raises(ValueError) as exc_info:
        check(
            packet=packet,
            directive_text=_DIRECTIVE_WITH_TASK_ID,
            trace_id="orch_test_001",
            idempotency_key="test_a5_violation",
        )
    msg = str(exc_info.value)
    assert "A5:TASK_ID_INTEGRITY VIOLATED" in msg
    assert "RECLASSIFY-PEHA-8SKU" in msg
    assert "A5-TASK-ID-CHECK" in msg


# ---------------------------------------------------------------------------
# Violation case: wrong task_id in a changed_file basename
# ---------------------------------------------------------------------------

def test_a5_raises_on_wrong_task_id_in_changed_file():
    packet = {
        **_BASE_PACKET,
        "changed_files": ["results/OTHER-TASK-ONE_report.json"],
        "created_files": [],
    }
    with pytest.raises(ValueError) as exc_info:
        check(
            packet=packet,
            directive_text=_DIRECTIVE_WITH_TASK_ID,
            trace_id="orch_test_001",
            idempotency_key="test_a5_violation_changed",
        )
    msg = str(exc_info.value)
    assert "A5:TASK_ID_INTEGRITY VIOLATED" in msg
    assert "OTHER-TASK-ONE" in msg


# ---------------------------------------------------------------------------
# Directive has no task_id — A5 is skipped
# ---------------------------------------------------------------------------

def test_a5_skipped_when_no_task_id_in_directive():
    packet = {
        **_BASE_PACKET,
        "changed_files": ["orchestrator/acceptance_checker.py"],
        # Even if the file has a task_id-like token, A5 is skipped
        "created_files": ["catalog/RECLASSIFY-PEHA-8SKU_output.json"],
    }
    # Must NOT raise
    result: AcceptanceResult = check(
        packet=packet,
        directive_text=_DIRECTIVE_NO_TASK_ID,
        trace_id="orch_test_002",
        idempotency_key="test_a5_skip",
    )
    a5 = _find_check(result, "A5:TASK_ID_INTEGRITY")
    assert a5.passed is True
    assert "skipped" in a5.detail


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _find_check(result: AcceptanceResult, check_id: str):
    for c in result.checks:
        if c.check_id == check_id:
            return c
    raise AssertionError(f"Check {check_id!r} not found in result.checks")
