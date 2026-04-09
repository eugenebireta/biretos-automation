"""
advisor.py — Claude Advisor: calls Claude Code CLI, structured JSON verdict.

M2: Calls `claude -p` (Claude Code CLI) with ContextBundle, returns AdvisorVerdict.
Uses the user's Claude Code subscription (not API balance).

Error chain:
  1. Call with full context → parse JSON from response
  2. On parse fail: retry with simplified prompt (sprint goal + task only)
  3. On second fail: write escalation packet → return None (caller handles)

Side effects:
  - Writes orchestrator/last_advisor_verdict.json on success
  - Writes orchestrator/last_escalation.json on escalation

No FSM mutations — caller (main.py) owns state transitions.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any  # noqa: F401

from claude_cli import call_claude

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"

DEFAULT_CLI_TIMEOUT = 120  # seconds — advisor prompts are small, 2 min is plenty

_SYSTEM_PROMPT = """\
You are a task advisor for the Biretos Automation project.
Your role: given the current sprint goal, task state, and last execution result,
determine the precise next step for the AI executor.

Rules:
1. Output ONLY a valid JSON object — no prose, no markdown fences.
2. Keep "next_step" to 1–3 sentences maximum.
3. "scope" lists only files the executor should touch in the next cycle (Tier-3 only unless CORE approved).
4. "risk_assessment" must be one of: LOW, SEMI, CORE.
5. "governance_route" must be one of: none, critique, audit, spec_full.
6. If context is insufficient, set next_step to "NEEDS_OWNER_CLARIFICATION".

Output schema (all fields required):
{
  "schema_version": "v1",
  "trace_id": "<echo back the trace_id from context>",
  "risk_assessment": "LOW",
  "governance_route": "none",
  "rationale": "<why this risk level>",
  "next_step": "<what to do next>",
  "scope": ["path/to/file.py"],
  "issued_at": "<ISO 8601 UTC timestamp>"
}
"""

_SIMPLIFIED_PROMPT = """\
Given:
  sprint_goal: {sprint_goal}
  task_id: {task_id}

Output ONLY a JSON object with these fields:
  schema_version, trace_id, risk_assessment, governance_route, rationale, next_step, scope, issued_at

