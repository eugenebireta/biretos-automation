"""
providers/openai_auditor.py — OpenAI Responses API + Structured Outputs (SPEC §20.8).

Uses client.responses.create() with json_schema format — NOT Chat Completions + JSON mode.
Structured Outputs guarantees valid JSON (no parse errors from format issues).

API key passed directly to client — NEVER via os.environ.
System prompt built dynamically from ContextAssembler context (SPEC §19.4).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from ..hard_shell.contracts import AuditVerdict, AuditVerdictValue, TaskPack
from ..hard_shell.schema_validator import SchemaViolationError, validate_and_parse
from .base import AuditorProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON Schema for AuditVerdict (SPEC §19.3 — Structured Outputs schema)
# Derived from contracts.AuditVerdict. Must stay in sync.
# ---------------------------------------------------------------------------

VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["approve", "concerns", "reject"],
            "description": "Overall audit verdict",
        },
        "summary": {
            "type": "string",
            "description": "Brief summary of the audit findings (1-3 sentences)",
        },
        "issues": {
            "type": "array",
            "description": "List of specific issues found",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["info", "warning", "critical"],
                    },
                    "area": {
                        "type": "string",
                        "description": "Area affected: architecture|security|test_coverage|fsm|guardian|policy|other",
                    },
                    "description": {
                        "type": "string",
                        "description": "Specific description of the issue",
                    },
                    "line_ref": {
                        "type": "string",
                        "description": "Optional code reference (file:line)",
                    },
                },
                "required": ["severity", "area", "description", "line_ref"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdict", "summary", "issues"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_system_prompt(context: dict[str, Any]) -> str:
    """Builds system prompt dynamically from ContextAssembler context (SPEC §19.4)."""
    risk = context.get("risk", "unknown")
    surface = context.get("effective_surface", [])
    prohibitions = context.get("absolute_prohibitions", [])
    revenue_rules = context.get("revenue_table_rules", [])
    mismatch_warn = context.get("surface_mismatch_warning", "")

    prohibitions_text = "\n".join(f"  - {p}" for p in prohibitions)
    revenue_text = "\n".join(f"  - {r}" for r in revenue_rules)
    surface_text = ", ".join(surface) if surface else "none"

    prompt = f"""You are an independent technical auditor for the Biretos automation project.
Your role: critique code proposals for correctness, safety, and policy compliance.
You do NOT approve proposals lightly — find real issues or explain why there are none.

## Task context
Risk level: {risk.upper()}
Mutation surface: {surface_text}

## Absolute prohibitions (VIOLATION = CRITICAL issue)
{prohibitions_text}

## Revenue table rules (Tier-3)
{revenue_text}

## Required per Tier-3 module
Every new module MUST have:
  - trace_id from payload
  - idempotency_key for side-effects
  - No commit inside domain operations
  - No logging of secrets or raw payload
  - Structured error logging: error_class (TRANSIENT/PERMANENT/POLICY_VIOLATION), severity, retriable
  - No silent exception swallowing
  - At least one deterministic test (no live API, no unmocked time)
  - Webhook workers must validate HMAC signature BEFORE processing
  - Inbound event dedup via INSERT ON CONFLICT DO NOTHING

## FSM rules
  - Linear FSM only, max 5 states
  - No nested FSM, no branching states, no custom retry orchestrators
  - No direct JOIN with Core tables; read Core only via read-only views

## Your output
Return a JSON object with:
  - verdict: "approve" | "concerns" | "reject"
  - summary: 1-3 sentences
  - issues: list of {{severity, area, description, line_ref}}

Use "critical" severity only for policy violations, frozen file touches, or pinned API signature changes.
Use "warning" for missing tests, incomplete error handling, unclear scope.
Use "info" for suggestions.
"""
    if mismatch_warn:
        prompt += f"\n## ⚠️ Surface mismatch\n{mismatch_warn}\n"

    return prompt


def _build_user_prompt(
    proposal: str,
    task: TaskPack,
    stage: str,
    context: dict[str, Any],
) -> str:
    why_now = context.get("why_now", task.why_now)
    stage_label = context.get("roadmap_stage", task.roadmap_stage)

    return f"""## Task
Title: {task.title}
Stage: {stage_label}
Risk: {task.risk.value.upper()}
Why now: {why_now}
Description: {task.description or '(no description provided)'}

## {stage.upper()} to audit
{proposal}

---
Audit the above {stage}. Return your verdict as JSON.
"""


# ---------------------------------------------------------------------------
# OpenAIAuditor
# ---------------------------------------------------------------------------

class OpenAIAuditor(AuditorProvider):
    """
    Auditor using OpenAI Responses API + Structured Outputs.
    API key passed directly — NOT from os.environ (SPEC §20.8).
    """

    auditor_id = "openai"

    def __init__(self, model: str = "gpt-4o", api_key: str | None = None):
        if not api_key:
            raise ValueError("OpenAIAuditor: api_key is required (SPEC §20.8)")
        self.model = model
        self._api_key = api_key  # NEVER log (DNA §7)
        # Lazy import to avoid import errors when openai not installed
        import openai
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def _call(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
        stage: str,
    ) -> AuditVerdict:
        system_prompt = _build_system_prompt(context)
        user_prompt = _build_user_prompt(proposal, task, stage, context)

        logger.info(
            "openai_auditor: calling API model=%s task_id=%s stage=%s",
            self.model, task.task_id, stage,
        )

        response = await self._client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "audit_verdict",
                    "schema": VERDICT_SCHEMA,
                    "strict": True,
                }
            },
        )

        raw_text = response.output_text
        logger.info(
            "openai_auditor: response received task_id=%s stage=%s len=%d",
            task.task_id, stage, len(raw_text),
        )

        verdict = validate_and_parse("openai", raw_text)
        logger.info(
            "openai_auditor: verdict=%s critical=%d warnings=%d task_id=%s",
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
