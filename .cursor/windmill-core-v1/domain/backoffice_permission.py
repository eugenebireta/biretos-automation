"""
Backoffice Permission Guard. Phase 6.2.

Pure function — no DB, no side-effects.
Raises GuardianVeto on permission violation.
"""

from __future__ import annotations

from .backoffice_models import (
    BackofficeTaskIntent,
    EmployeeRole,
    Permission,
    ROLE_PERMISSIONS,
)
from .guardian import GuardianVeto

# Map intent_type string → Permission enum
_INTENT_PERMISSION: dict[str, Permission] = {
    "check_payment": Permission.CHECK_PAYMENT,
    "get_tracking":  Permission.GET_TRACKING,
    "get_waybill":   Permission.GET_WAYBILL,
}

SUPPORTED_INTENTS: frozenset[str] = frozenset(_INTENT_PERMISSION)


def guard_employee_intent(intent: BackofficeTaskIntent) -> None:
    """
    Raises GuardianVeto if:
      - intent_type is not in SUPPORTED_INTENTS
      - employee_role is not a valid EmployeeRole
      - role does not have the required permission for this intent

    Called by backoffice_router BEFORE any external call.
    """
    # 1. Intent type must be known
    if intent.intent_type not in SUPPORTED_INTENTS:
        raise GuardianVeto(
            reason=f"intent_type '{intent.intent_type}' is not a supported backoffice intent",
            invariant="INV-INTENT-WHITELIST",
        )

    # 2. Role must be valid
    role = intent.effective_role()
    if role is None:
        raise GuardianVeto(
            reason=f"employee_role '{intent.employee_role}' is not a valid EmployeeRole",
            invariant="INV-ROLE-UNKNOWN",
        )

    # 3. Role must have the required permission
    required = _INTENT_PERMISSION[intent.intent_type]
    allowed = ROLE_PERMISSIONS.get(role, frozenset())
    if required not in allowed:
        raise GuardianVeto(
            reason=(
                f"role '{role.value}' does not have permission "
                f"'{required.value}' for intent '{intent.intent_type}'"
            ),
            invariant="INV-PERMISSION-DENIED",
        )
