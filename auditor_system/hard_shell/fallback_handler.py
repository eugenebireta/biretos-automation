"""
hard_shell/fallback_handler.py — risk-aware fallback on single auditor failure (SPEC §7).

FallbackHandler.handle() → FallbackAction.
ReviewRunner applies the action to decide how to proceed.

Rules:
    CORE:  STOP + owner alert (never continue with one auditor)
    SEMI:  other_result OK → continue batch only; both failed → retry → block
    LOW:   other_result OK → continue one auditor; both failed → retry → one auditor
"""
from __future__ import annotations

import logging
from enum import Enum

from .contracts import AuditVerdict, RiskLevel

logger = logging.getLogger(__name__)


class FallbackAction(str, Enum):
    """Action to take when one or both auditors fail."""

    STOP_OWNER_ALERT = "stop_owner_alert"
    """CORE: halt execution, raise error, notify owner."""

    CONTINUE_ONE_AUDITOR_BATCH_ONLY = "continue_one_auditor_batch_only"
    """SEMI + one OK: continue but force BATCH_APPROVAL (no AUTO_PASS)."""

    RETRY_THEN_BLOCK = "retry_then_block"
    """SEMI + both failed: retry once then BLOCKED."""

    CONTINUE_ONE_AUDITOR = "continue_one_auditor"
    """LOW + one OK: continue with single auditor verdict."""

    RETRY_THEN_ONE_AUDITOR = "retry_then_one_auditor"
    """LOW + both failed: retry once then continue with single auditor."""


class AuditorFailureError(RuntimeError):
    """
    Raised when FallbackHandler returns STOP_OWNER_ALERT or unrecoverable failure.
    Sets run to BLOCKED and halts ReviewRunner.
    """

    def __init__(self, failed_auditor: str, stage: str, reason: str):
        self.failed_auditor = failed_auditor
        self.stage = stage
        self.reason = reason
        super().__init__(
            f"AuditorFailure BLOCKED: auditor={failed_auditor} stage={stage} reason={reason}"
        )


class FallbackHandler:
    """
    Risk-aware fallback for single or dual auditor failure.

    Usage:
        action = handler.handle(risk, failed_id, other_result, stage)
        if action == FallbackAction.STOP_OWNER_ALERT:
            raise AuditorFailureError(...)
    """

    def handle(
        self,
        risk_level: RiskLevel,
        failed_auditor: str,
        other_result: AuditVerdict | None,
        stage: str = "unknown",
    ) -> FallbackAction:
        """
        Returns the action to take given the failure context.

        Args:
            risk_level:    RiskLevel of the current task
            failed_auditor: auditor_id that failed
            other_result:   result from the other auditor (None if both failed)
            stage:          "critique" | "final_audit" (for logging)
        """
        logger.warning(
            "fallback_handler: auditor_failure "
            "risk=%s failed=%s other_ok=%s stage=%s "
            "error_class=TRANSIENT severity=WARNING retriable=true",
            risk_level.value,
            failed_auditor,
            other_result is not None,
            stage,
        )

        if risk_level == RiskLevel.CORE:
            logger.error(
                "fallback_handler: CORE task auditor failed → STOP_OWNER_ALERT "
                "auditor=%s stage=%s",
                failed_auditor, stage,
            )
            return FallbackAction.STOP_OWNER_ALERT

        if risk_level == RiskLevel.SEMI:
            if other_result is not None:
                logger.warning(
                    "fallback_handler: SEMI task one auditor failed → CONTINUE_ONE_AUDITOR_BATCH_ONLY "
                    "auditor=%s stage=%s",
                    failed_auditor, stage,
                )
                return FallbackAction.CONTINUE_ONE_AUDITOR_BATCH_ONLY
            logger.error(
                "fallback_handler: SEMI task both auditors failed → RETRY_THEN_BLOCK "
                "stage=%s",
                stage,
            )
            return FallbackAction.RETRY_THEN_BLOCK

        # LOW
        if other_result is not None:
            logger.warning(
                "fallback_handler: LOW task one auditor failed → CONTINUE_ONE_AUDITOR "
                "auditor=%s stage=%s",
                failed_auditor, stage,
            )
            return FallbackAction.CONTINUE_ONE_AUDITOR

        logger.warning(
            "fallback_handler: LOW task both auditors failed → RETRY_THEN_ONE_AUDITOR "
            "stage=%s",
            stage,
        )
        return FallbackAction.RETRY_THEN_ONE_AUDITOR