Use risk_assessment=LOW and governance_route=none unless you have strong reason otherwise.
Keep next_step to 1 sentence. scope may be empty list.
"""


@dataclass
class AdvisorVerdict:
    schema_version: str
    trace_id: str
    risk_assessment: str      # LOW | SEMI | CORE
    governance_route: str     # none | critique | audit | spec_full
    rationale: str
    next_step: str
    scope: list[str]
    issued_at: str
    raw_response: str = field(default="", repr=False)


@dataclass
class AdvisorResult:
    verdict: AdvisorVerdict | None
    escalated: bool = False
    escalation_reason: str = ""
    attempt_count: int = 0
    warnings: list[str] = field(default_factory=list)


def _load_config() -> dict:
    try:
        import yaml
        cfg_path = ORCH_DIR / "config.yaml"
        if cfg_path.exists():
            return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _call_cli(prompt: str, system_prompt: str, timeout: int) -> str:
    """Call Claude Code CLI. Delegates to shared claude_cli.call_claude."""
    return call_claude(prompt, system_prompt=system_prompt, timeout=timeout)


def _extract_json(text: str) -> dict:
    """
    Extract first JSON object from text.
    Handles responses with surrounding prose or markdown fences.
    Raises ValueError if no valid JSON found.
    """
    # Strip markdown fences
    text = re.sub(r"```(?:json)?\s*", "", text).strip()

    # Try full text first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find first {...} block
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object in response")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError as e:
                    raise ValueError(f"Malformed JSON block: {e}") from e
    raise ValueError("Unbalanced braces in response")


def _validate_verdict_dict(data: dict, trace_id: str) -> list[str]:
    """Return list of validation errors (empty = OK)."""
    errors = []
    required = {"schema_version", "trace_id", "risk_assessment",
                "governance_route", "rationale", "next_step", "scope", "issued_at"}
    missing = required - set(data.keys())
    if missing:
        errors.append(f"Missing fields: {sorted(missing)}")
    if data.get("risk_assessment") not in ("LOW", "SEMI", "CORE"):
        errors.append(f"Invalid risk_assessment: {data.get('risk_assessment')!r}")
    if data.get("governance_route") not in ("none", "critique", "audit", "spec_full"):
        errors.append(f"Invalid governance_route: {data.get('governance_route')!r}")
    if not isinstance(data.get("scope"), list):
        errors.append("scope must be a list")
    return errors


def _build_full_user_prompt(bundle) -> str:
    """Build the full context user prompt from ContextBundle."""
    return bundle.to_advisor_prompt_context()



def _write_verdict_file(verdict: AdvisorVerdict, path: Path | None = None) -> None:
    path = path or ORCH_DIR / "last_advisor_verdict.json"
    data = {
        "schema_version": verdict.schema_version,
        "trace_id": verdict.trace_id,
        "risk_assessment": verdict.risk_assessment,
        "governance_route": verdict.governance_route,
        "rationale": verdict.rationale,
        "next_step": verdict.next_step,
        "scope": verdict.scope,
        "issued_at": verdict.issued_at,
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_escalation_file(reason: str, trace_id: str,
                            path: Path | None = None) -> None:
    path = path or ORCH_DIR / "last_escalation.json"
    data = {
        "schema_version": "v1",
        "escalation_type": "advisor_parse_failure",
        "trace_id": trace_id,
        "reason": reason,
        "idempotency_key": f"escalation_{trace_id}",
        "affected_entity_count": 0,
        "options": [
            {
                "option_id": "retry_manual",
                "label": "Retry with manual sprint goal clarification",
                "risk": "LOW",
            }
        ],
        "issued_at": _now(),
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def call(
    bundle,
    api_key: str | None = None,
    config: dict | None = None,
    verdict_path: Path | None = None,
    escalation_path: Path | None = None,
    _call_fn=None,  # injectable for tests — replaces _call_cli
) -> AdvisorResult:
    """
    Call Claude Advisor via Claude Code CLI (`claude -p`).

    Uses the user's Claude Code subscription (not API balance).
    Model selection is handled by Claude Code settings (user controls via /model).

    Returns AdvisorResult with verdict (or None + escalated=True on failure).
    Writes last_advisor_verdict.json on success.
    Writes last_escalation.json on escalation.
    """
    cfg = config if config is not None else _load_config()
    timeout = int(cfg.get("advisor_timeout_seconds", DEFAULT_CLI_TIMEOUT))
    call_fn = _call_fn or _call_cli

    warnings: list[str] = []
    trace_id = getattr(bundle, "trace_id", "") or "unknown"

    print(f"[advisor] channel=cli trace_id={trace_id}")

    # --- Attempt 1: full context ---
    raw1 = ""
    try:
        user_prompt = _build_full_user_prompt(bundle)
        raw1 = call_fn(user_prompt, _SYSTEM_PROMPT, timeout)
        data = _extract_json(raw1)
        errs = _validate_verdict_dict(data, trace_id)
        if not errs:
            if not data.get("issued_at"):
                data["issued_at"] = _now()
            verdict = AdvisorVerdict(
                schema_version=data.get("schema_version", "v1"),
                trace_id=data.get("trace_id", trace_id),
                risk_assessment=data["risk_assessment"],
                governance_route=data["governance_route"],
                rationale=data.get("rationale", ""),
                next_step=data.get("next_step", ""),
                scope=data.get("scope", []),
                issued_at=data["issued_at"],
                raw_response=raw1,
            )
            _write_verdict_file(verdict, verdict_path)
            return AdvisorResult(verdict=verdict, attempt_count=1, warnings=warnings)
        else:
            warnings.append(f"Attempt 1 validation errors: {errs}")
    except Exception as e:
        warnings.append(f"Attempt 1 failed: {e}")

    # --- Attempt 2: simplified prompt ---
    raw2 = ""
    try:
        simplified = _SIMPLIFIED_PROMPT.format(
            sprint_goal=getattr(bundle, "sprint_goal", "(not set)"),
            task_id=getattr(bundle, "task_id", "(unknown)"),
        )
        raw2 = call_fn(simplified, _SYSTEM_PROMPT, timeout)
        data = _extract_json(raw2)
        errs = _validate_verdict_dict(data, trace_id)
        if not errs:
            if not data.get("issued_at"):
                data["issued_at"] = _now()
            verdict = AdvisorVerdict(
                schema_version=data.get("schema_version", "v1"),
                trace_id=data.get("trace_id", trace_id),
                risk_assessment=data["risk_assessment"],
                governance_route=data["governance_route"],
                rationale=data.get("rationale", ""),
                next_step=data.get("next_step", ""),
                scope=data.get("scope", []),
                issued_at=data["issued_at"],
                raw_response=raw2,
            )
            _write_verdict_file(verdict, verdict_path)
            return AdvisorResult(verdict=verdict, attempt_count=2, warnings=warnings)
        else:
            warnings.append(f"Attempt 2 validation errors: {errs}")
    except Exception as e:
        warnings.append(f"Attempt 2 failed: {e}")

    # --- ESCALATE ---
    reason = "; ".join(warnings) or "Unknown advisor failure"
    _write_escalation_file(reason, trace_id, escalation_path)
    return AdvisorResult(
        verdict=None,
        escalated=True,
        escalation_reason=reason,
        attempt_count=2,
        warnings=warnings,
    )
