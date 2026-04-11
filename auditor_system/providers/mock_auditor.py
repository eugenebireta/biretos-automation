"""
providers/mock_auditor.py — Mock Auditor для dry-run.
Поддерживает настройку verdict и issues для тестирования разных сценариев.
"""
from __future__ import annotations

from typing import Any

from ..hard_shell.contracts import (
    AuditIssue,
    AuditVerdict,
    AuditVerdictValue,
    IssueSeverity,
    TaskPack,
)
from .base import AuditorProvider


class MockAuditor(AuditorProvider):
    """
    Детерминированный Mock Auditor.

    Параметры:
        name: идентификатор аудитора ("mock_openai", "mock_anthropic", etc.)
        verdict: "approve" | "concerns" | "reject"
        issues: список AuditIssue
        summary: текст summary
    """

    def __init__(
        self,
        name: str,
        verdict: str = "approve",
        issues: list[AuditIssue] | None = None,
        summary: str | None = None,
    ):
        self.auditor_id = name
        self._verdict = AuditVerdictValue(verdict)
        self._issues = issues or []
        self._summary = summary or f"Mock audit by {name}: {verdict}"

    async def critique(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
    ) -> AuditVerdict:
        return AuditVerdict(
            auditor_id=self.auditor_id,
            verdict=self._verdict,
            summary=self._summary,
            issues=self._issues,
        )

    async def final_audit(
        self,
        revised_proposal: str,
        task: TaskPack,
        context: dict[str, Any],
    ) -> AuditVerdict:
        return AuditVerdict(
            auditor_id=self.auditor_id,
            verdict=self._verdict,
            summary=self._summary + " (final)",
            issues=self._issues,
        )

    async def debate(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
        peer_verdict: AuditVerdict,
    ) -> AuditVerdict:
        return AuditVerdict(
            auditor_id=self.auditor_id,
            verdict=self._verdict,
            summary=self._summary + " (debate)",
            issues=self._issues,
        )


# ---------------------------------------------------------------------------
# Preset сценарии для тестов
# ---------------------------------------------------------------------------

def make_approve_auditor(name: str) -> MockAuditor:
    return MockAuditor(name, verdict="approve", summary=f"{name}: no issues found")


def make_reject_auditor(name: str, critical: bool = True) -> MockAuditor:
    severity = IssueSeverity.CRITICAL if critical else IssueSeverity.WARNING
    return MockAuditor(
        name,
        verdict="reject",
        issues=[AuditIssue(severity=severity, area="architecture", description="Mock critical issue")],
        summary=f"{name}: critical issue found",
    )


def make_concerns_auditor(name: str, warning_count: int = 3) -> MockAuditor:
    issues = [
        AuditIssue(severity=IssueSeverity.WARNING, area="test_coverage", description=f"Warning {i+1}")
        for i in range(warning_count)
    ]
    return MockAuditor(
        name,
        verdict="concerns",
        issues=issues,
        summary=f"{name}: {warning_count} warnings",
    )
