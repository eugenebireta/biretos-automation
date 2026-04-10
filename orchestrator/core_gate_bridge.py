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

import ast
import asyncio
import hashlib
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
LAST_AUDIT_RESULT_PATH = ROOT / "orchestrator" / "last_audit_result.json"

# Hard guards that run BEFORE any LLM audit (deterministic, no API cost).
# These correspond to DNA §3 (frozen files), §4 (pinned API), §5 (prohibitions).
_PREFLIGHT_GUARDS = [
    "frozen_files",      # Tier-1 files unchanged (DNA §3)
    "pinned_api",        # Function signatures unchanged (DNA §4)
    "forbidden_imports", # No imports from reconciliation_* (DNA §5)
    "forbidden_dml",     # No DML on core tables from Tier-3 (DNA §5)
]

_STUB_VALUE = "stub_not_checked"

# ── Guard patterns (DNA §5) — mirror Iron Fence CI tests ──────────────────
_FORBIDDEN_IMPORTS_RE = re.compile(
    r"from domain\.reconciliation_service|"
    r"from domain\.reconciliation_verify|"
    r"from domain\.reconciliation_alerts|"
    r"from domain\.structural_checks|"
    r"from domain\.observability_service|"
    r"import reconciliation_service|"
    r"import reconciliation_verify|"
    r"import reconciliation_alerts|"
    r"import structural_checks|"
    r"import observability_service"
)

_RECON_TABLES = (
    "reconciliation_audit_log", "reconciliation_alerts", "reconciliation_suppressions",
)
_CORE_BIZ_TABLES = (
    "order_ledger", "shipments", "payment_transactions", "reservations",
    "stock_ledger_entries", "availability_snapshot", "documents",
)
_DML_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP")
_DML_RE = "|".join(_DML_KEYWORDS)
_RECON_TABLES_RE = "|".join(_RECON_TABLES)
_CORE_BIZ_TABLES_RE = "|".join(_CORE_BIZ_TABLES)
_FORBIDDEN_DML_RE = re.compile(
    rf"({_DML_RE})\s+.*({_RECON_TABLES_RE}|{_CORE_BIZ_TABLES_RE})",
    re.IGNORECASE,
)

# ── Pinned API signatures (DNA §4) — hash of ast-extracted signatures ─────
_PINNED_API_HASHES: dict[str, str] = {
    "domain/payment_service.py::_derive_payment_status": "2721dacd183f371c",
    "domain/payment_service.py::_extract_order_total_minor": "943ea30c15f95caa",
    "domain/shipment_service.py::recompute_order_cdek_cache_atomic": "73eabd40619c3a89",
    "domain/shipment_service.py::update_shipment_status_atomic": "9e4787b9ecb8c430",
    "domain/availability_service.py::_ensure_snapshot_row": "31e1a2d055754f54",
    "domain/ports.py::InvoiceStatusRequest": "46d7ab177a2a9fa5",
    "domain/ports.py::ShipmentTrackingStatusRequest": "d238f70f33919096",
}

_WINDMILL_ROOT = ROOT / ".cursor" / "windmill-core-v1"


def _read_changed_file(filepath: str) -> str | None:
    """Read a changed file's content. Returns None if file doesn't exist."""
    for base in (_WINDMILL_ROOT, ROOT):
        full = base / filepath
        if full.exists():
            try:
                return full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
    return None


def _check_forbidden_imports(changed_files: list[str]) -> tuple[str, list[str]]:
    """Check changed files for forbidden imports (DNA §5). Returns (status, violations)."""
    violations = []
    for fpath in changed_files:
        if not fpath.endswith(".py"):
            continue
        content = _read_changed_file(fpath)
        if content is None:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            if _FORBIDDEN_IMPORTS_RE.search(line):
                violations.append(f"{fpath}:{i}: {line.strip()}")
    return ("fail" if violations else "pass"), violations


def _check_forbidden_dml(changed_files: list[str]) -> tuple[str, list[str]]:
    """Check changed files for forbidden DML on protected tables (DNA §5)."""
    violations = []
    for fpath in changed_files:
        if not fpath.endswith(".py"):
            continue
        content = _read_changed_file(fpath)
        if content is None:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            if _FORBIDDEN_DML_RE.search(line):
                violations.append(f"{fpath}:{i}: {line.strip()}")
    return ("fail" if violations else "pass"), violations


