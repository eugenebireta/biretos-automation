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


def run_scope_review_sync(task_pack, scope_text: str = ""):
    """
    Lightweight pre-execution scope/risk review.

    Unlike run_audit_sync (full 2-round protocol with MockBuilder),
    this runs a SINGLE round of critique on the scope/risk proposal.
    No builder revision, no second round — just: "is this scope safe?"

    Returns a simplified result dict (not full ProtocolRun):
        {passed: bool, concerns: list[str], auditor_verdicts: dict}
    """
    import sys
    _orch_dir = Path(__file__).resolve().parent
    if str(_orch_dir) not in sys.path:
        sys.path.insert(0, str(_orch_dir))

    from auditor_system.runner_factory import _load_secrets_safe, _CONFIG_PATH
    import yaml

    secrets = _load_secrets_safe()

    models_config = {}
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            models_config = yaml.safe_load(f) or {}

    gemini_model = models_config.get("auditors", {}).get("gemini", "gemini-2.5-pro")
    anthropic_model = models_config.get("auditors", {}).get("anthropic", "claude-sonnet-4-6")

    from auditor_system.providers.gemini_auditor import GeminiAuditor
    from auditor_system.providers.anthropic_auditor import AnthropicAuditor

    auditors = [
        GeminiAuditor(model=gemini_model, api_key=secrets["GEMINI_API_KEY"]),
        AnthropicAuditor(model=anthropic_model, api_key=secrets["ANTHROPIC_API_KEY"]),
    ]

    # Single critique round — no builder, no revision
    async def _run():
        verdicts = []
        for auditor in auditors:
            try:
                verdict = await auditor.critique(task_pack, scope_text)
                verdicts.append(verdict)
            except Exception as exc:
                logger.warning("scope_review: auditor %s failed: %s",
                               auditor.auditor_id, exc)
        return verdicts

    verdicts = asyncio.run(_run())

    # Simple pass logic: no critical issues = pass
    concerns = []
    has_critical = False
    auditor_verdicts = {}
    for v in verdicts:
        auditor_verdicts[v.auditor_id] = v.verdict.value
        for issue in v.issues:
            if issue.severity.value == "critical":
                has_critical = True
            concerns.append(f"[{v.auditor_id}/{issue.severity.value}] {issue.description}")

    passed = not has_critical and len(verdicts) > 0

    logger.info(
        json.dumps({
            "trace_id": getattr(task_pack, "title", "?"),
            "outcome": "scope_review_complete",
            "passed": passed,
            "auditor_count": len(verdicts),
            "concern_count": len(concerns),
        }, ensure_ascii=False)
    )

    return {
        "passed": passed,
        "concerns": concerns,
        "auditor_verdicts": auditor_verdicts,
        "verdict_count": len(verdicts),
    }


def run_post_execution_audit_sync(
    packet: dict,
    directive_text: str,
    trace_id: str,
    risk_class: str,
    manifest: dict,
) -> "ProtocolRun":
    """
    Run auditor on COMPLETED execution for SEMI/CORE tasks.

    Unlike run_audit_sync (pre-execution for CORE_GATE), this reviews
    the actual execution result: diff, changed files, test results.

    Args:
        packet: Execution packet (from collect_packet)
        directive_text: The directive that was executed
        trace_id: Orchestrator trace ID
        risk_class: LOW/SEMI/CORE
        manifest: Current manifest dict

    Returns:
        ProtocolRun with quality_gate, approval_route, critiques

    Raises:
        ConfigError: if .env.auditors missing
    """
    import sys
    from auditor_system.hard_shell.contracts import TaskPack, RiskLevel

    _orch_dir = Path(__file__).resolve().parent
    if str(_orch_dir) not in sys.path:
        sys.path.insert(0, str(_orch_dir))

    from auditor_system.runner_factory import create_review_runner

    # Build proposal text from execution results
    changed_files = packet.get("changed_files") or []
    test_results = packet.get("test_results") or {}
    affected_tiers = packet.get("affected_tiers") or []

    proposal_text = (
        f"## Post-Execution Review\n\n"
        f"**Directive executed:** trace_id={trace_id}\n"
        f"**Changed files ({len(changed_files)}):** {changed_files[:20]}\n"
        f"**Affected tiers:** {affected_tiers}\n"
        f"**Test results:** passed={test_results.get('passed', '?')} "
        f"failed={test_results.get('failed', '?')}\n\n"
        f"### Directive\n```\n{directive_text[:2000]}\n```\n"
    )

    risk_str = risk_class.lower()
    try:
        risk = RiskLevel(risk_str)
    except ValueError:
        risk = RiskLevel.SEMI

    task_id = manifest.get("current_task_id") or "unknown"
    sprint_goal = manifest.get("current_sprint_goal") or ""

    task_pack = TaskPack(
        title=f"post-exec-review:{task_id}",
        description=f"Post-execution semantic review: {sprint_goal}",
        roadmap_stage=task_id or "bootstrap",
        why_now=f"Executor completed SEMI/CORE task. Semantic review required per governance.",
        risk=risk,
        declared_surface=changed_files[:20],
    )

    logger.info(json.dumps({
        "trace_id": trace_id,
        "task_id": task_id,
        "risk": risk.value,
        "changed_files": len(changed_files),
        "outcome": "post_exec_audit_starting",
    }, ensure_ascii=False))

    runner = create_review_runner(proposal_text=proposal_text)
    result = asyncio.run(runner.execute(task_pack))

    logger.info(json.dumps({
        "trace_id": trace_id,
        "run_id": result.run_id,
        "gate_passed": result.quality_gate.passed if result.quality_gate else None,
        "approval_route": result.approval_route.value if result.approval_route else None,
        "outcome": "post_exec_audit_complete",
    }, ensure_ascii=False))

    return result


def extract_critique_text(audit_result) -> str:
    """Extract human-readable critique from ProtocolRun for retry directive."""
    parts = []
    if hasattr(audit_result, "critiques") and audit_result.critiques:
        for critique in audit_result.critiques:
            auditor_id = getattr(critique, "auditor_id", "unknown")
            summary = getattr(critique, "summary", "")
            issues = getattr(critique, "issues", [])
            parts.append(f"[{auditor_id}] {summary}")
            for issue in issues[:5]:
                severity = getattr(issue, "severity", "")
                desc = getattr(issue, "description", str(issue))
                parts.append(f"  - [{severity}] {desc}")
    if hasattr(audit_result, "final_verdicts") and audit_result.final_verdicts:
        for verdict in audit_result.final_verdicts:
            auditor_id = getattr(verdict, "auditor_id", "unknown")
            v = getattr(verdict, "verdict", "")
            summary = getattr(verdict, "summary", "")
            parts.append(f"[{auditor_id} final] {v}: {summary}")
    return "\n".join(parts) if parts else "No critique details available."


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
