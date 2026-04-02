"""
providers/anthropic_auditor.py — Anthropic Messages API (заглушка).

Реализуется в Phase 2.

ВАЖНО (SPEC §20.8):
  Builder (Claude Code) работает БЕЗ ANTHROPIC_API_KEY в env → подписка Max.
  Auditor (этот модуль) вызывается С ANTHROPIC_API_KEY → API billing (pay-per-use).
  Это РАЗНЫЕ окружения. Если ANTHROPIC_API_KEY есть в env Claude Code →
  он переключается на API-billing вместо подписки. Это дорого.
  Запускать review_runner в отдельном процессе без Claude Code env.
"""
from __future__ import annotations

from typing import Any

from ..hard_shell.contracts import AuditVerdict, TaskPack
from .base import AuditorProvider


class AnthropicAuditor(AuditorProvider):
    """
    Аудитор на базе Anthropic Messages API.
    Phase 2 — пока заглушка.
    """

    auditor_id = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None):
        self.model = model
        self._api_key = api_key  # НЕ логировать (DNA §7)
        # TODO Phase 2: инициализировать anthropic client
        # import anthropic
        # self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def critique(self, proposal: str, task: TaskPack, context: dict[str, Any]) -> AuditVerdict:
        # TODO Phase 2: вызов Messages API
        raise NotImplementedError("AnthropicAuditor not implemented yet (Phase 2)")

    async def final_audit(self, revised_proposal: str, task: TaskPack, context: dict[str, Any]) -> AuditVerdict:
        raise NotImplementedError("AnthropicAuditor not implemented yet (Phase 2)")
