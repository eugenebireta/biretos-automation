"""
hard_shell/approval_router.py — детерминированная маршрутизация результата.

ApprovalRoute (SPEC §9):
  AUTO_PASS        — LOW + оба approve + Quality Gate passed
  BATCH_APPROVAL   — SEMI + approve/concerns + Quality Gate passed
  INDIVIDUAL_REVIEW— CORE, reject, конфликт, Quality Gate failed после Opus
  BLOCKED          — Policy violation, dependency conflict, API failure (CORE)
"""
from __future__ import annotations

import logging

from .contracts import (
    ApprovalRoute,
    AuditVerdictValue,
    AuditVerdict,
    ModelName,
    QualityGateResult,
    RiskLevel,
)

logger = logging.getLogger(__name__)


class ApprovalRouter:
    """
    Детерминированный роутер (SPEC §15 критерий 8).
    Не использует AI для принятия решений о маршрутизации.
    """

    def route(
        self,
        risk: RiskLevel,
        verdicts: list[AuditVerdict],
        gate: QualityGateResult,
        model_used: ModelName,
        policy_violation: bool = False,
        api_failure: bool = False,
    ) -> ApprovalRoute:

        # BLOCKED — всегда первый приоритет
        if policy_violation:
            logger.warning("approval_router: BLOCKED (policy_violation)")
            return ApprovalRoute.BLOCKED

        if api_failure and risk == RiskLevel.CORE:
            logger.warning("approval_router: BLOCKED (api_failure + CORE)")
            return ApprovalRoute.BLOCKED

        # Quality Gate failed после Opus → INDIVIDUAL_REVIEW
        if not gate.passed and model_used == ModelName.OPUS:
            logger.info("approval_router: INDIVIDUAL_REVIEW (gate failed after opus)")
            return ApprovalRoute.INDIVIDUAL_REVIEW

        # Quality Gate failed с Sonnet → нужна escalation (caller обрабатывает)
        # Сюда попадаем только если escalation уже была или caller решил не escalate
        if not gate.passed:
            logger.info("approval_router: INDIVIDUAL_REVIEW (gate failed)")
            return ApprovalRoute.INDIVIDUAL_REVIEW

        # Gate passed — маршрут по risk + verdicts
        if risk == RiskLevel.CORE:
            logger.info("approval_router: INDIVIDUAL_REVIEW (core task)")
            return ApprovalRoute.INDIVIDUAL_REVIEW

        # Проверяем конфликт вердиктов
        verdict_values = {v.verdict for v in verdicts}
        has_reject = AuditVerdictValue.REJECT in verdict_values

        if has_reject:
            logger.info("approval_router: INDIVIDUAL_REVIEW (has reject)")
            return ApprovalRoute.INDIVIDUAL_REVIEW

        if risk == RiskLevel.LOW:
            # LOW + оба approve/concerns + gate passed → AUTO_PASS
            logger.info("approval_router: AUTO_PASS")
            return ApprovalRoute.AUTO_PASS

        # SEMI
        logger.info("approval_router: BATCH_APPROVAL")
        return ApprovalRoute.BATCH_APPROVAL

    def build_owner_summary(
        self,
        route: ApprovalRoute,
        risk: RiskLevel,
        verdicts: list[AuditVerdict],
        gate: QualityGateResult,
        task_title: str,
        roadmap_stage: str,
        model_used: ModelName,
        escalated: bool,
    ) -> str:
        """Генерирует owner_summary.md — читаемый человеком итог прогона."""
        lines = [
            f"# Owner Summary",
            f"",
            f"**Task:** {task_title}",
            f"**Stage:** {roadmap_stage}",
            f"**Risk:** {risk.value.upper()}",
            f"**Route:** `{route.value}`",
            f"**Model:** {model_used.value}" + (" (escalated from sonnet)" if escalated else ""),
            f"",
            f"## Audit Results",
        ]

        for v in verdicts:
            icon = {"approve": "✅", "concerns": "⚠️", "reject": "❌"}.get(v.verdict.value, "?")
            lines.append(f"- **{v.auditor_id}**: {icon} {v.verdict.value.upper()}")
            if v.summary:
                lines.append(f"  > {v.summary}")
            for issue in v.issues:
                sev_icon = {"critical": "🔴", "warning": "🟡", "info": "ℹ️"}.get(issue.severity.value, "")
                lines.append(f"  - {sev_icon} [{issue.area}] {issue.description}")

        lines += [
            f"",
            f"## Quality Gate",
            f"**Passed:** {'✅ Yes' if gate.passed else '❌ No'}",
            f"**Reason:** {gate.reason}",
            f"",
            f"## Action Required",
        ]

        if route == ApprovalRoute.AUTO_PASS:
            lines.append("✅ **AUTO_PASS** — branch ready, no action needed (merge after batch approval when enabled)")
        elif route == ApprovalRoute.BATCH_APPROVAL:
            lines.append("📦 **BATCH_APPROVAL** — add to next batch pack for owner review")
        elif route == ApprovalRoute.INDIVIDUAL_REVIEW:
            lines.append("👤 **INDIVIDUAL_REVIEW** — requires owner review before merge")
        elif route == ApprovalRoute.BLOCKED:
            lines.append("🚫 **BLOCKED** — do not proceed, owner action required")

        return "\n".join(lines)
