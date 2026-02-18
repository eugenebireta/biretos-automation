"""
FSM Transition Guards -- single source of truth for allowed state transitions.

Used by:
- ru_worker/fsm_v2.py (FSM engine)
- domain/shipment_service.py (direct state mutation guard)
- tests/validation/test_hardening_guards.py (contract tests)
"""
from __future__ import annotations

from typing import Dict


STATES = {
    "draft",
    "pending_invoice",
    "invoice_created",
    "partially_paid",
    "paid",
    "shipment_pending",
    "partially_shipped",
    "shipped",
    "completed",
    "cancelled",
    "failed",
    "pending_approval",
    "quarantined",
    "human_decision_timeout",
    "quarantine_expired",
    # legacy compatibility
    "shipment_created",
    "consignment_registered",
}

TERMINAL_STATES = {"completed", "cancelled", "human_decision_timeout", "quarantine_expired"}

ALLOWED_TRANSITIONS: Dict[str, list] = {
    "draft": ["pending_invoice", "pending_approval", "quarantined", "cancelled", "failed"],
    "pending_invoice": ["invoice_created", "pending_approval", "quarantined", "cancelled", "failed"],
    "invoice_created": ["partially_paid", "paid", "pending_approval", "quarantined", "cancelled", "failed"],
    "partially_paid": ["paid", "pending_approval", "quarantined", "cancelled", "failed"],
    "paid": ["shipment_pending", "partially_shipped", "shipped", "pending_approval", "quarantined", "cancelled", "failed"],
    "shipment_pending": ["partially_shipped", "shipped", "pending_approval", "quarantined", "failed"],
    "partially_shipped": ["partially_shipped", "shipped", "pending_approval", "quarantined", "failed"],
    "shipped": ["completed", "pending_approval", "quarantined", "failed"],
    "pending_approval": [
        "pending_invoice",
        "invoice_created",
        "paid",
        "shipment_pending",
        "quarantined",
        "cancelled",
        "failed",
        "human_decision_timeout",
    ],
    "quarantined": [
        "pending_invoice",
        "invoice_created",
        "paid",
        "shipment_pending",
        "cancelled",
        "failed",
        "quarantine_expired",
    ],
    "completed": [],
    "cancelled": [],
    "human_decision_timeout": [],
    "quarantine_expired": [],
    "failed": ["pending_invoice", "shipment_pending"],
    # legacy
    "shipment_created": ["consignment_registered", "shipped", "failed"],
    "consignment_registered": ["completed", "failed"],
}


def validate_transition(from_state: str, to_state: str) -> bool:
    """Pure function: returns True if transition is valid per FSM rules."""
    if from_state == to_state:
        return True  # idempotent
    return to_state in ALLOWED_TRANSITIONS.get(from_state, [])
