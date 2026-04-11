"""
providers/anthropic_auditor.py — Anthropic Messages API (SPEC §20.8).

IMPORTANT (SPEC §20.8):
  Builder (Claude Code) works WITHOUT ANTHROPIC_API_KEY in env → Max subscription.
  Auditor (this module) is called WITH ANTHROPIC_API_KEY → API billing (pay-per-use).
  These are DIFFERENT environments. If ANTHROPIC_API_KEY leaks to Claude Code env →
  it switches to API billing. NEVER use load_dotenv() or os.environ for this key.

API key passed directly to client from dotenv_values("auditor_system/config/.env.auditors").
System prompt built dynamically from ContextAssembler context (SPEC §19.4).
"""
from __future__ import annotations

import logging
from typing import Any

from ..hard_shell.contracts import AuditVerdict, TaskPack
from ..hard_shell.schema_validator import validate_and_parse
from .base import AuditorProvider
# Reuse prompt builders from openai_auditor (same system/user prompt format)
from .openai_auditor import _build_system_prompt, _build_user_prompt

logger = logging.getLogger(__name__)


class AnthropicAuditor(AuditorProvider):
    """
    Auditor using Anthropic Messages API.
    API key passed directly — NOT from os.environ (SPEC §20.8).

    Response parsing: JSON extracted from text content with fallback on
    markdown code fences.
    """

    auditor_id = "anthropic"

    def __init__(
        self,
        model: str = "claude-sonnet-4-6-20250514",
        api_key: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ):
        if not api_key:
            raise ValueError("AnthropicAuditor: api_key is required (SPEC §20.8)")
        self.model = model
        self._api_key = api_key  # NEVER log (DNA §7)
        self._max_tokens = max_tokens
        self._temperature = temperature
        # Lazy import to avoid import errors when anthropic not installed
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

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
        import re
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
        # Anthropic: add JSON instruction to user prompt since no Structured Outputs
        user_prompt = (
            _build_user_prompt(proposal, task, stage, context)
            + "\n\nReturn ONLY a JSON object matching the schema above. No prose outside JSON."
        )

        logger.info(
            "anthropic_auditor: calling API model=%s task_id=%s stage=%s",
            self.model, task.task_id, stage,
        )

        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=self._temperature,
        )

        raw_text = response.content[0].text if response.content else ""
        logger.info(
            "anthropic_auditor: response received task_id=%s stage=%s len=%d",
            task.task_id, stage, len(raw_text),
        )

        json_text = self._extract_json(raw_text)
        try:
            verdict = validate_and_parse("anthropic", json_text)
        except Exception:
            # Retry once with strict JSON instruction (parity with Gemini)
            logger.warning(
                "anthropic_auditor: parse failed, retrying with strict JSON prompt task_id=%s",
                task.task_id,
            )
            response2 = await self._client.messages.create(
                model=self.model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": (
                        "You must respond with ONLY a valid JSON object, nothing else.\n"
                        "No markdown, no prose, no code fences. Start with { and end with }.\n\n"
                        + user_prompt
                    )},
                ],
                temperature=0.0,
            )
            raw_text = response2.content[0].text if response2.content else ""
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
