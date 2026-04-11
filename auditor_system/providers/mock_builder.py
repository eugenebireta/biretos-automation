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

    _DEFAULT_PROPOSAL = "Mock proposal: implement {title} via standard pattern."
    _DEFAULT_REVISION = "Mock revision: addressed {n} critique(s) from auditors."

    def __init__(self, proposal_text: str | None = None, revision_text: str | None = None):
        # Custom text is used as-is (no .format()). Default templates support substitution.
        self._proposal = proposal_text
        self._revision = revision_text

    async def propose(self, task: TaskPack, context: dict[str, Any]) -> str:
        if self._proposal is not None:
            return self._proposal  # custom — return as-is
        return self._DEFAULT_PROPOSAL.format(title=task.title, stage=task.roadmap_stage)

    async def revise(
        self,
        task: TaskPack,
        original_proposal: str,
        critiques: list[AuditVerdict],
        context: dict[str, Any],
    ) -> str:
        if self._revision is not None:
            return self._revision  # custom — return as-is

        # If original_proposal has real code (from --proposal-file),
        # pass it through with a changelog header instead of a stub.
        # This ensures final_audit sees the actual code, not a one-liner.
        critique_summary = []
        for c in critiques:
            for issue in c.issues:
                critique_summary.append(
                    f"- [{issue.severity}] {issue.area}: {issue.description}"
                )

        changelog = "\n".join(critique_summary) if critique_summary else "(no issues raised)"

        return (
            f"## Revision changelog\n"
            f"Addressed {len(critiques)} critique(s):\n{changelog}\n\n"
            f"## AUDITOR NOTE\n"
            f"This is a CODE AUDIT run — the code below is the ACTUAL implementation "
            f"being reviewed. MockBuilder cannot modify code; the original proposal IS "
            f"the deliverable. Audit the code quality, not the revision process.\n\n"
            f"## Source code\n\n"
            f"{original_proposal}"
        )
