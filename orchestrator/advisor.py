"""
advisor.py — Claude Advisor: single API call, structured JSON verdict.

M2: Calls Claude API with ContextBundle, returns AdvisorVerdict.

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
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TIMEOUT = 60

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


def _make_client(api_key: str | None = None):
    """Create Anthropic client. Raises if SDK missing or key absent."""
    import anthropic
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=key)


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


def _call_api(client, model: str, user_prompt: str,
              max_tokens: int, timeout: int) -> str:
    """Make the API call and return raw text content."""
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        timeout=timeout,
    )
    return response.content[0].text


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
    _client=None,  # injectable for tests
) -> AdvisorResult:
    """
    Call Claude Advisor with the given ContextBundle.

    Returns AdvisorResult with verdict (or None + escalated=True on failure).
    Writes last_advisor_verdict.json on success.
    Writes last_escalation.json on escalation.
    """
    cfg = config if config is not None else _load_config()
    model = cfg.get("advisor_model", DEFAULT_MODEL)
    max_tokens = int(cfg.get("advisor_max_tokens", DEFAULT_MAX_TOKENS))
    timeout = int(cfg.get("advisor_timeout_seconds", DEFAULT_TIMEOUT))

    warnings: list[str] = []
    attempt = 0

    try:
        client = _client if _client is not None else _make_client(api_key)
    except ValueError as e:
        return AdvisorResult(
            verdict=None,
            escalated=True,
            escalation_reason=str(e),
            attempt_count=0,
            warnings=[str(e)],
        )

    trace_id = getattr(bundle, "trace_id", "") or "unknown"

    # --- Attempt 1: full context ---
    attempt = 1
    raw1 = ""
    try:
        user_prompt = _build_full_user_prompt(bundle)
        raw1 = _call_api(client, model, user_prompt, max_tokens, timeout)
        data = _extract_json(raw1)
        errs = _validate_verdict_dict(data, trace_id)
        if not errs:
            # Patch issued_at if missing
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
    attempt = 2
    raw2 = ""
    try:
        simplified = _SIMPLIFIED_PROMPT.format(
            sprint_goal=getattr(bundle, "sprint_goal", "(not set)"),
            task_id=getattr(bundle, "task_id", "(unknown)"),
        )
        raw2 = _call_api(client, model, simplified, max_tokens, timeout)
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
