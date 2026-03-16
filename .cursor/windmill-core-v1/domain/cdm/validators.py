"""
CDM validators — single source of truth for order state validation.
Uses domain.fsm_guards.STATES; no ru_worker imports.
"""
from __future__ import annotations

from domain.fsm_guards import STATES


def validate_order_state(v: str) -> str:
    if v not in STATES:
        raise ValueError(f"state must be in {STATES}")
    return v
