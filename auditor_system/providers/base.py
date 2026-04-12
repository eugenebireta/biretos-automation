"""
providers/base.py — абстрактные интерфейсы BuilderProvider и AuditorProvider.

Роли постоянны. Модели меняются. Провайдеры — pluggable (SPEC §3.2).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..hard_shell.contracts import AuditVerdict, DefectRegister, L2Report, RepairEntry, TaskPack


class BuilderProvider(ABC):
    """Абстракция Builder (Claude Code / Codex / любой другой)."""

    @abstractmethod
    async def propose(self, task: TaskPack, context: dict[str, Any]) -> str:
        """Генерирует первоначальный proposal по задаче."""
        ...

    @abstractmethod
    async def revise(
        self,
        task: TaskPack,
        original_proposal: str,
        critiques: list[AuditVerdict],
        context: dict[str, Any],
    ) -> str:
        """Ревизия proposal на основе critique от аудиторов."""
        ...

    async def repair(
        self,
        task: TaskPack,
        current_proposal: str,
        defect_register: DefectRegister,
        repair_prompt: str,
        context: dict[str, Any],
    ) -> tuple[str, list[RepairEntry]]:
        """
        Consensus Pipeline Protocol v1: structured repair pass.

        Receives a targeted repair_prompt (generated from defect register, not raw critique).
        Returns: (repaired_proposal, repair_manifest).

        Default implementation: delegates to revise() for backward compat.
        Override for proper repair_manifest generation.
        """
        repaired = await self.revise(task, current_proposal, [], context)
        # Minimal manifest: mark all open defects as FIXED (mock behavior)
        manifest = [
            RepairEntry(
                defect_id=d.defect_id,
                action="FIXED",
                changes=["(MockBuilder: repair via revise fallback)"],
            )
            for d in defect_register.open_blockers
        ]
        return repaired, manifest


class AuditorProvider(ABC):
    """Абстракция Auditor (OpenAI API / Anthropic API)."""

    auditor_id: str  # "openai" | "anthropic" | "mock_*"

    @abstractmethod
    async def critique(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
    ) -> AuditVerdict:
        """
        Первый раунд критики proposal.
        Аудиторы не видят друг друга (SPEC §4, шаг 5).
        """
        ...

    @abstractmethod
    async def final_audit(
        self,
        revised_proposal: str,
        task: TaskPack,
        context: dict[str, Any],
    ) -> AuditVerdict:
        """Финальный аудит после revision."""
        ...

    async def debate(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
        peer_verdict: AuditVerdict,
    ) -> AuditVerdict:
        """
        Round 2 debate: re-audit with visibility into peer's Round 1 verdict.

        Default: delegates to final_audit (backwards compatible).
        Override in concrete providers for proper debate prompt.
        """
        return await self.final_audit(proposal, task, context)

    async def re_review(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
        defect_register: DefectRegister,
        repair_manifest: list[RepairEntry],
        l2_report: L2Report,
        original_diff: str = "",
    ) -> AuditVerdict:
        """
        Consensus Pipeline Protocol v1: re-review after builder repair.

        Critic receives:
          - Updated proposal/diff
          - Full defect register (ALL issues, not just own)
          - Repair manifest (builder's per-defect response)
          - New L2Report (execution evidence)
          - Original diff anchor (to detect regressions)

        Default: builds re_review context and delegates to final_audit.
        Override for proper structured checklist response.
        """
        from ..debate import build_re_review_context
        re_review_ctx = build_re_review_context(
            context,
            defect_register,
            repair_manifest,
            l2_report,
            original_diff,
        )
        return await self.final_audit(proposal, task, re_review_ctx)
