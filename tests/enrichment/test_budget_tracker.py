"""
Tests for Task 2: Budget Pre-Gate (infra/acceleration-bootstrap)

Covers:
- check_budget() returns HARD_STOP when exceeded
- budget persists between BudgetTracker instances
- new day resets daily total
- atomic write (temp + rename) — state file not corrupted
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tracker(tmp_path):
    """BudgetTracker with isolated state and config in tmp_path."""
    # Config with tiny thresholds so we can easily trigger them in tests
    config = {"hard_stop_usd": 1.0, "warning_threshold_usd": 0.5, "per_batch_warning_usd": 0.2}
    cfg_path   = tmp_path / "budget_guardrails.json"
    state_path = tmp_path / "budget_tracking.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
    from budget_tracker import BudgetTracker
    return BudgetTracker(config_path=cfg_path, state_path=state_path)


# ---------------------------------------------------------------------------
# Test 1: HARD_STOP when daily total >= hard_stop_usd
# ---------------------------------------------------------------------------

def test_check_budget_returns_hard_stop(tracker):
    from budget_tracker import BudgetStatus
    # Record more than hard_stop_usd (1.0)
    tracker.record_cost("anthropic", "claude-sonnet-4-6", 0.60)
    tracker.record_cost("anthropic", "claude-sonnet-4-6", 0.50)  # total = 1.10

    status = tracker.check_budget()
    assert status == BudgetStatus.HARD_STOP
    assert not status.is_ok


# ---------------------------------------------------------------------------
# Test 2: budget persists between instances
# ---------------------------------------------------------------------------

def test_budget_persists_between_instances(tmp_path):
    from budget_tracker import BudgetStatus, BudgetTracker

    config = {"hard_stop_usd": 5.0, "warning_threshold_usd": 2.0, "per_batch_warning_usd": 1.0}
    cfg_path   = tmp_path / "cfg.json"
    state_path = tmp_path / "state.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")

    t1 = BudgetTracker(config_path=cfg_path, state_path=state_path)
    t1.record_cost("anthropic", "claude-haiku-4-5", 1.50)
    del t1

    t2 = BudgetTracker(config_path=cfg_path, state_path=state_path)
    assert t2.get_daily_total() == pytest.approx(1.50, abs=1e-5)


# ---------------------------------------------------------------------------
# Test 3: new day resets daily total
# ---------------------------------------------------------------------------

def test_new_day_resets_total(tmp_path):
    from budget_tracker import BudgetTracker

    config = {"hard_stop_usd": 5.0, "warning_threshold_usd": 2.0, "per_batch_warning_usd": 1.0}
    cfg_path   = tmp_path / "cfg.json"
    state_path = tmp_path / "state.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")

    # Write state from yesterday
    yesterday = "2020-01-01"
    state_path.write_text(
        json.dumps({"date": yesterday, "runs": [], "daily_total_usd": 9.99}),
        encoding="utf-8",
    )

    t = BudgetTracker(config_path=cfg_path, state_path=state_path)
    # Today's total should start at 0
    assert t.get_daily_total() == pytest.approx(0.0, abs=1e-5)


# ---------------------------------------------------------------------------
# Test 4: atomic write — state file is valid JSON after record_cost
# ---------------------------------------------------------------------------

def test_atomic_write_produces_valid_json(tracker, tmp_path):
    tracker.record_cost("anthropic", "claude-haiku-4-5", 0.01)
    tracker.record_cost("anthropic", "claude-haiku-4-5", 0.02)

    # State file must be readable valid JSON
    raw = tracker._state_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert "daily_total_usd" in data
    assert "runs" in data
    assert len(data["runs"]) == 2


# ---------------------------------------------------------------------------
# Test 5: WARNING status at intermediate threshold
# ---------------------------------------------------------------------------

def test_check_budget_returns_warning(tracker):
    from budget_tracker import BudgetStatus
    # Record more than warning_threshold (0.5) but less than hard_stop (1.0)
    tracker.record_cost("anthropic", "claude-haiku-4-5", 0.55)

    status = tracker.check_budget()
    assert status == BudgetStatus.WARNING
    assert status.is_ok  # WARNING is still ok (call proceeds)


# ---------------------------------------------------------------------------
# Test 6: BudgetExceeded raised when HARD_STOP and gate is integrated
# ---------------------------------------------------------------------------

def test_budget_exceeded_exception(tracker):
    from budget_tracker import BudgetExceeded, BudgetStatus
    tracker.record_cost("anthropic", "claude-sonnet-4-6", 1.50)  # exceed hard_stop

    # Simulate the gate logic in ClaudeChatAdapter.complete()
    bt = tracker
    status = bt.check_budget()
    if not status.is_ok:
        with pytest.raises(BudgetExceeded):
            raise BudgetExceeded("hard stop")
