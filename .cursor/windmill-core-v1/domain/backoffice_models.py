"""
Backoffice Task Engine — domain models. Phase 6.2.

EmployeeRole + Permission matrix, rate limit config, BackofficeTaskIntent.
Pure models only — no DB, no side-effects, no Tier-1 imports.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, FrozenSet, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Role + Permission
# ---------------------------------------------------------------------------

class EmployeeRole(str, Enum):
    OPERATOR = "operator"   # read-only: payment status + tracking
    MANAGER  = "manager"    # + waybill download
    ADMIN    = "admin"      # all backoffice intents


class Permission(str, Enum):
    CHECK_PAYMENT = "check_payment"
    GET_TRACKING  = "get_tracking"
    GET_WAYBILL   = "get_waybill"
    SEND_INVOICE  = "send_invoice"


ROLE_PERMISSIONS: Dict[EmployeeRole, FrozenSet[Permission]] = {
    EmployeeRole.OPERATOR: frozenset({
        Permission.CHECK_PAYMENT,
        Permission.GET_TRACKING,
        Permission.GET_WAYBILL,
        Permission.SEND_INVOICE,
    }),
    EmployeeRole.MANAGER: frozenset({
        Permission.CHECK_PAYMENT,
        Permission.GET_TRACKING,
        Permission.GET_WAYBILL,
        Permission.SEND_INVOICE,
    }),
    EmployeeRole.ADMIN: frozenset({
        Permission.CHECK_PAYMENT,
        Permission.GET_TRACKING,
        Permission.GET_WAYBILL,
        Permission.SEND_INVOICE,
    }),
}


# ---------------------------------------------------------------------------
# Intent risk classification (used by IntentRiskRegistry)
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


INTENT_RISK: Dict[str, RiskLevel] = {
    "check_payment": RiskLevel.LOW,
    "get_tracking":  RiskLevel.LOW,
    "get_waybill":   RiskLevel.MEDIUM,
    "send_invoice":  RiskLevel.HIGH,
}


# ---------------------------------------------------------------------------
# Rate limits per risk level (calls/hour per employee)
# Configurable via BACKOFFICE_RATE_LIMIT_LOW_PER_HOUR /
#                  BACKOFFICE_RATE_LIMIT_MEDIUM_PER_HOUR
# ---------------------------------------------------------------------------

DEFAULT_RATE_LIMITS: Dict[RiskLevel, int] = {
    RiskLevel.LOW:    100,
    RiskLevel.MEDIUM: 20,
    RiskLevel.HIGH:   5,
}

RATE_WINDOW_SECONDS: int = 3600  # 1 hour


# ---------------------------------------------------------------------------
# BackofficeTaskIntent — Pydantic model for inbound employee requests
# Separate from TaskIntent (pinned API) to avoid touching frozen signatures.
# ---------------------------------------------------------------------------

class BackofficeTaskIntent(BaseModel):
    """
    Employee-initiated backoffice request entering the Backoffice Router.

    Required fields:
      trace_id      — must be non-empty (Fail Loud, same rule as TaskIntent)
      intent_type   — one of the 3 supported intents
      employee_id   — opaque identifier (Telegram user_id, email, etc.)
      employee_role — EmployeeRole string
      payload       — intent-specific parameters (e.g. invoice_id, tracking_id)

    idempotency_key is auto-derived if not supplied:
      "{intent_type}:{trace_id}"
    """

    trace_id:        str = Field(..., min_length=1)
    intent_type:     str
    employee_id:     str = Field(..., min_length=1)
    employee_role:   str
    payload:         Dict[str, Any] = Field(default_factory=dict)
    metadata:        Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None

    def effective_idempotency_key(self) -> str:
        return self.idempotency_key or f"{self.intent_type}:{self.trace_id}"

    def effective_role(self) -> Optional[EmployeeRole]:
        try:
            return EmployeeRole(self.employee_role)
        except ValueError:
            return None
