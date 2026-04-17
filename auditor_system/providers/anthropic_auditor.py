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

from ..hard_shell.contracts import AuditVerdict, DefectRegister, L2Report, RepairEntry, TaskPack
from ..hard_shell.schema_validator import extract_json_from_response, validate_and_parse
from .base import AuditorProvider
# Reuse prompt builders from openai_auditor (same system/user prompt format)
from .openai_auditor import _build_re_review_user_prompt, _build_system_prompt, _build_user_prompt

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
        from orchestrator._api_cost_tracker import log_api_call
        log_api_call(__file__, self.model, response.usage)

        raw_text = response.content[0].text if response.content else ""
        logger.info(
            "anthropic_auditor: response received task_id=%s stage=%s len=%d",
            task.task_id, stage, len(raw_text),
        )

        json_text = extract_json_from_response(raw_text)
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

    async def debate(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
        peer_verdict: "AuditVerdict",
    ) -> AuditVerdict:
        """Round 2 debate: re-audit with visibility into peer's Round 1 verdict."""
        from ..debate import build_debate_context

        debate_ctx = build_debate_context(context, peer_verdict)
        return await self._call(proposal, task, debate_ctx, stage="debate")

    async def re_review(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
        defect_register: "DefectRegister",
        repair_manifest: list["RepairEntry"],
        l2_report: "L2Report",
        original_diff: str = "",
    ) -> AuditVerdict:
        """
        Consensus Pipeline Protocol v1: re-review after builder repair.
        Uses structured checklist prompt instead of fresh critique.
        """
        from ..debate import build_re_review_context

        re_review_ctx = build_re_review_context(
            context,
            defect_register,
            repair_manifest,
            l2_report,
            original_diff,
        )
        system_prompt = _build_system_prompt(re_review_ctx)
        user_prompt = (
            _build_re_review_user_prompt(proposal, task, re_review_ctx)
            + "\n\nReturn ONLY a JSON object matching the schema above. No prose outside JSON."
        )

        logger.info(
            "anthropic_auditor: re_review API call model=%s task_id=%s",
            self.model, task.task_id,
        )

        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=self._temperature,
        )
        from orchestrator._api_cost_tracker import log_api_call
        log_api_call(__file__, self.model, response.usage)

        raw_text = response.content[0].text if response.content else ""
        json_text = extract_json_from_response(raw_text)
        verdict = validate_and_parse("anthropic", json_text)
        logger.info(
            "anthropic_auditor: re_review verdict=%s task_id=%s",
            verdict.verdict.value, task.task_id,
        )
        return verdict
