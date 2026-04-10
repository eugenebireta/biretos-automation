"""
intake.py — Task Intake + Context Pruner.

Reads persisted artifacts (manifest, execution packet, advisor verdict) and
assembles a trimmed context bundle ready for the Claude Advisor call in M2.

Responsibilities:
  1. Load manifest, last_execution_packet, last_advisor_verdict
  2. Validate each against its schema (soft — never raises)
  3. Prune diff to diff_truncation_chars limit
  4. Warn if current_sprint_goal is stale
  5. Return ContextBundle (typed dict-like object)

No LLM calls. No subprocess. No side effects beyond reading files.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"

# Default limits (overridden by config.yaml if present)
DEFAULT_MAX_CONTEXT_CHARS = 15_000
DEFAULT_DIFF_TRUNCATION_CHARS = 15_000
DEFAULT_SPRINT_GOAL_WARN_DAYS = 7


def _load_config() -> dict:
    try:
        import yaml
        cfg_path = ORCH_DIR / "config.yaml"
        if cfg_path.exists():
            return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


@dataclass
class ContextBundle:
    """Assembled, pruned context ready for Claude Advisor."""
    sprint_goal: str
    task_id: str
    fsm_state: str
    attempt_count: int
    trace_id: str

    # From last execution packet (may be None on first cycle)
    last_status: str | None
    last_changed_files: list[str]
    last_diff: str | None               # pruned
    last_diff_truncated: bool
    last_test_results: dict | None
    last_affected_tiers: list[str]
    last_executor_notes: str | None
    last_questions: list[str]
    last_blockers: list[str]

    # From last advisor verdict (may be None on first cycle)
    last_verdict_risk: str | None
    last_verdict_route: str | None
    last_verdict_rationale: str | None

    # Relevant DNA constraints (static excerpt for advisor)
    dna_constraints: list[str]

    # Warnings generated during intake
    warnings: list[str] = field(default_factory=list)

    # Validation errors (soft — recorded, not raised)
    validation_errors: list[str] = field(default_factory=list)

    def to_advisor_prompt_context(self) -> str:
        """
        Render context bundle as structured text for the Claude Advisor prompt.
        Keeps total size within reasonable bounds.
        """
        lines: list[str] = []

        lines.append(f"## Sprint Goal\n{self.sprint_goal or '(not set)'}")
        lines.append(f"## Current Task\ntask_id: {self.task_id}\n"
                     f"fsm_state: {self.fsm_state}\nattempt: {self.attempt_count}")

        if self.last_status:
            lines.append(f"## Last Execution Result\nstatus: {self.last_status}")
            if self.last_changed_files:
                lines.append(f"changed_files:\n" +
                              "\n".join(f"  - {f}" for f in self.last_changed_files))
            if self.last_test_results:
                tr = self.last_test_results
                lines.append(f"tests: passed={tr.get('passed',0)} "
                              f"failed={tr.get('failed',0)} skipped={tr.get('skipped',0)}")
            if self.last_affected_tiers:
                lines.append(f"affected_tiers: {self.last_affected_tiers}")
            if self.last_questions:
                lines.append("questions:\n" +
                              "\n".join(f"  - {q}" for q in self.last_questions))
            if self.last_blockers:
                lines.append("blockers:\n" +
                              "\n".join(f"  - {b}" for b in self.last_blockers))
            if self.last_executor_notes:
                lines.append(f"executor_notes: {self.last_executor_notes}")
            if self.last_diff:
                diff_note = " [TRUNCATED]" if self.last_diff_truncated else ""
                lines.append(f"## Diff Summary{diff_note}\n```\n{self.last_diff}\n```")

        if self.last_verdict_rationale:
            lines.append(f"## Previous Advisor Verdict\n"
                         f"risk: {self.last_verdict_risk}  "
                         f"route: {self.last_verdict_route}\n"
                         f"rationale: {self.last_verdict_rationale}")

        if self.dna_constraints:
            lines.append("## Active Constraints\n" +
                         "\n".join(f"  - {c}" for c in self.dna_constraints))

        if self.warnings:
            lines.append("## Intake Warnings\n" +
                         "\n".join(f"  - {w}" for w in self.warnings))

        return "\n\n".join(lines)


# Static DNA constraint excerpts provided to Claude Advisor
_DNA_CONSTRAINTS = [
    "Tier-1 files (19) are FROZEN — never modify",
    "Tier-2 pinned signatures must not change names, args, or return types",
    "Tier-3 code cannot INSERT/UPDATE/DELETE on reconciliation_* or Core business tables",
    "No import from domain.reconciliation_* in Tier-3",
    "Revenue tables use rev_* / stg_* / lot_* prefix only",
    "Revenue FSM: linear, max 5 states, no nested FSM",
    "Every new Tier-3 module needs: trace_id, idempotency_key, deterministic test",
    "No commit inside domain operations — commit only at worker boundary",
    "Fail Loud: no silent exception swallowing",
    "orchestrator/ synthesizer changes require SEMI risk review before M3 gate",
]


def load(
    manifest_path: Path | None = None,
    packet_path: Path | None = None,
    verdict_path: Path | None = None,
    config: dict | None = None,
) -> ContextBundle:
    """
    Load and assemble context bundle from persisted artifacts.

    All file reads are soft — missing files produce warnings, not exceptions.
    Schema validation is soft — errors are recorded in bundle.validation_errors.
    """
    cfg = config if config is not None else _load_config()
    diff_limit = int(cfg.get("diff_truncation_chars", DEFAULT_DIFF_TRUNCATION_CHARS))
    warn_days = int(cfg.get("sprint_goal_staleness_warn_days", DEFAULT_SPRINT_GOAL_WARN_DAYS))

    manifest_path = manifest_path or ORCH_DIR / "manifest.json"
    packet_path = packet_path or ORCH_DIR / "last_execution_packet.json"
    verdict_path = verdict_path or ORCH_DIR / "last_advisor_verdict.json"

    warnings: list[str] = []
    validation_errors: list[str] = []

    # --- Load manifest ---
    manifest = _read_json(manifest_path, warnings, "manifest")
    _validate_soft("manifest_v1", manifest, validation_errors)

    sprint_goal = manifest.get("current_sprint_goal", "")
    task_id = manifest.get("current_task_id", "")
    fsm_state = manifest.get("fsm_state", "ready")
    attempt_count = int(manifest.get("attempt_count", 0))
    trace_id = manifest.get("trace_id", "")
    updated_at = manifest.get("updated_at", "")

    # Sprint goal staleness check
    if not sprint_goal:
        warnings.append("current_sprint_goal is empty — set it before running advisor")
    elif updated_at:
        try:
            updated = datetime.fromisoformat(updated_at)
            if datetime.now(timezone.utc) - updated > timedelta(days=warn_days):
                warnings.append(
                    f"current_sprint_goal not updated in >{warn_days} days "
                    f"(last: {updated_at[:10]})"
                )
        except Exception:
            pass

    # --- Load execution packet ---
    packet = _read_json(packet_path, warnings, "execution_packet") if packet_path.exists() else {}
    if packet:
        _validate_soft("execution_packet_v1", packet, validation_errors)

    last_diff_raw: str | None = packet.get("diff_summary")
    last_diff_truncated = bool(packet.get("diff_truncated", False))

    # Re-truncate if needed (packet may have been written with different limit)
    if last_diff_raw and len(last_diff_raw) > diff_limit:
        last_diff_raw = last_diff_raw[:diff_limit] + "\n[DIFF TRUNCATED]"
        last_diff_truncated = True

    # --- Load last advisor verdict ---
    verdict = _read_json(verdict_path, warnings, "advisor_verdict") if verdict_path.exists() else {}
    if verdict:
        _validate_soft("advisor_verdict_v1", verdict, validation_errors)

    return ContextBundle(
        sprint_goal=sprint_goal,
        task_id=task_id,
        fsm_state=fsm_state,
        attempt_count=attempt_count,
        trace_id=trace_id,
        last_status=packet.get("status"),
        last_changed_files=packet.get("changed_files", []),
        last_diff=last_diff_raw,
        last_diff_truncated=last_diff_truncated,
        last_test_results=packet.get("test_results"),
        last_affected_tiers=packet.get("affected_tiers", []),
        last_executor_notes=packet.get("executor_notes"),
        last_questions=packet.get("questions", []),
        last_blockers=packet.get("blockers", []),
        last_verdict_risk=verdict.get("risk_assessment"),
        last_verdict_route=verdict.get("governance_route"),
        last_verdict_rationale=verdict.get("rationale"),
        dna_constraints=list(_DNA_CONSTRAINTS),
        warnings=warnings,
        validation_errors=validation_errors,
    )


def _read_json(path: Path, warnings: list[str], label: str) -> dict:
    """Read JSON file softly — on error, record warning and return {}."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        warnings.append(f"{label} not found at {path}")
        return {}
    except json.JSONDecodeError as e:
        warnings.append(f"{label} invalid JSON: {e}")
        return {}
    except Exception as e:
        warnings.append(f"{label} read error: {e}")
        return {}


def _validate_soft(schema_name: str, data: Any, errors: list[str]) -> None:
    """Run schema validation softly — append errors, never raise."""
    try:
        # Import lazily to avoid hard dependency at module load
        from schemas import validate_soft as _vs
        errs = _vs(schema_name, data)
        errors.extend(f"{schema_name}: {e}" for e in errs)
    except ImportError:
        errors.append(f"schemas module not available — skipping {schema_name} validation")
    except Exception as e:
        errors.append(f"{schema_name} validation error: {e}")
