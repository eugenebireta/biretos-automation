"""
hard_shell/quality_gate.py — проверка качества после audit round.

Quality Gate Failed если (SPEC §10.1):
  - Хотя бы один аудитор: reject с critical issue
  - Оба: concerns с 3+ warnings
  - Конфликт: один approve, другой reject
  - Post-audit: регрессия (Tier-1/Tier-2 violation)
"""
from __future__ import annotations

import logging

from .contracts import AuditVerdictValue, AuditVerdict, QualityGateResult

logger = logging.getLogger(__name__)


class QualityGate:
    """
    Принимает список вердиктов аудиторов, возвращает QualityGateResult.
    Детерминированный (SPEC §15 критерий 8).
    """

    def check(self, verdicts: list[AuditVerdict]) -> QualityGateResult:
        if not verdicts:
            return QualityGateResult(
                passed=False,
                reason="no_verdicts: no auditor responses received",
                escalation_needed=True,
            )

        reject_with_critical = [
            v for v in verdicts
            if v.verdict == AuditVerdictValue.REJECT and v.critical_count > 0
        ]
        if reject_with_critical:
            auditor_ids = [v.auditor_id for v in reject_with_critical]
            return QualityGateResult(
                passed=False,
                reason=f"reject_with_critical: {auditor_ids}",
                escalation_needed=True,
                details={
                    "auditors": auditor_ids,
                    "critical_issues": [
                        {"auditor": v.auditor_id, "issues": [i.model_dump() for i in v.issues if i.severity.value == "critical"]}
                        for v in reject_with_critical
                    ],
                },
            )

        # Оба с 3+ warnings
        if len(verdicts) >= 2:
            heavy_concerns = [v for v in verdicts if v.warning_count >= 3]
            if len(heavy_concerns) == len(verdicts):
                return QualityGateResult(
                    passed=False,
                    reason=f"dual_heavy_concerns: both auditors have 3+ warnings",
                    escalation_needed=True,
                    details={"warning_counts": {v.auditor_id: v.warning_count for v in verdicts}},
                )

        # Конфликт: один approve, другой reject
        if len(verdicts) >= 2:
            verdict_set = {v.verdict for v in verdicts}
            if AuditVerdictValue.APPROVE in verdict_set and AuditVerdictValue.REJECT in verdict_set:
                return QualityGateResult(
                    passed=False,
                    reason="conflict: approve vs reject",
                    escalation_needed=True,
                    details={"verdicts": {v.auditor_id: v.verdict.value for v in verdicts}},
                )

        # Прошло
        reject_count = sum(1 for v in verdicts if v.verdict == AuditVerdictValue.REJECT)
        if reject_count > 0:
            # Reject без critical → failed, но может escalate
            return QualityGateResult(
                passed=False,
                reason=f"reject_no_critical: {reject_count} auditor(s) rejected",
                escalation_needed=True,
                details={"reject_count": reject_count},
            )

        logger.info(
            "quality_gate: PASSED verdicts=%s",
            {v.auditor_id: v.verdict.value for v in verdicts},
        )
        return QualityGateResult(
            passed=True,
            reason="all_approved_or_concerns_below_threshold",
            details={"verdicts": {v.auditor_id: v.verdict.value for v in verdicts}},
        )

    def check_post_audit(self, verdicts: list[AuditVerdict]) -> QualityGateResult:
        """
        Post-audit проверка после implementation.
        Более строгая — ловит регрессии.
        """
        result = self.check(verdicts)
        if not result.passed:
            result.reason = "post_audit_regression: " + result.reason
        return result
