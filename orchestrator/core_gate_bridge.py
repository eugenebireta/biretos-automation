"""
core_gate_bridge.py — Converts SynthesizerDecision → TaskPack and runs
the automated dual audit (Gemini CRITIC + Anthropic JUDGE) synchronously.

This is the glue between orchestrator/main.py and auditor_system.
It replaces the manual "awaiting_owner_reply" stop with an automated
ReviewRunner invocation for CORE_GATE decisions.

Standalone demo usage (no live API):
    python orchestrator/core_gate_bridge.py
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synthesizer import SynthesizerDecision

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
LAST_AUDIT_RESULT_PATH = ROOT / "orchestrator" / "last_audit_result.json"


def decision_to_task_pack(decision, manifest: dict):
    """
    Convert a SynthesizerDecision + manifest into an auditor_system TaskPack.

    Args:
        decision: SynthesizerDecision (from orchestrator/synthesizer.py)
        manifest: current orchestrator manifest dict

    Returns:
        TaskPack ready for ReviewRunner.execute()
    """
    from auditor_system.hard_shell.contracts import TaskPack, RiskLevel

    task_id    = manifest.get("current_task_id") or "unknown"
    sprint_goal = manifest.get("current_sprint_goal") or ""
    rationale  = getattr(decision, "rationale", None) or "CORE_GATE triggered by classifier"

    # Map synthesizer risk string → RiskLevel enum
    risk_str = (getattr(decision, "final_risk", None) or "core").lower()
    try:
        risk = RiskLevel(risk_str)
    except ValueError:
        risk = RiskLevel.CORE  # conservative default

    declared_surface = list(getattr(decision, "approved_scope", None) or [])

    task_pack = TaskPack(
        title=task_id,
        description=sprint_goal,
        roadmap_stage=task_id or "bootstrap",
        why_now=rationale,
        risk=risk,
        declared_surface=declared_surface,
    )

    logger.info(
        json.dumps({
            "trace_id":    manifest.get("trace_id"),
            "task_id":     task_id,
            "risk":        risk.value,
            "surface_count": len(declared_surface),
            "outcome":     "task_pack_created",
        }, ensure_ascii=False)
    )

    return task_pack


def run_audit_sync(task_pack, proposal_text: str = ""):
    """
    Run the automated dual audit synchronously.

    asyncio.run() creates and closes a fresh event loop, safe to call from
    synchronous main.py (as long as main.py is not itself async).

    Args:
        task_pack: TaskPack instance
        proposal_text: optional proposal context

    Returns:
        ProtocolRun — the completed audit run

    Raises:
        auditor_system.runner_factory.ConfigError: if .env.auditors missing
        Any exception from ReviewRunner.execute()
    """
    import sys
    _orch_dir = Path(__file__).resolve().parent
    if str(_orch_dir) not in sys.path:
        sys.path.insert(0, str(_orch_dir))

    # Import here (not top-level) to avoid hard dependency at module import time
    from auditor_system.runner_factory import create_review_runner

    runner = create_review_runner(proposal_text=proposal_text)

    logger.info(
        json.dumps({
            "trace_id":   getattr(task_pack, "task_id", "?"),
            "task_title": getattr(task_pack, "title", "?"),
            "outcome":    "audit_starting",
        }, ensure_ascii=False)
    )

    result = asyncio.run(runner.execute(task_pack))

    logger.info(
        json.dumps({
            "trace_id":      getattr(task_pack, "task_id", "?"),
            "run_id":        result.run_id,
            "approval_route": result.approval_route.value if result.approval_route else None,
            "gate_passed":   result.quality_gate.passed if result.quality_gate else None,
            "outcome":       "audit_complete",
        }, ensure_ascii=False)
    )

    return result


def _determine_fsm_state(audit_result) -> str:
    """
    Map ProtocolRun outcome → fsm_state string.

    Mapping:
      quality_gate.passed=True  → "audit_passed"
      approval_route=BLOCKED    → "blocked"
      anything else             → "needs_owner_review"
    """
    from auditor_system.hard_shell.contracts import ApprovalRoute

    if audit_result.quality_gate and audit_result.quality_gate.passed:
        return "audit_passed"
    if audit_result.approval_route == ApprovalRoute.BLOCKED:
        return "blocked"
    return "needs_owner_review"


def _determine_last_verdict(fsm_state: str) -> str:
    mapping = {
        "audit_passed":       "AUDIT_PASSED",
        "blocked":            "AUDIT_FAILED",
        "needs_owner_review": "AUDIT_INCONCLUSIVE",
    }
    return mapping.get(fsm_state, "AUDIT_INCONCLUSIVE")


if __name__ == "__main__":
    import sys
    from dataclasses import dataclass

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    @dataclass
    class _MockDecision:
        action: str = "CORE_GATE"
        final_risk: str = "core"
        final_route: str = "spec_full"
        approved_scope: list = None
        rationale: str = "Demo CORE_GATE trigger"
        rule_trace: list = None

        def __post_init__(self):
            self.approved_scope = self.approved_scope or []
            self.rule_trace = self.rule_trace or []

    manifest = {
        "current_task_id": "demo-task",
        "current_sprint_goal": "Demo sprint goal for CORE_GATE test",
        "trace_id": "demo-trace-001",
    }

    decision = _MockDecision()
    task_pack = decision_to_task_pack(decision, manifest)

    print(f"TaskPack created:")
    print(f"  title:          {task_pack.title}")
    print(f"  roadmap_stage:  {task_pack.roadmap_stage}")
    print(f"  why_now:        {task_pack.why_now}")
    print(f"  risk:           {task_pack.risk}")
    print(f"  declared_surface: {task_pack.declared_surface}")
    print()
    print("(skipping run_audit_sync — requires .env.auditors)")
