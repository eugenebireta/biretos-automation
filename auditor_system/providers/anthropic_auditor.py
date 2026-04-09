"""
providers/anthropic_auditor.py — Claude auditor via Claude Code CLI.

Routes all Claude audit calls through `claude -p` (Claude Code CLI),
using the user's $200/mo subscription instead of API balance.

Previously used Anthropic Messages API directly (SPEC §20.8).
Switched to CLI to eliminate per-token API costs for auditor calls.
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any

from ..hard_shell.contracts import AuditVerdict, TaskPack
from ..hard_shell.schema_validator import validate_and_parse
from .base import AuditorProvider
# Reuse prompt builders from openai_auditor (same system/user prompt format)
from .openai_auditor import _build_system_prompt, _build_user_prompt

logger = logging.getLogger(__name__)

# Ensure orchestrator dir is on path for claude_cli import
_ORCH_DIR = str(Path(__file__).resolve().parent.parent.parent / "orchestrator")
if _ORCH_DIR not in sys.path:
    sys.path.insert(0, _ORCH_DIR)


class AnthropicAuditor(AuditorProvider):
    """
    Auditor using Claude Code CLI (`claude -p`).

    All calls go through the user's Claude Code subscription,
    not the Anthropic API balance. The api_key parameter is kept
    for interface compatibility but is not used for CLI calls.
    """

    auditor_id = "anthropic"

    def __init__(
        self,
        model: str = "claude-sonnet-4-6-20250514",
        api_key: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ):
        # api_key kept for interface compat but not used (CLI uses subscription)
        self.model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    def _extract_json(self, text: str) -> str:
        """
        Extracts JSON from response text.
        Handles raw JSON and markdown code fences (```json ... ```).
        """
        text = text.strip()

        # Try raw JSON first
        if text.startswith("{"):
            return text

        # Try markdown code fence: ```json ... ```
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            return fence_match.group(1)

        # Last resort: find first { to last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]

        return text  # Let validate_and_parse handle the parse error

    async def _call(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
        stage: str,
    ) -> AuditVerdict:
        system_prompt = _build_system_prompt(context)
        # Add JSON instruction since CLI output is free-form text
        user_prompt = (
            _build_user_prompt(proposal, task, stage, context)
            + "\n\nReturn ONLY a JSON object matching the schema above. No prose outside JSON."
        )

        logger.info(
            "anthropic_auditor: calling CLI task_id=%s stage=%s",
            task.task_id, stage,
        )

        from claude_cli import call_claude_async
        raw_text = await call_claude_async(
            user_prompt,
            system_prompt=system_prompt,
            timeout=180,  # auditor prompts can be large
        )

        logger.info(
            "anthropic_auditor: response received task_id=%s stage=%s len=%d",
            task.task_id, stage, len(raw_text),
        )

        json_text = self._extract_json(raw_text)
        verdict = validate_and_parse("anthropic", json_text)
        logger.info(
            "anthropic_auditor: verdict=%s critical=%d warnings=%d task_id=%s",
            verdict.verdict.value, verdict.critical_count, verdict.warning_count, task.task_id,
        )
        return verdict

    async def critique(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
    ) -> AuditVerdict:
        return await self._call(proposal, task, context, stage="proposal")

    async def final_audit(
        self,
        revised_proposal: str,
        task: TaskPack,
        context: dict[str, Any],
    ) -> AuditVerdict:
        return await self._call(revised_proposal, task, context, stage="revised_proposal")
