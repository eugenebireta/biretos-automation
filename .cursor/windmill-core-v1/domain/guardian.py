"""
Guardian — hardcoded invariant validation layer.  Task 5.4.

Performs deterministic business-invariant checks BEFORE mutations.
These checks are hardcoded and cannot be disabled or bypassed.

Guardian is separate from Pydantic schema validation (Task 5.2/5.3).
Pydantic validates structure.  Guardian validates business invariants.

Usage:
    from domain.guardian import guard_task_intent, guard_action_snapshot, GuardianVeto
    guard_task_intent(intent)        # raises GuardianVeto on violation
    guard_action_snapshot(snapshot)  # raises GuardianVeto on violation
"""
from __future__ import annotations

from typing import TYPE_CHECKING, FrozenSet

from .cdm_models import ActionSnapshot, TaskIntent

if TYPE_CHECKING:
    from .backoffice_rate_limiter import RateLimitResult
    from .assistant_models import ConfirmationPending

# ---------------------------------------------------------------------------
# Whitelists
# ---------------------------------------------------------------------------

ALLOWED_ACTION_TYPES: FrozenSet[str] = frozenset(
    {
        "cdek_shipment",
        "tbank_payment",
        "tbank_invoice_status",
        "tbank_invoices_list",
        "ship_paid",
        "auto_ship_all_paid",
        "governance_execute",
        "governance_case_create",
        # Phase 6 — Backoffice Task Engine
        "check_payment",
        "get_tracking",
        "get_waybill",
        # Phase 7 — AI Executive Assistant NLU
        "nlu_parse",
        "nlu_confirm",
    }
)

SUPPORTED_LEAF_WORKERS: FrozenSet[str] = frozenset({"cdek_shipment"})


# ---------------------------------------------------------------------------
# Veto exception
# ---------------------------------------------------------------------------


class GuardianVeto(Exception):
    """Raised when Guardian rejects an operation.  Always PERMANENT/non-retriable."""

    def __init__(self, *, reason: str, invariant: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.invariant = invariant


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def guard_task_intent(intent: TaskIntent) -> None:
    """
    Hardcoded invariant checks for TaskIntent.

    Raises GuardianVeto when any invariant is violated.
    Called by dispatch_action() BEFORE any side-effects.
    """
    if intent.action_type not in ALLOWED_ACTION_TYPES:
        raise GuardianVeto(
            reason=f"action_type '{intent.action_type}' is not in ALLOWED_ACTION_TYPES",
            invariant="INV-ACTION-WHITELIST",
        )


def guard_backoffice_rate_limit(rate_result: "RateLimitResult") -> None:
    """
    Raises GuardianVeto(INV-RATE) when an employee has exceeded their
    per-hour rate limit for a given intent type.

    Called by backoffice_router AFTER check_rate_limit().
    """
    if not rate_result.allowed:
        raise GuardianVeto(
            reason=(
                f"rate limit exceeded for employee '{rate_result.employee_id}' "
                f"on intent '{rate_result.intent_type}': "
                f"{rate_result.current_count}/{rate_result.limit} "
                f"calls in the last hour (risk={rate_result.risk_level})"
            ),
            invariant="INV-RATE",
        )


def guard_nlu_confirmation(pending: "ConfirmationPending") -> None:
    """
    Raises GuardianVeto(INV-MBC) if the confirmation row does not represent
    a valid, employee-originated intent.

    Called by confirm_nlu_intent() AFTER atomic consume from DB.
    This is the last hardcoded check before backoffice execution.
    """
    if not pending.parsed_intent_type:
        raise GuardianVeto(
            reason="nlu confirmation has empty intent_type — INV-MBC",
            invariant="INV-MBC",
        )
    if not pending.employee_id:
        raise GuardianVeto(
            reason="nlu confirmation has empty employee_id — INV-MBC",
            invariant="INV-MBC",
        )


def guard_action_snapshot(snapshot: ActionSnapshot) -> None:
    """
    Hardcoded invariant checks for ActionSnapshot.

    Raises GuardianVeto when any invariant is violated.
    Called by governance_executor BEFORE leaf worker execution.

    Note: leaf_worker_type is already constrained to Literal["cdek_shipment"]
    by Pydantic.  The check here is defense-in-depth for future expansion.
    """
    if not snapshot.external_idempotency_key:
        raise GuardianVeto(
            reason="external_idempotency_key must be non-empty (INV-IDEM)",
            invariant="INV-IDEM",
        )
    if snapshot.leaf_worker_type not in SUPPORTED_LEAF_WORKERS:
        raise GuardianVeto(
            reason=(
                f"leaf_worker_type '{snapshot.leaf_worker_type}' "
                f"not in SUPPORTED_LEAF_WORKERS"
            ),
            invariant="INV-LEAF-WORKER",
        )
