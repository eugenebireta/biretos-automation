"""
phase_runner.py — FSM phase executor for the autonomous loop.

Runs ONE phase per invocation based on manifest.fsm_state.
The watcher IS the loop: it detects phase states and re-spawns main.py.

Phase flow:
    planning → building → testing → auditing → evaluating
                                                    ↓
                                    ready / building (correction) /
                                    planning (rethink) / escalated / blocked

Strangler pattern: _phase_building wraps the existing executor_bridge
as a black box. Future batches will extract pieces from it.

Usage:
    from phase_runner import PhaseRunner
    runner = PhaseRunner(cfg)
    updated_manifest = runner.run_phase(manifest)
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"

# Ensure project root is in sys.path for cross-package imports
import sys as _sys  # noqa: E402
if str(ROOT) not in _sys.path:
    _sys.path.insert(0, str(ROOT))
if str(ORCH_DIR) not in _sys.path:
    _sys.path.insert(0, str(ORCH_DIR))
DIRECTIVE_PATH = ORCH_DIR / "orchestrator_directive.md"
RUNS_DIR = ORCH_DIR / "runs"

# Phase states that the watcher should trigger on
PHASE_STATES = frozenset({
    "planning", "building", "testing", "auditing", "evaluating",
})

# Terminal/wait states — watcher should NOT trigger
WAIT_STATES = frozenset({
    "idle", "completed", "error", "blocked", "blocked_by_consensus",
    "awaiting_owner_reply", "escalated",
})

MAX_RETRIES = 3

# Notification-worthy state changes (for Telegram/MAX)
NOTIFY_STATES = frozenset({"ready", "escalated", "blocked"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def recover_manifest_from_handoff(manifest: dict) -> dict:
    """Recover manifest.fsm_state from handoff pack if they diverge.

    Handoff pack is the source of truth for phase state.
    If manifest and handoff disagree (crash between two writes),
    trust handoff.

    Returns manifest (possibly updated). No-op if consistent or no handoff.
    """
    run_dir = manifest.get("_run_dir", "")
    if not run_dir:
        return manifest

    try:
        from handoff import HandoffPack
        pack = HandoffPack.load_or_none(run_dir)
        if pack is None:
            return manifest

        handoff_phase = pack.phase
        manifest_state = manifest.get("fsm_state", "")

        # Only recover if both are phase states and they disagree
        if (handoff_phase in PHASE_STATES
                and manifest_state in PHASE_STATES
                and handoff_phase != manifest_state):
            logger.warning(
                "phase_runner: state mismatch — manifest=%s handoff=%s "
                "→ trusting handoff (source of truth)",
                manifest_state, handoff_phase,
            )
            manifest["fsm_state"] = handoff_phase
            manifest["_recovered_from_handoff"] = True
    except Exception as exc:
        logger.debug("phase_runner: handoff recovery skipped: %s", exc)

    return manifest


class PhaseRunner:
    """Executes one FSM phase and returns updated manifest."""

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.max_retries = int(cfg.get("max_retries", MAX_RETRIES))

    def run_phase(self, manifest: dict) -> dict:
        """Dispatch to the appropriate phase handler.

        Returns updated manifest with new fsm_state.
        """
        # Recovery: trust handoff over manifest if they diverge
        manifest = recover_manifest_from_handoff(manifest)

        state = manifest.get("fsm_state", "")
        handler = {
            "planning":   self._phase_planning,
            "building":   self._phase_building,
            "testing":    self._phase_testing,
            "auditing":   self._phase_auditing,
            "evaluating": self._phase_evaluating,
        }.get(state)

        if handler is None:
            logger.debug("phase_runner: no handler for state=%s", state)
            return manifest

        trace_id = manifest.get("trace_id", "")
        logger.info(
            "phase_runner: start phase=%s trace_id=%s attempt=%d",
            state, trace_id, manifest.get("attempt_count", 1),
        )

        try:
            manifest = handler(manifest)
        except Exception as exc:
            logger.error(
                "phase_runner: phase_error phase=%s trace_id=%s "
                "error_class=TRANSIENT severity=ERROR retriable=true error=%s",
                state, trace_id, exc,
            )
            manifest["fsm_state"] = "error"
            manifest["last_verdict"] = f"PHASE_ERROR_{state.upper()}"
            manifest["park_reason"] = f"#phase_error: {state}: {str(exc)[:200]}"

        manifest["updated_at"] = _now()
        return manifest

    # ------------------------------------------------------------------
    # Phase: PLANNING
    # ------------------------------------------------------------------
    def _phase_planning(self, manifest: dict) -> dict:
        """Planning phase: advisor + experience + optional critique.

        1. Load experience from past runs
        2. Call advisor for plan/directive
        3. One round of Gemini critique (if SEMI/CORE)
        4. Write approved plan to handoff pack
        5. Transition to 'building'
        """
        from handoff import HandoffPack, PlanResult

        trace_id = manifest.get("trace_id", "")
        task_id = manifest.get("current_task_id", "")
        risk_class = manifest.get("_last_risk_class", "LOW")
        run_dir = manifest.get("_run_dir", "")

        if not run_dir:
            run_dir = str(RUNS_DIR / trace_id)
            manifest["_run_dir"] = run_dir
            Path(run_dir).mkdir(parents=True, exist_ok=True)

        # Load or create handoff pack
        pack = HandoffPack.load_or_none(run_dir)
        if pack is None:
            pack = HandoffPack(
                trace_id=trace_id,
                task_id=task_id,
                sprint_goal=manifest.get("current_sprint_goal", ""),
                risk_class=risk_class,
                phase="planning",
            )

        # Step 1: Read experience
        lessons = ""
        try:
            from experience_reader import get_lessons_for_task
            lessons = get_lessons_for_task(task_id, risk_class=risk_class)
            if lessons:
                logger.info("phase_runner: injecting %d chars of experience", len(lessons))
        except Exception as exc:
            logger.warning("phase_runner: experience_reader failed: %s", exc)

        # Step 2: Build context + call advisor
        try:
            from intake import build_context_bundle
            from classifier import classify as run_classify
            from advisor import call_advisor

            bundle = build_context_bundle(manifest)
            classification = run_classify(bundle)
            advisor_result = call_advisor(
                bundle, trace_id,
                classifier_risk=classification.risk_class,
                extra_context=lessons,
            )

            if advisor_result.escalated:
                manifest["fsm_state"] = "escalated"
                manifest["last_verdict"] = "ESCALATE"
                manifest["park_reason"] = (
                    f"#advisor_escalation: {advisor_result.escalation_reason[:200]}"
                )
                pack.phase = "escalated"
                pack.save(run_dir)
                return manifest

            verdict = advisor_result.verdict
        except Exception as exc:
            logger.error("phase_runner: planning failed: %s", exc)
            manifest["fsm_state"] = "error"
            manifest["last_verdict"] = "PLANNING_FAILED"
            manifest["park_reason"] = f"#planning_error: {str(exc)[:200]}"
            return manifest

        # Step 3: Build directive
        from synthesizer import synthesize as run_synthesizer
        synth = run_synthesizer(
            classification, verdict,
            attempt_count=manifest.get("attempt_count", 1),
            last_packet_status=bundle.last_status,
            max_attempts=self.max_retries + 1,
            declared_risk=manifest.get("_last_risk_class"),
        )

        # Step 4: Write directive file
        directive_text = self._build_directive(
            manifest, synth, verdict, lessons,
            pack.format_experience_for_directive(),
        )
        DIRECTIVE_PATH.write_text(directive_text, encoding="utf-8")

        # Save directive to run dir too
        Path(run_dir, "directive.md").write_text(directive_text, encoding="utf-8")

        # Step 5: Optional critique for SEMI/CORE (1 round max)
        critique_text = ""
        approved_by = []
        if risk_class in ("SEMI", "CORE"):
            critique_text, approved_by = self._critique_plan(
                directive_text, manifest, trace_id,
            )
            if critique_text:
                # Revise directive with critique
                directive_text = self._revise_directive_with_critique(
                    directive_text, critique_text,
                )
                DIRECTIVE_PATH.write_text(directive_text, encoding="utf-8")
                Path(run_dir, "directive.md").write_text(
                    directive_text, encoding="utf-8",
                )

        # Step 6: Save plan to handoff pack
        pack.plan = PlanResult(
            summary=manifest.get("current_sprint_goal", ""),
            scope=synth.approved_scope[:50] if hasattr(synth, 'approved_scope') else [],
            approved_by=approved_by,
            risk_class=risk_class,
            directive_text=directive_text[:5000],  # truncate for pack size
            critique=critique_text[:2000],
        )
        pack.phase = "building"
        pack.save(run_dir)

        # Snapshot HEAD for later revert
        try:
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
            )
            if head.returncode == 0:
                manifest["_base_commit"] = head.stdout.strip()
        except Exception:
            pass

        # Transition
        manifest["fsm_state"] = "building"
        manifest["last_verdict"] = "PLAN_APPROVED"
        logger.info(
            "phase_runner: planning complete trace_id=%s, moving to building",
            trace_id,
        )
        return manifest

    def _critique_plan(
        self, directive_text: str, manifest: dict, trace_id: str,
    ) -> tuple[str, list[str]]:
        """One round of Gemini critique on the plan. Returns (critique, approved_by)."""
        approved_by = []
        critique_text = ""
        try:
            from core_gate_bridge import run_scope_review_sync
            from auditor_system.hard_shell.contracts import TaskPack, RiskLevel

            risk_class = manifest.get("_last_risk_class", "LOW")
            task_pack = TaskPack(
                task_id=manifest.get("current_task_id", "plan-review"),
                title=manifest.get("current_sprint_goal", "")[:200],
                roadmap_stage=manifest.get("current_task_id", "").split("-")[0]
                if "-" in manifest.get("current_task_id", "") else "R1",
                why_now="planning phase critique",
                risk=RiskLevel(risk_class.lower()),
            )
            result = run_scope_review_sync(task_pack, scope_text=directive_text[:3000])
            if result.get("passed"):
                approved_by = list(result.get("auditor_verdicts", {}).keys())
            critique_text = "; ".join(result.get("concerns", []))[:2000]
        except Exception as exc:
            logger.warning("phase_runner: plan critique failed (non-fatal): %s", exc)
        return critique_text, approved_by

    def _build_directive(
        self, manifest: dict, synth: Any, verdict: Any,
        lessons: str, experience_block: str,
    ) -> str:
        """Build the directive markdown from synthesizer + advisor output."""
        # This replicates the directive building logic from main.py
        # but in a clean, isolated way
        trace_id = manifest.get("trace_id", "")
        task_id = manifest.get("current_task_id", "")
        sprint_goal = manifest.get("current_sprint_goal", "")
        risk_class = manifest.get("_last_risk_class", "LOW")

        sections = [
            "# Orchestrator Directive\n",
            f"**trace_id:** `{trace_id}`\n",
            f"**task_id:** `{task_id}`\n",
            f"**risk:** `{risk_class}`\n",
            f"**attempt:** {manifest.get('attempt_count', 1)}\n",
            f"\n## Sprint Goal\n\n{sprint_goal}\n",
        ]

        if hasattr(synth, 'approved_scope') and synth.approved_scope:
            sections.append(f"\n## Approved Scope ({len(synth.approved_scope)} files)\n")
            for f in synth.approved_scope[:30]:
                sections.append(f"- `{f}`")
            sections.append("")

        if hasattr(verdict, 'next_step') and verdict.next_step:
            sections.append(f"\n## Advisor Guidance\n\n{verdict.next_step}\n")

        if hasattr(synth, 'rule_trace') and synth.rule_trace:
            sections.append(f"\n## Rules\n\n{synth.rule_trace}\n")

        if lessons:
            sections.append(f"\n{lessons}\n")

        if experience_block:
            sections.append(f"\n{experience_block}\n")

        return "\n".join(sections)

    def _revise_directive_with_critique(
        self, directive: str, critique: str,
    ) -> str:
        """Append critique section to directive for executor awareness."""
        return (
            directive
            + f"\n\n## Planning Critique (address these concerns)\n\n{critique}\n"
        )

    # ------------------------------------------------------------------
    # Phase: BUILDING
    # ------------------------------------------------------------------
    def _phase_building(self, manifest: dict) -> dict:
        """Building phase: run executor via strangler-wrapped executor_bridge.

        Strangler pattern: calls the existing executor_bridge.run_with_collect()
        as a black box. Stores result in handoff pack.
        Does NOT run acceptance/audit — that's for testing/auditing phases.
        """
        from handoff import HandoffPack, BuildResult

        trace_id = manifest.get("trace_id", "")
        run_dir = manifest.get("_run_dir", "")

        pack = HandoffPack.load(run_dir)

        # Run executor
        try:
            import executor_bridge as _eb

            timeout = int(self.cfg.get("executor_timeout_seconds", 600))
            base_commit = manifest.get("_base_commit")

            exec_result, packet = _eb.run_with_collect(
                directive_path=DIRECTIVE_PATH,
                trace_id=trace_id,
                base_commit=base_commit,
                run_pytest=bool(self.cfg.get("auto_pytest", False)),
                timeout=timeout,
            )

            # Store raw packet for testing phase
            if packet is not None:
                packet_path = Path(run_dir) / "packet.json"
                packet_path.write_text(
                    json.dumps(packet, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

            pack.build = BuildResult(
                changed_files=packet.get("changed_files", []) if packet else [],
                diff_stat=packet.get("diff_stat", "") if packet else "",
                base_commit=base_commit or "",
                executor_status=exec_result.status,
                exit_code=exec_result.exit_code,
                elapsed_seconds=exec_result.elapsed_seconds,
                executor_notes=(exec_result.stdout or "")[:500],
            )

            if exec_result.status != "completed":
                pack.record_experience(
                    verdict=f"executor_{exec_result.status}",
                    critique=exec_result.stderr[:500] if exec_result.stderr else "",
                )
                pack.phase = "evaluating"  # let evaluator decide retry/block
                pack.save(run_dir)
                manifest["fsm_state"] = "evaluating"
                manifest["last_verdict"] = f"BUILD_{exec_result.status.upper()}"
                return manifest

            if packet is None:
                pack.record_experience(verdict="collect_failed")
                pack.phase = "evaluating"
                pack.save(run_dir)
                manifest["fsm_state"] = "evaluating"
                manifest["last_verdict"] = "COLLECT_FAILED"
                return manifest

        except Exception as exc:
            logger.error("phase_runner: building failed: %s", exc)
            manifest["fsm_state"] = "error"
            manifest["last_verdict"] = "BUILD_ERROR"
            manifest["park_reason"] = f"#build_error: {str(exc)[:200]}"
            return manifest

        # Success — move to testing
        pack.phase = "testing"
        pack.save(run_dir)
        manifest["fsm_state"] = "testing"
        manifest["last_verdict"] = "BUILD_COMPLETED"
        logger.info(
            "phase_runner: building complete trace_id=%s files=%d, moving to testing",
            trace_id, len(pack.build.changed_files),
        )
        return manifest

    # ------------------------------------------------------------------
    # Phase: TESTING
    # ------------------------------------------------------------------
    def _phase_testing(self, manifest: dict) -> dict:
        """Testing phase: acceptance check + batch quality gate.

        Deterministic, no API cost. Blocks before expensive audit phase.
        """
        from handoff import HandoffPack, TestResult

        trace_id = manifest.get("trace_id", "")
        run_dir = manifest.get("_run_dir", "")
        risk_class = manifest.get("_last_risk_class", "LOW")

        pack = HandoffPack.load(run_dir)

        # Load packet from build phase
        packet_path = Path(run_dir) / "packet.json"
        if not packet_path.exists():
            manifest["fsm_state"] = "error"
            manifest["last_verdict"] = "NO_PACKET"
            return manifest
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        # Batch quality gate (deterministic)
        try:
            import batch_quality_gate as _bqg
            gate_result = _bqg.check_packet(packet, expected_risk=risk_class)
        except Exception as exc:
            logger.error("phase_runner: batch gate error: %s", exc)
            gate_result = type('GateResult', (), {
                'passed': False, 'rule': 'ERROR', 'reason': str(exc),
                'auto_merge_eligible': False,
            })()

        # Acceptance check
        try:
            import acceptance_checker as _ac
            directive_text = ""
            directive_path = Path(run_dir) / "directive.md"
            if directive_path.exists():
                directive_text = directive_path.read_text(encoding="utf-8")
            elif DIRECTIVE_PATH.exists():
                directive_text = DIRECTIVE_PATH.read_text(encoding="utf-8")

            acceptance = _ac.check(
                packet=packet,
                directive_text=directive_text,
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.error("phase_runner: acceptance check error: %s", exc)
            acceptance = type('Acceptance', (), {
                'passed': False, 'drift_detected': True,
                'out_of_scope_files': [], 'checks': [],
            })()

        failed_checks = [
            c.check_id for c in getattr(acceptance, 'checks', [])
            if not c.passed
        ]

        pack.test = TestResult(
            acceptance_passed=acceptance.passed,
            gate_passed=gate_result.passed,
            gate_rule=gate_result.rule,
            drift_detected=acceptance.drift_detected,
            out_of_scope_files=acceptance.out_of_scope_files[:10],
            failed_checks=failed_checks,
        )

        if not gate_result.passed:
            pack.record_experience(
                verdict="gate_failed",
                critique=gate_result.reason[:500] if hasattr(gate_result, 'reason') else "",
                failed_checks=failed_checks,
            )

        if not acceptance.passed:
            pack.record_experience(
                verdict="acceptance_failed",
                critique=f"drift={acceptance.drift_detected}, "
                         f"oos={acceptance.out_of_scope_files[:5]}",
                failed_checks=failed_checks,
            )

        # Write experience record
        try:
            import experience_writer as _ew
            _ew.write_execution_experience(
                trace_id=trace_id,
                task_id=manifest.get("current_task_id", "unknown"),
                risk_class=risk_class,
                acceptance_passed=acceptance.passed,
                acceptance_checks=[
                    {"check_id": c.check_id, "passed": c.passed, "detail": c.detail}
                    for c in getattr(acceptance, 'checks', [])
                ],
                drift_detected=acceptance.drift_detected,
                changed_files=packet.get("changed_files", []),
                elapsed_seconds=pack.build.elapsed_seconds if pack.build else 0,
                executor_status=pack.build.executor_status if pack.build else "unknown",
                gate_passed=gate_result.passed,
                gate_rule=gate_result.rule,
                out_of_scope_files=acceptance.out_of_scope_files,
            )
        except Exception as exc:
            logger.warning("phase_runner: experience write failed: %s", exc)

        # Decide next phase
        if gate_result.passed and acceptance.passed:
            if risk_class in ("SEMI", "CORE"):
                # Need audit before accepting
                pack.phase = "auditing"
                pack.save(run_dir)
                manifest["fsm_state"] = "auditing"
                manifest["last_verdict"] = "TESTS_PASSED"
            else:
                # LOW risk, skip audit → evaluating
                pack.phase = "evaluating"
                pack.save(run_dir)
                manifest["fsm_state"] = "evaluating"
                manifest["last_verdict"] = "TESTS_PASSED"
        else:
            # Tests failed → go to evaluating for retry/escalate decision
            pack.phase = "evaluating"
            pack.save(run_dir)
            manifest["fsm_state"] = "evaluating"
            manifest["last_verdict"] = "TESTS_FAILED"

        logger.info(
            "phase_runner: testing complete trace_id=%s gate=%s acceptance=%s → %s",
            trace_id, gate_result.passed, acceptance.passed, manifest["fsm_state"],
        )
        return manifest

    # ------------------------------------------------------------------
    # Phase: AUDITING
    # ------------------------------------------------------------------
    def _phase_auditing(self, manifest: dict) -> dict:
        """Auditing phase: dual audit (Gemini + Anthropic) + debate if conflict.

        Only runs for SEMI/CORE. LOW goes straight to evaluating.
        """
        from handoff import HandoffPack, AuditResult

        trace_id = manifest.get("trace_id", "")
        run_dir = manifest.get("_run_dir", "")
        risk_class = manifest.get("_last_risk_class", "LOW")

        pack = HandoffPack.load(run_dir)

        # Load packet + directive for audit
        packet_path = Path(run_dir) / "packet.json"
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        directive_path = Path(run_dir) / "directive.md"
        directive_text = ""
        if directive_path.exists():
            directive_text = directive_path.read_text(encoding="utf-8")

        # Preflight hard guards (deterministic, $0)
        try:
            from core_gate_bridge import run_preflight_guards
            preflight = run_preflight_guards(
                changed_files=packet.get("changed_files", []),
                trace_id=trace_id,
            )
            if not preflight["passed"]:
                pack.audit = AuditResult(
                    verdict="blocked",
                    critique_text=f"Preflight blocked: {preflight['blocked_by']}",
                )
                pack.record_experience(
                    verdict="preflight_blocked",
                    critique=str(preflight["blocked_by"]),
                )
                pack.phase = "evaluating"
                pack.save(run_dir)
                manifest["fsm_state"] = "evaluating"
                manifest["last_verdict"] = "PREFLIGHT_BLOCKED"
                return manifest
        except Exception as exc:
            logger.warning("phase_runner: preflight error (non-fatal): %s", exc)

        # Full API audit
        audit_verdict = None
        audit_critique_text = ""
        auditor_verdicts = {}
        run_id = ""
        debate_triggered = False
        arbiter_used = False

        try:
            from core_gate_bridge import (
                run_post_execution_audit_sync,
                extract_critique_text,
                _determine_fsm_state,
            )
            audit_result = run_post_execution_audit_sync(
                packet=packet,
                directive_text=directive_text,
                trace_id=trace_id,
                risk_class=risk_class,
                manifest=manifest,
            )
            audit_verdict = _determine_fsm_state(audit_result)
            audit_critique_text = extract_critique_text(audit_result)
            run_id = audit_result.run_id

            # Extract per-auditor verdicts
            for v in (audit_result.final_verdicts or []):
                auditor_verdicts[v.auditor_id] = v.verdict.value

            # Debate hook: if auditors disagree, trigger debate
            if len(audit_result.final_verdicts or []) >= 2:
                verdict_values = {v.verdict for v in audit_result.final_verdicts}
                if len(verdict_values) > 1:
                    # Conflict detected — try debate
                    debate_triggered = True
                    logger.info(
                        "phase_runner: auditor conflict detected, "
                        "triggering debate trace_id=%s",
                        trace_id,
                    )
                    try:
                        from auditor_system.debate import (
                            should_debate,
                            build_debate_context,
                            needs_arbiter,
                        )
                        if should_debate(audit_result.final_verdicts):
                            debate_ctx = build_debate_context(
                                audit_result.final_verdicts,
                            )
                            # For now, log debate context; full Round 2 in future batch
                            debate_path = Path(run_dir) / "debate_context.json"
                            debate_path.write_text(
                                json.dumps(debate_ctx, indent=2, default=str),
                                encoding="utf-8",
                            )
                            if needs_arbiter(audit_result.final_verdicts):
                                arbiter_used = True
                                logger.info(
                                    "phase_runner: arbiter needed trace_id=%s",
                                    trace_id,
                                )
                    except Exception as exc:
                        logger.warning(
                            "phase_runner: debate hook failed: %s", exc,
                        )

        except Exception as exc:
            logger.error("phase_runner: audit failed: %s", exc)
            # Retry once
            try:
                audit_result = run_post_execution_audit_sync(
                    packet=packet,
                    directive_text=directive_text,
                    trace_id=trace_id,
                    risk_class=risk_class,
                    manifest=manifest,
                )
                audit_verdict = _determine_fsm_state(audit_result)
                audit_critique_text = extract_critique_text(audit_result)
                run_id = audit_result.run_id
            except Exception as retry_exc:
                logger.error("phase_runner: audit retry failed: %s", retry_exc)
                manifest["fsm_state"] = "blocked"
                manifest["last_verdict"] = "POST_AUDIT_FAILED"
                manifest["park_reason"] = (
                    "#blocker: post-exec audit failed twice — owner review required"
                )
                return manifest

        # Determine if audit is complete (critique #6: debate-skipped awareness)
        # If auditors conflict and debate was triggered but not resolved,
        # the evaluating phase must know the audit is single-round only.
        conflict_detected = debate_triggered
        debate_resolved = arbiter_used  # arbiter = conflict actually resolved
        single_round = conflict_detected and not debate_resolved

        # Save audit result
        pack.audit = AuditResult(
            verdict=audit_verdict or "unknown",
            run_id=run_id,
            auditor_verdicts=auditor_verdicts,
            critique_text=audit_critique_text[:2000],
            debate_triggered=debate_triggered,
            debate_resolved=debate_resolved,
            arbiter_used=arbiter_used,
            single_round_only=single_round or not debate_triggered,
            critique_round=len(pack.critique_history) + 1,
        )

        # Accumulate critique
        pack.critique_history.append({
            "round": len(pack.critique_history) + 1,
            "attempt": pack.attempt,
            "verdict": audit_verdict,
            "auditor_verdicts": auditor_verdicts,
            "critique": audit_critique_text[:1000],
        })

        pack.phase = "evaluating"
        pack.save(run_dir)
        manifest["fsm_state"] = "evaluating"
        manifest["last_verdict"] = f"AUDIT_{(audit_verdict or 'unknown').upper()}"
        manifest["last_audit_result"] = {
            "run_id": run_id,
            "verdict": audit_verdict,
            "critique_rounds": len(pack.critique_history),
        }

        logger.info(
            "phase_runner: auditing complete trace_id=%s verdict=%s debate=%s",
            trace_id, audit_verdict, debate_triggered,
        )
        return manifest

    # ------------------------------------------------------------------
    # Phase: EVALUATING
    # ------------------------------------------------------------------
    def _phase_evaluating(self, manifest: dict) -> dict:
        """Evaluating phase: decide what to do next.

        Decision tree:
        1. Tests failed + retries left → correction (back to building)
        2. Tests failed + retries exhausted → escalate
        3. Audit passed → ready (task complete)
        4. Audit failed + retries left → correction (back to building)
        5. Audit failed + retries exhausted → escalate
        6. Audit blocked → blocked
        7. Build failed → retry or escalate
        """
        from handoff import HandoffPack, EvalDecision

        trace_id = manifest.get("trace_id", "")
        run_dir = manifest.get("_run_dir", "")
        risk_class = manifest.get("_last_risk_class", "LOW")

        pack = HandoffPack.load(run_dir)

        # Sync attempt from manifest (authoritative global counter).
        # This prevents infinite planning loops: even if handoff pack is
        # recreated with a new plan, the manifest counter survives.
        global_attempt = manifest.get("_global_attempt", pack.attempt)
        pack.attempt = global_attempt

        test = pack.test
        audit = pack.audit
        build = pack.build

        action = ""
        reason = ""
        next_phase = ""

        # Decision logic
        if build and build.executor_status != "completed":
            # Build failed
            if pack.can_retry():
                action = "correction"
                reason = f"Build failed: {build.executor_status}"
                next_phase = "building"
            else:
                action = "escalate"
                reason = f"Build failed after {pack.attempt} attempts"
                next_phase = "escalated"

        elif test and not test.gate_passed:
            # Gate failed
            action = "escalate"
            reason = f"Batch gate failed: {test.gate_rule}"
            next_phase = "escalated"
            # Revert executor commits
            self._revert_if_needed(manifest)

        elif test and not test.acceptance_passed:
            # Acceptance failed
            self._revert_if_needed(manifest)
            if pack.can_retry():
                action = "correction"
                reason = (
                    f"Acceptance failed: {test.failed_checks}, "
                    f"drift={test.drift_detected}"
                )
                next_phase = "building"
            else:
                action = "escalate"
                reason = f"Acceptance failed after {pack.attempt} attempts"
                next_phase = "escalated"

        elif audit and audit.verdict == "blocked":
            # Auditor blocked
            self._revert_if_needed(manifest)
            action = "blocked"
            reason = f"Auditor blocked: {audit.critique_text[:200]}"
            next_phase = "blocked"

        elif audit and audit.verdict == "audit_passed":
            # Check if audit was incomplete due to unresolved debate
            if audit.debate_triggered and not audit.debate_resolved:
                # Auditors conflicted, debate not resolved — treat as soft pass
                # with warning (don't block, but flag for future)
                action = "next_batch"
                reason = (
                    "Audit passed but debate unresolved "
                    "(single-round only, conflict not arbitrated)"
                )
                next_phase = "ready"
                logger.warning(
                    "phase_runner: audit_passed with unresolved debate "
                    "trace_id=%s — single_round_only=True",
                    trace_id,
                )
            else:
                action = "next_batch"
                reason = "All checks passed"
                next_phase = "ready"

        elif audit and audit.verdict in ("needs_owner_review", "audit_failed"):
            # Audit concerns
            self._revert_if_needed(manifest)
            if pack.can_retry():
                action = "correction"
                reason = f"Audit: {audit.verdict}: {audit.critique_text[:200]}"
                next_phase = "building"
            else:
                action = "escalate"
                reason = f"Audit failed after {pack.attempt} attempts"
                next_phase = "escalated"

        elif risk_class == "LOW" and test and test.acceptance_passed:
            # LOW risk, no audit needed, tests passed
            action = "next_batch"
            reason = "LOW risk: tests passed, no audit needed"
            next_phase = "ready"

        else:
            # Fallback
            action = "escalate"
            reason = "Unexpected state in evaluating"
            next_phase = "escalated"

        # Save decision
        pack.eval_decision = EvalDecision(
            action=action,
            reason=reason,
            next_phase=next_phase,
        )

        # Execute decision
        if action == "correction" and next_phase == "building":
            # Prepare retry: build fresh directive with experience
            pack.record_experience(
                verdict=reason[:100],
                critique=audit.critique_text[:500] if audit else "",
                failed_checks=test.failed_checks if test else [],
            )
            pack.reset_for_retry()
            pack.phase = "planning"  # re-plan with experience, not just re-build
            pack.save(run_dir)
            manifest["fsm_state"] = "planning"
            # Global attempt counter (critique #1: anti-infinite-loop)
            manifest["_global_attempt"] = pack.attempt
            manifest["retry_count"] = manifest.get("retry_count", 0) + 1
            manifest["_retry_reason"] = reason[:200]
            logger.info(
                "phase_runner: correction → re-planning attempt=%d trace_id=%s",
                pack.attempt, trace_id,
            )

        elif action == "next_batch":
            pack.phase = "completed"
            pack.save(run_dir)
            manifest["fsm_state"] = "ready"
            manifest["last_verdict"] = None
            manifest["retry_count"] = 0
            manifest.pop("_retry_reason", None)
            manifest.pop("_global_attempt", None)  # reset for next task
            logger.info(
                "phase_runner: task complete trace_id=%s, ready for next",
                trace_id,
            )

        elif action == "escalate":
            pack.phase = "escalated"
            pack.save(run_dir)
            manifest["fsm_state"] = "awaiting_owner_reply"
            manifest["last_verdict"] = "ESCALATED"
            manifest["park_reason"] = f"#escalation: {reason[:200]}"
            logger.info(
                "phase_runner: escalating trace_id=%s reason=%s",
                trace_id, reason[:100],
            )

        elif action == "blocked":
            pack.phase = "blocked"
            pack.save(run_dir)
            manifest["fsm_state"] = "blocked"
            manifest["last_verdict"] = "AUDIT_BLOCKED"
            manifest["park_reason"] = f"#blocker: {reason[:200]}"
            logger.info(
                "phase_runner: blocked trace_id=%s reason=%s",
                trace_id, reason[:100],
            )

        return manifest

    def _revert_if_needed(self, manifest: dict) -> None:
        """B10: revert executor commits back to base_commit."""
        base_commit = manifest.get("_base_commit")
        if not base_commit:
            return
        try:
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
            )
            if head.returncode != 0 or head.stdout.strip() == base_commit:
                return
            subprocess.run(
                ["git", "reset", "--soft", base_commit],
                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
            )
            subprocess.run(
                ["git", "restore", "--staged", "."],
                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
            )
            subprocess.run(
                ["git", "checkout", "--", "."],
                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
            )
            logger.info("phase_runner: reverted to %s", base_commit[:8])
        except Exception as exc:
            logger.warning("phase_runner: revert failed: %s", exc)
