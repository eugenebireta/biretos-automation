"""
Tests for domain/backoffice_permission.py — Phase 6.2.
Pure unit tests: no DB, no external I/O, deterministic.
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

from domain.backoffice_models import BackofficeTaskIntent
from domain.backoffice_permission import guard_employee_intent
from domain.guardian import GuardianVeto


def _intent(intent_type: str, role: str) -> BackofficeTaskIntent:
    return BackofficeTaskIntent(
        trace_id="test-trace-001",
        intent_type=intent_type,
        employee_id="emp-1",
        employee_role=role,
        payload={},
    )


# ---------------------------------------------------------------------------
# OPERATOR permissions
# ---------------------------------------------------------------------------

def test_operator_can_check_payment():
    guard_employee_intent(_intent("check_payment", "operator"))


def test_operator_can_get_tracking():
    guard_employee_intent(_intent("get_tracking", "operator"))


def test_operator_cannot_get_waybill():
    with pytest.raises(GuardianVeto) as exc_info:
        guard_employee_intent(_intent("get_waybill", "operator"))
    assert exc_info.value.invariant == "INV-PERMISSION-DENIED"


# ---------------------------------------------------------------------------
# MANAGER permissions
# ---------------------------------------------------------------------------

def test_manager_can_check_payment():
    guard_employee_intent(_intent("check_payment", "manager"))


def test_manager_can_get_tracking():
    guard_employee_intent(_intent("get_tracking", "manager"))


def test_manager_can_get_waybill():
    guard_employee_intent(_intent("get_waybill", "manager"))


# ---------------------------------------------------------------------------
# ADMIN permissions
# ---------------------------------------------------------------------------

def test_admin_can_check_payment():
    guard_employee_intent(_intent("check_payment", "admin"))


def test_admin_can_get_tracking():
    guard_employee_intent(_intent("get_tracking", "admin"))


def test_admin_can_get_waybill():
    guard_employee_intent(_intent("get_waybill", "admin"))


# ---------------------------------------------------------------------------
# Unknown / invalid role
# ---------------------------------------------------------------------------

def test_unknown_role_raises_veto():
    with pytest.raises(GuardianVeto) as exc_info:
        guard_employee_intent(_intent("check_payment", "superuser"))
    assert exc_info.value.invariant == "INV-ROLE-UNKNOWN"


# ---------------------------------------------------------------------------
# Unknown intent type
# ---------------------------------------------------------------------------

def test_unknown_intent_raises_veto():
    with pytest.raises(GuardianVeto) as exc_info:
        guard_employee_intent(_intent("send_invoice", "admin"))
    assert exc_info.value.invariant == "INV-INTENT-WHITELIST"


def test_empty_intent_type_raises_veto():
    with pytest.raises(GuardianVeto):
        guard_employee_intent(_intent("", "admin"))
