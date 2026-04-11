"""
providers/openai_auditor.py — OpenAI Responses API + Structured Outputs (SPEC §20.8).

Uses client.responses.create() with json_schema format — NOT Chat Completions + JSON mode.
Structured Outputs guarantees valid JSON (no parse errors from format issues).

API key passed directly to client — NEVER via os.environ.
System prompt built dynamically from ContextAssembler context (SPEC §19.4).
"""
from __future__ import annotations

import logging
from typing import Any

from ..hard_shell.contracts import AuditVerdict, TaskPack
from ..hard_shell.schema_validator import validate_and_parse
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


def _build_debate_instruction(peer_verdict: dict[str, Any]) -> str:
    """Build debate instruction block for Round 2 cross-visibility."""
    peer_id = peer_verdict.get("auditor_id", "unknown")
    peer_v = peer_verdict.get("verdict", "unknown")
    peer_summary = peer_verdict.get("summary", "")
    peer_issues = peer_verdict.get("issues", [])

    issues_text = "\n".join(
        f"  - [{i.get('severity', '?')}] {i.get('area', '?')}: {i.get('description', '')}"
        for i in peer_issues
    ) or "  (no issues raised)"

    return f"""
## DEBATE ROUND — Peer Auditor Verdict
Another auditor ({peer_id}) has independently reviewed the same proposal.
Their verdict: **{peer_v.upper()}**
Their summary: {peer_summary}
Their issues:
{issues_text}

## Your task in this debate round
1. Re-examine the PROPOSAL (not the peer's verdict) with their findings in mind
2. If the peer found something you missed — acknowledge it
3. If you disagree with the peer — explain why with evidence from the code
4. Your verdict should reflect YOUR independent judgment, informed by the debate
5. Do NOT just agree with the peer to avoid conflict — genuine disagreement is valuable
"""


def _detect_code_content(text: str) -> bool:
    """Detect if proposal contains actual code (not just description)."""
    code_indicators = [
        "```python",
        "def ",
        "class ",
        "import ",
        "from ",
        "async def ",
    ]
    matches = sum(1 for ind in code_indicators if ind in text)
    return matches >= 2


def _build_user_prompt(
    proposal: str,
    task: TaskPack,
    stage: str,
    context: dict[str, Any],
) -> str:
    why_now = context.get("why_now", task.why_now)
    stage_label = context.get("roadmap_stage", task.roadmap_stage)
    has_code = _detect_code_content(proposal)

    files_section = ""
    if task.affected_files:
        files_section = "Changed files: " + ", ".join(task.affected_files) + "\n"

    code_flag = f"has_code_diff: {'true' if has_code else 'false'}\n"

    # Debate round: include peer verdict context
    debate_section = ""
    peer = context.get("peer_verdict")
    if peer and context.get("debate_round"):
        debate_section = _build_debate_instruction(peer)

    return f"""## Task
Title: {task.title}
Stage: {stage_label}
Risk: {task.risk.value.upper()}
Why now: {why_now}
{files_section}{code_flag}Description: {task.description or '(no description provided)'}
{debate_section}
## {stage.upper()} to audit
{proposal}

---
Audit the above {stage}. Focus on code correctness, policy compliance, and test coverage.
{'Code is present — audit the actual implementation.' if has_code else 'No code provided — flag as process issue.'}
Return your verdict as JSON.
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
