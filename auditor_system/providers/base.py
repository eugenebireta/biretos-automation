"""
providers/base.py — абстрактные интерфейсы BuilderProvider и AuditorProvider.

Роли постоянны. Модели меняются. Провайдеры — pluggable (SPEC §3.2).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..hard_shell.contracts import AuditVerdict, TaskPack


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
