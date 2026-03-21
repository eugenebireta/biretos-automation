"""
Tests for domain/backoffice_risk_registry.py — Phase 6.4.
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

from domain.backoffice_models import RiskLevel
from domain.backoffice_risk_registry import classify_intent_risk


def test_check_payment_is_low():
    assert classify_intent_risk("check_payment") == RiskLevel.LOW


def test_get_tracking_is_low():
    assert classify_intent_risk("get_tracking") == RiskLevel.LOW


def test_get_waybill_is_medium():
    assert classify_intent_risk("get_waybill") == RiskLevel.MEDIUM


def test_unknown_intent_raises_value_error():
    with pytest.raises(ValueError, match="unknown intent_type"):
        classify_intent_risk("send_invoice")


def test_empty_intent_raises_value_error():
    with pytest.raises(ValueError):
        classify_intent_risk("")
