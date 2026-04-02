"""
providers/mock_builder.py — Mock Builder для dry-run.
Не вызывает никаких внешних API.
"""
from __future__ import annotations

from typing import Any

from ..hard_shell.contracts import AuditVerdict, TaskPack
from .base import BuilderProvider


class MockBuilder(BuilderProvider):
    """
    Детерминированный Mock Builder для тестов.
    Возвращает предсказуемые ответы без внешних вызовов.
    """

    def __init__(self, proposal_text: str | None = None, revision_text: str | None = None):
        self._proposal = proposal_text or "Mock proposal: implement {title} via standard pattern."
        self._revision = revision_text or "Mock revision: addressed {n} critique(s) from auditors."

    async def propose(self, task: TaskPack, context: dict[str, Any]) -> str:
        return self._proposal.format(title=task.title, stage=task.roadmap_stage)

    async def revise(
        self,
        task: TaskPack,
        original_proposal: str,
        critiques: list[AuditVerdict],
        context: dict[str, Any],
    ) -> str:
        issue_count = sum(len(c.issues) for c in critiques)
        return self._revision.format(n=len(critiques), issues=issue_count, title=task.title)
