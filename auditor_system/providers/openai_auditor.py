"""
providers/openai_auditor.py — OpenAI Responses API + Structured Outputs (заглушка).

Реализуется в Phase 2. Сейчас — интерфейс + TODO.
Использовать: Responses API + json_schema (НЕ старый Chat Completions + JSON mode).
Structured Outputs гарантируют валидность JSON (SPEC §20.8).
"""
from __future__ import annotations

from typing import Any

from ..hard_shell.contracts import AuditVerdict, TaskPack
from .base import AuditorProvider


class OpenAIAuditor(AuditorProvider):
    """
    Аудитор на базе OpenAI Responses API.
    Phase 2 — пока заглушка.
    """

    auditor_id = "openai"

    def __init__(self, model: str = "gpt-4o", api_key: str | None = None):
        self.model = model
        self._api_key = api_key  # НЕ логировать (DNA §7)
        # TODO Phase 2: инициализировать openai client
        # import openai
        # self._client = openai.AsyncOpenAI(api_key=api_key)

    async def critique(self, proposal: str, task: TaskPack, context: dict[str, Any]) -> AuditVerdict:
        # TODO Phase 2: вызов Responses API + json_schema
        raise NotImplementedError("OpenAIAuditor not implemented yet (Phase 2)")

    async def final_audit(self, revised_proposal: str, task: TaskPack, context: dict[str, Any]) -> AuditVerdict:
        raise NotImplementedError("OpenAIAuditor not implemented yet (Phase 2)")
