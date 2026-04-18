"""
providers/opus_arbiter.py — Opus Arbiter for Round 3 dispute resolution.

Separate module with own contract (critique #6 recommendation):
review_runner calls it as a black box, does not know internal logic.

The arbiter:
  - Sees raw proposal (original + revised)
  - Sees all Round 1 + Round 2 verdicts (the full critic pack)
  - Makes a FINAL ruling as AuditVerdict
  - Does NOT see the builder's reasoning or internal debate context

API key: same ANTHROPIC_API_KEY as AnthropicAuditor.
Model: claude-opus-4-6 (or configured override).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..hard_shell.contracts import AuditVerdict, TaskPack
from ..hard_shell.schema_validator import validate_and_parse

logger = logging.getLogger(__name__)


class OpusArbiter:
    """
    Round 3 arbiter: resolves disagreement after debate fails.

    Contract:
        Input:  task + context + arbiter_pack (from debate.build_arbiter_pack)
        Output: AuditVerdict (same schema as regular auditors)

    This is NOT an AuditorProvider — it has a different interface
    (arbitrate, not critique/final_audit) and a different role.
    """

    auditor_id = "opus_arbiter"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ):
        if not api_key:
            raise ValueError("OpusArbiter: api_key is required")
        self._api_key = api_key
        self.model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def arbitrate(
        self,
        task: TaskPack,
        context: dict[str, Any],
        arbiter_pack: dict[str, Any],
    ) -> AuditVerdict:
        """
        Final arbitration after Round 2 debate fails to resolve.

        Returns AuditVerdict with auditor_id="opus_arbiter".
        """
        system_prompt = self._build_system_prompt(context)
        user_prompt = self._build_user_prompt(task, arbiter_pack)

        logger.info(
            "opus_arbiter: calling API model=%s task_id=%s",
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
        logger.info(
            "opus_arbiter: response received task_id=%s len=%d",
            task.task_id, len(raw_text),
        )

        json_text = self._extract_json(raw_text)
        verdict = validate_and_parse("opus_arbiter", json_text)
        logger.info(
            "opus_arbiter: verdict=%s critical=%d warnings=%d task_id=%s",
            verdict.verdict.value, verdict.critical_count,
            verdict.warning_count, task.task_id,
        )
        return verdict

    def _build_system_prompt(self, context: dict[str, Any]) -> str:
        risk = context.get("risk", "unknown")
        surface = context.get("effective_surface", [])
        surface_text = ", ".join(surface) if surface else "none"

        return f"""You are the FINAL ARBITER for the Biretos automation project audit system.

Two auditors have reviewed a code proposal and DISAGREED after two rounds of debate.
Your role: examine the raw proposal, both auditors' arguments, and make the FINAL ruling.

## Rules for arbitration
1. Judge the CODE/PROPOSAL directly — not the auditors' arguments
2. If an auditor raised a valid concern that the other dismissed, side with the concern
3. If both sides have merit, use "concerns" verdict with specific recommendations
4. CRITICAL severity: only for policy violations, frozen file touches, pinned API changes
5. Be decisive — your verdict is final, no further rounds

## Task context
Risk level: {risk.upper()}
Mutation surface: {surface_text}

## Output format
Return a JSON object:
  - verdict: "approve" | "concerns" | "reject"
  - summary: 2-4 sentences explaining your ruling and why you sided with one auditor or neither
  - issues: list of {{severity, area, description, line_ref}}
"""

    def _build_user_prompt(
        self, task: TaskPack, arbiter_pack: dict[str, Any],
    ) -> str:
        dispute = arbiter_pack.get("dispute_summary", "")
        r1 = json.dumps(arbiter_pack.get("round1_verdicts", []), indent=2, ensure_ascii=False)
        r2 = json.dumps(arbiter_pack.get("round2_verdicts", []), indent=2, ensure_ascii=False)
        original = arbiter_pack.get("original_proposal_excerpt", "")
        revised = arbiter_pack.get("revised_proposal_excerpt", "")

        return f"""## Task
Title: {task.title}
Risk: {task.risk.value.upper()}
Description: {task.description or '(none)'}

## Dispute summary
{dispute}

## Round 1 verdicts (isolated, no cross-visibility)
{r1}

## Round 2 verdicts (debate, cross-visible)
{r2}

## Original proposal
{original}

## Revised proposal
{revised}

---
You are the final arbiter. Examine the proposals and all verdicts.
Decide: approve, concerns, or reject. Explain your reasoning.
Return ONLY a JSON object matching the schema above.
"""

    def _extract_json(self, text: str) -> str:
        text = text.strip()
        if text.startswith("{"):
            return text
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            return fence_match.group(1)
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
        return text