def _extract_signature(source: str, name: str) -> str | None:
    """Extract function/class signature as normalized string for hash comparison."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            args = ast.unparse(node.args)
            ret = ast.unparse(node.returns) if node.returns else "None"
            return f"def {name}({args}) -> {ret}"
        if isinstance(node, ast.ClassDef) and node.name == name:
            fields = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    ann = ast.unparse(item.annotation)
                    fields.append(f"{item.target.id}: {ann}")
            return f"class {name}({', '.join(fields)})"
    return None


def _check_pinned_api(changed_files: list[str]) -> tuple[str, list[str]]:
    """Check that pinned API signatures haven't been modified (DNA §4)."""
    violations = []
    for key, expected_hash in _PINNED_API_HASHES.items():
        rel_path, func_name = key.split("::")
        # Only check if the file is in the changed list
        matched = [f for f in changed_files if f.replace("\\", "/").endswith(rel_path)]
        if not matched:
            continue
        source = _read_changed_file(matched[0])
        if source is None:
            continue
        sig = _extract_signature(source, func_name)
        if sig is None:
            violations.append(f"{key}: signature not found (deleted or renamed?)")
            continue
        actual_hash = hashlib.sha256(sig.encode("utf-8")).hexdigest()[:16]
        if actual_hash != expected_hash:
            violations.append(
                f"{key}: signature changed (expected {expected_hash}, got {actual_hash})"
            )
    return ("fail" if violations else "pass"), violations


def run_preflight_guards(changed_files: list[str], trace_id: str) -> dict:
    """
    Deterministic preflight hard guards — runs BEFORE any LLM audit.

    Checks DNA §3/§4/§5 constraints without any LLM calls.
    Always writes an audit artifact (even on BLOCKED) for evidence trail.

    Returns:
        {"passed": bool, "results": {guard: "pass"|"fail"}, "blocked_by": str|None}
    """
    from datetime import datetime, timezone

    results = {}
    blocked_by = None

    # Guard: frozen files (DNA §3)
    frozen_patterns = {
        "core/", "domain/reconciliation", "infra/guardian",
        "migrations/001", "migrations/002", "migrations/003",
    }
    touched_frozen = [f for f in changed_files if any(p in f for p in frozen_patterns)]
    results["frozen_files"] = "fail" if touched_frozen else "pass"
    if touched_frozen and not blocked_by:
        blocked_by = f"frozen_files: {touched_frozen[:5]}"

    # Guard: forbidden imports (DNA §5)
    imports_status, imports_violations = _check_forbidden_imports(changed_files)
    results["forbidden_imports"] = imports_status
    if imports_violations and not blocked_by:
        blocked_by = f"forbidden_imports: {imports_violations[:3]}"

    # Guard: forbidden DML patterns (DNA §5)
    dml_status, dml_violations = _check_forbidden_dml(changed_files)
    results["forbidden_dml"] = dml_status
    if dml_violations and not blocked_by:
        blocked_by = f"forbidden_dml: {dml_violations[:3]}"

    # Guard: pinned API signatures (DNA §4)
    api_status, api_violations = _check_pinned_api(changed_files)
    results["pinned_api"] = api_status
    if api_violations and not blocked_by:
        blocked_by = f"pinned_api: {api_violations[:3]}"

    passed = all(v == "pass" for v in results.values())

    # Always write artifact — even on BLOCKED (Fix 4: evidence trail)
    stub_guards = [k for k, v in results.items() if v == _STUB_VALUE]
    artifact = {
        "trace_id": trace_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "guard_type": "preflight_hard_guards",
        "passed": passed,
        "results": results,
        "blocked_by": blocked_by,
        "stub_guards": stub_guards,
        "changed_files": changed_files[:20],
    }
    artifact_path = LAST_AUDIT_RESULT_PATH.parent / "last_preflight_result.json"
    try:
        artifact_path.write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("preflight: failed to write artifact: %s", exc)

    logger.info(json.dumps({
        "trace_id": trace_id,
        "outcome": "preflight_complete",
        "passed": passed,
        "results": results,
        "blocked_by": blocked_by,
    }, ensure_ascii=False))

    return {"passed": passed, "results": results, "blocked_by": blocked_by}


