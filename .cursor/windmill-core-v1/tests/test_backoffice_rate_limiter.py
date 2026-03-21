"""
Tests for domain/backoffice_rate_limiter.py + guardian INV-RATE. Phase 6.10.
Pure unit tests: stub DB cursor, deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

import pytest

from domain.backoffice_models import RiskLevel
from domain.backoffice_rate_limiter import check_rate_limit
from domain.guardian import GuardianVeto, guard_backoffice_rate_limit


# ---------------------------------------------------------------------------
# Stub DB
# ---------------------------------------------------------------------------

class _StubCursor:
    def __init__(self, count: int) -> None:
        self._count = count

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return (self._count,)

    def close(self):
        pass


class _StubConn:
    def __init__(self, count: int) -> None:
        self._count = count

    def cursor(self):
        return _StubCursor(self._count)


# ---------------------------------------------------------------------------
# check_rate_limit
# ---------------------------------------------------------------------------

def test_within_limit_allowed():
    conn = _StubConn(count=5)
    result = check_rate_limit(conn, employee_id="emp-1", intent_type="check_payment", risk_level=RiskLevel.LOW)
    assert result.allowed is True
    assert result.current_count == 5
    assert result.limit == 100


def test_at_limit_not_allowed():
    """current == limit → not allowed."""
    conn = _StubConn(count=100)
    result = check_rate_limit(conn, employee_id="emp-1", intent_type="check_payment", risk_level=RiskLevel.LOW)
    assert result.allowed is False


def test_over_limit_not_allowed():
    conn = _StubConn(count=150)
    result = check_rate_limit(conn, employee_id="emp-1", intent_type="check_payment", risk_level=RiskLevel.LOW)
    assert result.allowed is False
    assert result.current_count == 150


def test_medium_risk_lower_limit():
    conn = _StubConn(count=19)
    result = check_rate_limit(conn, employee_id="emp-2", intent_type="get_waybill", risk_level=RiskLevel.MEDIUM)
    assert result.allowed is True
    assert result.limit == 20


def test_medium_risk_at_limit():
    conn = _StubConn(count=20)
    result = check_rate_limit(conn, employee_id="emp-2", intent_type="get_waybill", risk_level=RiskLevel.MEDIUM)
    assert result.allowed is False


def test_result_carries_employee_and_intent():
    conn = _StubConn(count=0)
    result = check_rate_limit(conn, employee_id="emp-99", intent_type="get_tracking", risk_level=RiskLevel.LOW)
    assert result.employee_id == "emp-99"
    assert result.intent_type == "get_tracking"
    assert result.risk_level == "LOW"


# ---------------------------------------------------------------------------
# guard_backoffice_rate_limit
# ---------------------------------------------------------------------------

def test_guard_passes_when_allowed():
    conn = _StubConn(count=0)
    result = check_rate_limit(conn, employee_id="emp-1", intent_type="check_payment", risk_level=RiskLevel.LOW)
    guard_backoffice_rate_limit(result)  # must not raise


def test_guard_raises_veto_when_exceeded():
    conn = _StubConn(count=200)
    result = check_rate_limit(conn, employee_id="emp-1", intent_type="check_payment", risk_level=RiskLevel.LOW)
    with pytest.raises(GuardianVeto) as exc_info:
        guard_backoffice_rate_limit(result)
    assert exc_info.value.invariant == "INV-RATE"
    assert "emp-1" in exc_info.value.reason
    assert "check_payment" in exc_info.value.reason


def test_guard_veto_message_contains_counts():
    conn = _StubConn(count=150)
    result = check_rate_limit(conn, employee_id="emp-x", intent_type="get_waybill", risk_level=RiskLevel.MEDIUM)
    with pytest.raises(GuardianVeto) as exc_info:
        guard_backoffice_rate_limit(result)
    reason = exc_info.value.reason
    assert "150" in reason
    assert "20" in reason
