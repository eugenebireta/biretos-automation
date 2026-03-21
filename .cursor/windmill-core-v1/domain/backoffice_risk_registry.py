"""
Backoffice Intent Risk Registry. Phase 6.4.

Pure lookup — no DB, no side-effects.
Returns RiskLevel for a given intent_type.
"""

from __future__ import annotations

from .backoffice_models import INTENT_RISK, RiskLevel


def classify_intent_risk(intent_type: str) -> RiskLevel:
    """
    Return the risk level for intent_type.

    Raises ValueError for unknown intent types (Fail Loud).
    Caller must have already passed guard_employee_intent() which
    validates intent_type is in SUPPORTED_INTENTS.
    """
    level = INTENT_RISK.get(intent_type)
    if level is None:
        raise ValueError(
            f"classify_intent_risk: unknown intent_type '{intent_type}'. "
            f"Known: {sorted(INTENT_RISK)}"
        )
    return level