def run_contract_check(
    stage_id: str,
    proposal_text: str,
    trace_id: str = "",
) -> dict:
    """
    Layer 0.5: Canonical Contract Gate.

    Deterministic verification of prerequisites, factual claims, and solution
    shape BEFORE any LLM audit. Produces verified_context for LLM auditors
    so they focus on residual engineering risk, not fact-checking.

    Returns compile_contract() result dict with status, prereqs, claims, shape,
    and verified_context suitable for passing to Layer 2 auditors.

    BLOCKED_PRECONDITION → hard block (prereqs not met).
    SHAPE_DEVIATION → advisory warning (LLM + owner decide).
    CLEAN → proceed to LLM audit.
    """
    from contract_compiler import compile_contract

    result = compile_contract(stage_id, proposal_text, trace_id)

    # Write artifact for evidence trail
    artifact_path = ROOT / "orchestrator" / "last_contract_check.json"
    artifact_path.write_text(json.dumps({
        "trace_id": trace_id,
        "stage_id": stage_id,
        "status": result["status"],
        "prereqs_passed": result["prereqs"]["passed"],
        "false_claims": result["verified_context"]["false_claims"],
        "shape_warnings": result["verified_context"]["shape_warnings"],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info(json.dumps({
        "trace_id": trace_id,
        "stage_id": stage_id,
        "status": result["status"],
        "outcome": "contract_check_complete",
    }, ensure_ascii=False))

    return result


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

    secrets, gemini_model, anthropic_model, anthropic_escalation = _init_auditors()

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
                verdict = await auditor.critique(scope_text, task_pack, context={})
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
):
    """
    Lean post-execution audit: single critique round (no mock revision, no escalation).

    Old protocol (ReviewRunner.execute): 4+ API calls per audit
      propose → 2× critique → mock revise → 2× final_audit → gate → (escalation: ×2)
    New protocol: 1 critique round = 2 API calls (Gemini + Anthropic)

    Cost reduction: ~4x fewer API calls.

    Returns ProtocolRun-compatible object with quality_gate, approval_route, critiques.
    """
    import sys
    from auditor_system.hard_shell.contracts import TaskPack, RiskLevel

    _orch_dir = Path(__file__).resolve().parent
    if str(_orch_dir) not in sys.path:
        sys.path.insert(0, str(_orch_dir))

    # --- Build lean proposal (only essential data) ---
    changed_files = packet.get("changed_files") or []
    test_results = packet.get("test_results") or {}
    affected_tiers = packet.get("affected_tiers") or []
    failed_tests = test_results.get("failed", 0)
    passed_tests = test_results.get("passed", "?")

    # Compact proposal — no fluff, just facts
    proposal_text = (
        f"Post-exec review: {trace_id}\n"
        f"Files ({len(changed_files)}): {', '.join(changed_files[:15])}\n"
        f"Tiers: {', '.join(affected_tiers) if affected_tiers else 'unknown'}\n"
        f"Tests: {passed_tests} passed, {failed_tests} failed\n"
        f"Directive:\n{directive_text[:1500]}"
    )

    risk_str = risk_class.lower()
    try:
        risk = RiskLevel(risk_str)
    except ValueError:
        risk = RiskLevel.SEMI

    task_id = manifest.get("current_task_id") or "unknown"

    task_pack = TaskPack(
        title=f"post-exec-review:{task_id}",
        description=manifest.get("current_sprint_goal") or "",
        roadmap_stage=task_id or "bootstrap",
        why_now="Post-execution semantic review",
        risk=risk,
        declared_surface=changed_files[:15],
    )

    logger.info(json.dumps({
        "trace_id": trace_id,
        "task_id": task_id,
        "risk": risk.value,
        "changed_files": len(changed_files),
        "outcome": "post_exec_audit_starting",
        "mode": "lean_single_round",
    }, ensure_ascii=False))

    # --- Tier 2: Single critique round with Sonnet (cheap) ---
    secrets, gemini_model, anthropic_model, anthropic_escalation = _init_auditors()

    from auditor_system.providers.gemini_auditor import GeminiAuditor
    from auditor_system.providers.anthropic_auditor import AnthropicAuditor
    from auditor_system.hard_shell.contracts import (
        ProtocolRun, QualityGateResult, ApprovalRoute,
    )

    auditors = [
        GeminiAuditor(model=gemini_model, api_key=secrets["GEMINI_API_KEY"]),
        AnthropicAuditor(model=anthropic_model, api_key=secrets["ANTHROPIC_API_KEY"]),
    ]

    async def _run_critique(auditor_list):
        verdicts = []
        for auditor in auditor_list:
            try:
                verdict = await auditor.critique(proposal_text, task_pack, context={})
                verdicts.append(verdict)
            except Exception as exc:
                logger.warning("post_exec_audit: auditor %s failed: %s",
                               auditor.auditor_id, exc)
        return verdicts

    verdicts = asyncio.run(_run_critique(auditors))

    # Check if ANY auditor (Gemini OR Sonnet) found critical issues.
    # Critical is deterministic: driven by IssueSeverity.CRITICAL enum in verdict schema.
    has_critical = any(
        issue.severity.value == "critical"
        for v in verdicts
        for issue in v.issues
    )

    escalated = False
    escalation_tier = ""
    if has_critical:
        # Identify which auditor(s) raised critical
        critical_sources = [
            v.auditor_id for v in verdicts
            if any(i.severity.value == "critical" for i in v.issues)
        ]
        critical_count = sum(
            1 for v in verdicts for i in v.issues if i.severity.value == "critical"
        )
        logger.info(json.dumps({
            "trace_id": trace_id,
            "outcome": "auditor_found_critical",
            "critical_count": critical_count,
            "critical_sources": critical_sources,
            "risk_class": risk_class,
        }, ensure_ascii=False))

        # Escalation: API critical verdict is never overridden by non-API entity.
        # No CLI filter — CLI has conflict of interest (same brain as executor).

        if risk_class == "CORE":
            # CORE: escalate to Opus API for authoritative second opinion
            print(f"[audit] {critical_sources} found {critical_count} critical "
                  f"— escalating to Opus API (CORE)...")
            opus_auditor = AnthropicAuditor(
                model=anthropic_escalation, api_key=secrets["ANTHROPIC_API_KEY"],
            )
            opus_verdicts = asyncio.run(_run_critique([opus_auditor]))

            if opus_verdicts:
                verdicts = [v for v in verdicts if v.auditor_id != "anthropic"] + opus_verdicts
                escalated = True
                escalation_tier = "opus_api"

                has_critical = any(
                    issue.severity.value == "critical"
                    for v in verdicts
                    for issue in v.issues
                )
                logger.info(json.dumps({
                    "trace_id": trace_id,
                    "outcome": "opus_api_escalation_complete",
                    "opus_verdict": opus_verdicts[0].verdict.value,
                    "still_critical": has_critical,
                }, ensure_ascii=False))
        else:
            # SEMI: critical from API → owner review (no auto-PASS, no Opus API spend)
            escalated = True
            escalation_tier = "owner_review"
            logger.info(json.dumps({
                "trace_id": trace_id,
                "outcome": "semi_critical_to_owner",
                "critical_count": critical_count,
                "critical_sources": critical_sources,
            }, ensure_ascii=False))

    # --- Build ProtocolRun-compatible result ---
    run = ProtocolRun(task=task_pack)
    run.proposal = proposal_text
    run.critiques = verdicts
    run.final_verdicts = verdicts
    run.escalated = escalated
    if escalated:
        run.escalation_reason = f"critical:{escalation_tier}"

    run.quality_gate = QualityGateResult(
        passed=not has_critical and len(verdicts) > 0,
        reason="no critical issues" if not has_critical else "critical issues found",
    )

    # Approval routing:
    # - CORE: NEVER auto_pass. Always INDIVIDUAL_REVIEW (→ JUDGE + owner).
    #   Opus clearing = "forwarded to JUDGE", NOT "approved".
    # - SEMI: NEVER auto_pass. Always BATCH_APPROVAL (→ owner ACCEPT).
    #   Per Master Plan: "SEMI: commit/merge только с owner approval".
    # - LOW: auto_pass if gate passed.
    if has_critical:
        run.approval_route = ApprovalRoute.BLOCKED
    elif risk_class == "CORE":
        # CORE always goes to JUDGE — even if gate passed
        run.approval_route = ApprovalRoute.INDIVIDUAL_REVIEW
    elif risk_class == "SEMI":
        # SEMI always needs owner ACCEPT — never auto-pass
        run.approval_route = ApprovalRoute.BATCH_APPROVAL
    elif run.quality_gate.passed:
        # LOW with clean gate — auto pass
        run.approval_route = ApprovalRoute.AUTO_PASS
    else:
        run.approval_route = ApprovalRoute.INDIVIDUAL_REVIEW

    run.mark_finished()

    tier = escalation_tier if escalated else "sonnet"
    logger.info(json.dumps({
        "trace_id": trace_id,
        "run_id": run.run_id,
        "gate_passed": run.quality_gate.passed,
        "approval_route": run.approval_route.value,
        "auditor_verdicts": {v.auditor_id: v.verdict.value for v in verdicts},
        "escalated": escalated,
        "outcome": "post_exec_audit_complete",
        "tier": tier,
    }, ensure_ascii=False))

    return run


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


def _cli_single_pass(prompt: str, timeout: int = 90) -> dict | None:
    """Run a single CLI pass. Returns parsed JSON dict or None on failure."""
    import re

    try:
        proc = subprocess.run(
            ["claude", "--print", "--no-session-persistence"],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=str(ROOT),
        )
        if proc.returncode != 0:
            return None

        response = proc.stdout.strip()
        response_clean = re.sub(r"```(?:json)?\s*", "", response).strip()
        start = response_clean.find("{")
        if start >= 0:
            end = response_clean.rfind("}")
            if end > start:
                try:
                    return json.loads(response_clean[start:end + 1])
                except json.JSONDecodeError:
                    pass
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def run_cli_prescreen_sync(
    packet: dict,
    directive_text: str,
    trace_id: str,
    risk_class: str,
    retry_count: int,
) -> dict:
    """
    Single-pass CLI pre-screening with structured Chain-of-Thought ($0, subscription).

    Uses one pass with built-in self-critique (devil's advocate pattern)
    instead of multiple passes of the same LLM confirming itself.

    This is NOT a governance verdict and has NO authority to trigger retries
    or block execution. It produces a RECOMMENDATION that the orchestrator
    policy (main.py) consumes to decide whether to spend API budget.
    The retry/escalation decision is made by the orchestrator, not by this function.

    Returns:
        {
            "passed": bool,
            "verdict": "prescreen_pass" | "prescreen_fail" | "prescreen_skip",
            "critique": str,
            "tier": "cli_prescreen",
        }
    """
    changed_files = packet.get("changed_files") or []
    test_results = packet.get("test_results") or {}

    prompt = (
        "You are a strict code quality auditor. Review this execution result.\n\n"
        f"Task (retry #{retry_count}, risk: {risk_class})\n"
        f"Changed files ({len(changed_files)}): {', '.join(changed_files[:15])}\n"
        f"Tests: passed={test_results.get('passed', '?')} "
        f"failed={test_results.get('failed', '?')}\n"
        f"Directive:\n{directive_text[:1500]}\n\n"
        "Follow this exact analysis chain:\n"
        "1. List ALL potential problems you see (scope violations, missing tests, "
        "regressions, policy violations, unsafe patterns)\n"
        "2. For each problem, play devil's advocate: is this a real issue or a "
        "false alarm? What evidence supports/contradicts it?\n"
        "3. Keep only problems that survived step 2\n\n"
        "Output ONLY a JSON object:\n"
        '{"passed": true/false, "issues": ["surviving issue 1", ...], '
        '"summary": "one line verdict"}\n\n'
        "PASS only if: tests pass, changes scoped to declared files, "
        "no regressions, no policy violations."
    )

    data = _cli_single_pass(prompt)
    if data is None:
        logger.warning("cli_prescreen: failed to parse CLI response")
        return {"passed": True, "verdict": "prescreen_skip", "critique": "",
                "tier": "cli_prescreen"}

    passed = bool(data.get("passed", True))
    issues = data.get("issues", [])
    critique = "\n".join(f"- {iss}" for iss in issues) if issues else ""

    logger.info(json.dumps({
        "trace_id": trace_id,
        "outcome": "cli_prescreen_complete",
        "passed": passed,
        "issues_count": len(issues),
    }, ensure_ascii=False))

    return {
        "passed": passed,
        "verdict": "prescreen_pass" if passed else "prescreen_fail",
        "critique": critique,
        "tier": "cli_prescreen",
    }


def _init_auditors():
    """Load API keys and create auditor instances (shared by multiple functions)."""
    import yaml
    from auditor_system.runner_factory import _load_secrets_safe, _CONFIG_PATH

    secrets = _load_secrets_safe()
    models_config = {}
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            models_config = yaml.safe_load(f) or {}

    auditors_cfg = models_config.get("auditors", {})
    gemini_model = auditors_cfg.get("gemini", "gemini-2.5-pro")
    anthropic_model = auditors_cfg.get("anthropic", "claude-sonnet-4-6")
    anthropic_escalation = auditors_cfg.get("anthropic_escalation", "claude-opus-4-6")
    return secrets, gemini_model, anthropic_model, anthropic_escalation


def _call_anthropic_revise(
    api_key: str,
    model: str,
    original_proposal: str,
    critique_text: str,
    task_context: str,
) -> str:
    """Call Anthropic API to revise a proposal based on critique.

    This is NOT using the auditor role — it's using Claude as an architect
    to produce a revised proposal text. Returns the revised proposal markdown.
    """
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed, returning original proposal")
        return original_proposal

    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = (
        "You are an architecture reviewer revising a proposal based on critique feedback.\n"
        "Your job: take the original proposal and the critic's structured feedback,\n"
        "then produce an IMPROVED version of the proposal that addresses all critical\n"
        "and warning-level issues raised by the critic.\n\n"
        "Rules:\n"
        "1. Output ONLY the revised proposal in Markdown format.\n"
        "2. Do NOT argue with the critic — address their concerns.\n"
        "3. If a concern is about missing information, add it.\n"
        "4. If a concern is about risk, add mitigation steps.\n"
        "5. Keep the same structure as the original proposal.\n"
        "6. Mark what changed with [REVISED] tags so the critic can see updates.\n"
    )

    user_msg = (
        f"## Task Context\n{task_context}\n\n"
        f"## Original Proposal\n{original_proposal}\n\n"
        f"## Critic Feedback (address ALL issues below)\n{critique_text}\n\n"
        "Now produce the revised proposal:"
    )

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        temperature=0.3,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
    )

    return response.content[0].text if response.content else original_proposal


def negotiate_architecture(
    task_pack,
    initial_proposal: str,
    task_context: str = "",
    max_attempts: int = 3,
) -> dict:
    """
    Pre-execution architectural convergence loop (Phase 2: Dual Consensus).

    Runs a negotiate loop between Architect (Anthropic/Claude) and Critic (Gemini):
      1. Critic reviews proposal (scope, risk, architecture — NOT code)
      2. If approved → converged
      3. If reject/concerns with critical issues → Architect revises
      4. Repeat up to max_attempts
      5. If no convergence → BLOCKED_BY_CONSENSUS

    Args:
        task_pack: TaskPack instance
        initial_proposal: The architectural proposal text to review
        task_context: Additional context for the architect revision
        max_attempts: Maximum number of critique→revise iterations

    Returns:
        {
            "converged": bool,
            "proposal": str,           # final (possibly revised) proposal
            "iterations": int,          # how many rounds ran
            "history": list[dict],      # per-round {attempt, verdict, concerns, revised}
            "final_verdict": str,       # "approve" | "concerns" | "reject"
            "auditor_verdicts": dict,   # last round's verdicts
        }
    """
    import sys
    _orch_dir = Path(__file__).resolve().parent
    if str(_orch_dir) not in sys.path:
        sys.path.insert(0, str(_orch_dir))

    secrets, gemini_model, anthropic_model, anthropic_escalation = _init_auditors()

    from auditor_system.providers.gemini_auditor import GeminiAuditor
    critic = GeminiAuditor(model=gemini_model, api_key=secrets["GEMINI_API_KEY"])

    proposal = initial_proposal
    history = []
    converged = False
    last_verdicts = {}

    for attempt in range(max_attempts):
        logger.info(json.dumps({
            "trace_id": getattr(task_pack, "title", "?"),
            "outcome": "negotiate_round_start",
            "attempt": attempt + 1,
            "max_attempts": max_attempts,
        }, ensure_ascii=False))

        # --- Step 1: Critic reviews proposal ---
        try:
            verdict = asyncio.run(
                critic.critique(proposal, task_pack, context={})
            )
        except Exception as exc:
            logger.error("negotiate_architecture: critic failed on attempt %d: %s",
                         attempt + 1, exc)
            history.append({
                "attempt": attempt + 1,
                "verdict": "error",
                "error": str(exc),
                "revised": False,
            })
            continue

        last_verdicts = {critic.auditor_id: verdict.verdict.value}

        # Extract structured concerns
        concerns = []
        has_critical = False
        for issue in verdict.issues:
            if issue.severity.value == "critical":
                has_critical = True
            concerns.append(
                f"[{issue.severity.value}] {issue.area}: {issue.description}"
            )

        round_info = {
            "attempt": attempt + 1,
            "verdict": verdict.verdict.value,
            "summary": verdict.summary,
            "concerns": concerns,
            "critical_count": verdict.critical_count,
            "warning_count": verdict.warning_count,
            "revised": False,
        }

        # --- Step 2: Check if converged ---
        if verdict.verdict.value == "approve" or (
            verdict.verdict.value == "concerns" and not has_critical
        ):
            # Proposal Consensus: approve or concerns-without-critical = converged
            round_info["revised"] = False
            history.append(round_info)
            converged = True
            logger.info(json.dumps({
                "trace_id": getattr(task_pack, "title", "?"),
                "outcome": "negotiate_converged",
                "attempt": attempt + 1,
                "verdict": verdict.verdict.value,
            }, ensure_ascii=False))
            break

        # --- Step 3: Critic rejected — Architect revises ---
        critique_text = f"Verdict: {verdict.verdict.value}\nSummary: {verdict.summary}\n\n"
        critique_text += "Issues:\n"
        for c in concerns:
            critique_text += f"  - {c}\n"

        try:
            revised = _call_anthropic_revise(
                api_key=secrets["ANTHROPIC_API_KEY"],
                model=anthropic_model,
                original_proposal=proposal,
                critique_text=critique_text,
                task_context=task_context,
            )
            proposal = revised
            round_info["revised"] = True
        except Exception as exc:
            logger.error("negotiate_architecture: architect revision failed: %s", exc)
            round_info["revision_error"] = str(exc)

        history.append(round_info)

        logger.info(json.dumps({
            "trace_id": getattr(task_pack, "title", "?"),
            "outcome": "negotiate_round_complete",
            "attempt": attempt + 1,
            "verdict": verdict.verdict.value,
            "revised": round_info["revised"],
            "concerns_count": len(concerns),
        }, ensure_ascii=False))

    if not converged:
        logger.warning(json.dumps({
            "trace_id": getattr(task_pack, "title", "?"),
            "outcome": "negotiate_blocked_by_consensus",
            "iterations": len(history),
            "max_attempts": max_attempts,
        }, ensure_ascii=False))

    return {
        "converged": converged,
        "proposal": proposal,
        "iterations": len(history),
        "history": history,
        "final_verdict": history[-1]["verdict"] if history else "no_rounds",
        "auditor_verdicts": last_verdicts,
    }


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

    print("TaskPack created:")
    print(f"  title:          {task_pack.title}")
    print(f"  roadmap_stage:  {task_pack.roadmap_stage}")
    print(f"  why_now:        {task_pack.why_now}")
    print(f"  risk:           {task_pack.risk}")
    print(f"  declared_surface: {task_pack.declared_surface}")
    print()
    print("(skipping run_audit_sync — requires .env.auditors)")
