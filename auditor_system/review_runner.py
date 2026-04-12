"""
review_runner.py — главный protocol brain.

Orchestrates Consensus Pipeline Protocol v1:
  L2 Loop (max 3): execute → assert → fix if fail → HALTED if all fail
  L1 Loop (max 2): blind critique → cross-validation → defect register →
                   repair → L2 re-run → repeat
  L3: bounded pipeline run on golden dataset
  JUDGE via ApprovalRouter → MERGE

Original rounds preserved within L1 loop:
  Round 1: Dual critique (parallel, isolated — auditors don't see each other)
  Fast path: all approve + no critical → skip debate
  Round 2: Debate (parallel, cross-visible — each sees peer's Round 1 verdict)
  Round 3: Opus arbiter if still disagree after debate

Design based on 7 external critiques + Consensus Pipeline Protocol v1:
  - L2 (CPU) runs BEFORE L1 (API) — no LLM calls on broken code
  - DefectRegister tracks issues across iterations
  - Builder repair is targeted (structured prompt), not "rewrite everything"
  - Critics review ALL defects + regressions in re-review passes
  - Frozen validation scripts = hard block if touched
  - Circuit breaker: max iterations prevent infinite loop

Один прогон = одна чистая сессия (SPEC §19.1).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from .debate import (
    build_arbiter_pack,
    build_repair_prompt,
    consolidate_defects,
    needs_arbiter,
    should_debate,
)
from .execution_gate import ExecutionGate, FrozenScriptViolationError
from .hard_shell.approval_router import ApprovalRouter
from .hard_shell.context_assembler import ContextAssembler
from .hard_shell.contracts import (
    ApprovalRoute,
    DefectRegister,
    ErrorClass,
    ProtocolRun,
    TaskPack,
)
from .hard_shell.experience_sink import ExperienceSink
from .hard_shell.fallback_handler import (
    AuditorFailureError,
    FallbackAction,
    FallbackHandler,
)
from .hard_shell.model_selector import ModelSelector
from .hard_shell.quality_gate import QualityGate
from .hard_shell.run_store import RunStore
from .hard_shell.schema_validator import SchemaViolationError
from .integration_gate import IntegrationGate
from .providers.base import AuditorProvider, BuilderProvider

# Consensus Pipeline Protocol v1 — circuit breaker limits
MAX_L2_ATTEMPTS = 3
MAX_L1_ITERATIONS = 2

logger = logging.getLogger(__name__)


class ReviewRunner:
    """
    Protocol brain — rule-based диспетчер.
    Не использует AI для принятия решений о маршрутизации.
    """

    def __init__(
        self,
        builder: BuilderProvider,
        auditors: list[AuditorProvider],
        runs_dir: str | Path = "runs",
        experience_dir: str | Path = ".",
        model_config_path: str | Path | None = None,
        arbiter: Any | None = None,
        execution_gate: ExecutionGate | None = None,
        integration_gate: IntegrationGate | None = None,
    ):
        if len(auditors) < 1:
            raise ValueError("At least one auditor required")

        self.builder = builder
        self.auditors = auditors
        self.arbiter = arbiter  # OpusArbiter or None (Round 3 black box)
        self.run_store = RunStore(runs_dir)
        self.experience_sink = ExperienceSink(experience_dir)
        self.context_assembler = ContextAssembler()
        self.model_selector = ModelSelector(model_config_path)
        self.quality_gate = QualityGate()
        self.approval_router = ApprovalRouter()
        self.fallback_handler = FallbackHandler()
        # Consensus Pipeline Protocol v1 gates (optional — soft-pass when None)
        self.execution_gate = execution_gate or ExecutionGate()
        self.integration_gate = integration_gate or IntegrationGate()

    async def _gather_safe(
        self,
        coros: list,
        task: TaskPack,
        stage: str,
    ) -> list:
        """
        Runs auditor coroutines with return_exceptions=True.
        Applies FallbackHandler on individual failures (SPEC §7).

        Returns: list of valid AuditVerdict
        Raises:  AuditorFailureError for CORE failures or unrecoverable SEMI failures
        """
        results = await asyncio.gather(*coros, return_exceptions=True)
        auditor_ids = [a.auditor_id for a in self.auditors]

        verdicts = []
        errors: list[tuple[str, Exception]] = []

        for auditor_id, result in zip(auditor_ids, results):
            if isinstance(result, Exception):
                errors.append((auditor_id, result))
                logger.error(
                    "review_runner: auditor_error "
                    "stage=%s auditor=%s error_class=TRANSIENT severity=ERROR retriable=true "
                    "error=%s",
                    stage, auditor_id, result,
                )
            else:
                verdicts.append(result)

        if not errors:
            return verdicts

        # Apply FallbackHandler for each failure
        for failed_id, exc in errors:
            other_result = verdicts[0] if verdicts else None
            action = self.fallback_handler.handle(
                task.risk, failed_id, other_result, stage
            )

            if action == FallbackAction.STOP_OWNER_ALERT:
                raise AuditorFailureError(failed_id, stage, str(exc))

            if action in (
                FallbackAction.RETRY_THEN_BLOCK,
                FallbackAction.RETRY_THEN_ONE_AUDITOR,
            ):
                # Phase 2 pilot: no retry infrastructure yet
                if not verdicts:
                    raise AuditorFailureError(
                        failed_id, stage,
                        f"Both auditors failed, no retry infrastructure: {exc}"
                    )
                # Fall through: use what we have

            # CONTINUE_ONE_AUDITOR* or fallthrough → log and continue with verdicts
            logger.warning(
                "review_runner: continuing with %d/%d auditor(s) "
                "after failure action=%s stage=%s",
                len(verdicts), len(self.auditors), action.value, stage,
            )

        return verdicts

    async def execute(
        self,
        task: TaskPack,
        owner_model_override: str | None = None,
    ) -> ProtocolRun:
        """
        Полный цикл: proposal → critique → debate → arbiter → gate → route.
        Возвращает ProtocolRun с артефактами.
        """
        run = ProtocolRun(task=task)
        logger.info(
            "review_runner: START run_id=%s trace_id=%s task=%s risk=%s",
            run.run_id, run.trace_id, task.title, task.risk.value,
        )

        try:
            return await self._execute_inner(run, task, owner_model_override)
        except AuditorFailureError as exc:
            run.error_class = ErrorClass.TRANSIENT
            run.error_message = str(exc)
            run.approval_route = ApprovalRoute.BLOCKED
            run.mark_finished()
            self.run_store.save_manifest(run)
            logger.error(
                "review_runner: BLOCKED due to auditor failure "
                "run_id=%s auditor=%s stage=%s error_class=TRANSIENT severity=ERROR retriable=false",
                run.run_id, exc.failed_auditor, exc.stage,
            )
            raise
        except SchemaViolationError as exc:
            run.error_class = ErrorClass.SCHEMA_VIOLATION
            run.error_message = str(exc)
            run.approval_route = ApprovalRoute.BLOCKED
            run.mark_finished()
            self.run_store.save_manifest(run)
            logger.error(
                "review_runner: BLOCKED due to schema violation "
                "run_id=%s auditor=%s error_class=SCHEMA_VIOLATION severity=ERROR retriable=false",
                run.run_id, exc.auditor_id,
            )
            raise

    async def _execute_inner(
        self,
        run: ProtocolRun,
        task: TaskPack,
        owner_model_override: str | None,
    ) -> ProtocolRun:
        """Inner execution — separated so execute() can catch and handle errors."""

        # --- Шаг 1: Surface classification ---
        surface = self.context_assembler.classify(task)
        run.surface = surface
        context = self.context_assembler.build_policy_context(task, surface)
        self.run_store.save_task(run)
        self.run_store.save_policy_context(run, context)

        # --- Шаг 2: Model selection (Trigger A или C) ---
        model, effort = self.model_selector.select(
            task.risk, surface.effective_surface, owner_model_override
        )
        run.model_used = model
        run.effort = effort
        logger.info(
            "review_runner: model_selected model=%s effort=%s surface=%s",
            model.value, effort.value, sorted(surface.effective_surface),
        )

        # --- Шаг 3: Builder proposal ---
        run.proposal = await self.builder.propose(task, context)
        self.run_store.save_proposal(run)
        logger.info("review_runner: proposal generated run_id=%s len=%d", run.run_id, len(run.proposal))

        # =====================================================================
        # Consensus Pipeline Protocol v1 — L2 → L1 → L3 repair loop
        # =====================================================================
        register = DefectRegister(run_id=run.run_id)
        run.defect_register = register

        # --- L2 Loop (max 3 attempts) ---
        l2_passed = await self._run_l2_loop(run, task, context)
        if not l2_passed:
            # Circuit breaker: HALTED after max L2 failures
            return run

        # --- L1 Loop (max 2 iterations) ---
        gate = await self._run_l1_loop(run, task, context)

        # If halted during L1, return early
        if run.halted:
            return run

        # --- L3 Gate (if configured) ---
        await self._run_l3_gate(run, task, context, register)
        if run.halted:
            return run

        # After L1 loop, promote final state for legacy compatibility
        # final_verdicts is set by _run_l1_loop
        gate = self.quality_gate.check_defect_register(register, run.l1_iteration)
        run.quality_gate = gate
        self.run_store.save_quality_gate(run)

        # --- ApprovalRouter ---
        route = self.approval_router.route(
            risk=task.risk,
            verdicts=run.final_verdicts,
            gate=gate,
            model_used=run.model_used,
        )
        run.approval_route = route
        self.run_store.save_approval_routing(run)

        # --- Owner summary ---
        summary = self.approval_router.build_owner_summary(
            route=route,
            risk=task.risk,
            verdicts=run.final_verdicts,
            gate=gate,
            task_title=task.title,
            roadmap_stage=task.roadmap_stage,
            model_used=run.model_used,
            escalated=run.escalated,
        )
        self.run_store.save_owner_summary(run, summary)

        # --- Финализация ---
        run.mark_finished()
        self.run_store.save_manifest(run)

        logger.info(
            "review_runner: DONE run_id=%s route=%s debate=%s arbiter=%s "
            "l2_iter=%d l1_iter=%d duration_min=%.1f",
            run.run_id,
            route.value,
            run.debate_triggered,
            run.arbiter_used,
            run.l2_iteration,
            run.l1_iteration,
            run.duration_minutes or 0,
        )
        return run

    async def _run_l2_loop(
        self,
        run: ProtocolRun,
        task: TaskPack,
        context: dict[str, Any],
    ) -> bool:
        """
        L2 execution loop (max 3 attempts).
        Returns True if L2 passed, False if HALTED.

        If task.test_commands is empty → soft pass (backward compat).
        """
        for attempt in range(MAX_L2_ATTEMPTS):
            run.l2_iteration = attempt

            # Check frozen validation scripts
            try:
                self.execution_gate.check_frozen_scripts(task, task.affected_files)
            except FrozenScriptViolationError as exc:
                run.halted = True
                run.halt_reason = str(exc)
                run.approval_route = ApprovalRoute.BLOCKED
                run.mark_finished()
                self.run_store.save_manifest(run)
                logger.error(
                    "review_runner: FROZEN_SCRIPT_VIOLATION run_id=%s: %s",
                    run.run_id, exc,
                )
                raise

            diff_stat = self.execution_gate.get_git_diff_stat()
            l2_report = await self.execution_gate.run(task, git_diff_stat=diff_stat)
            run.l2_reports.append(l2_report)
            self.run_store.save_l2_report(run, l2_report, attempt)

            logger.info(
                "review_runner: L2 attempt=%d all_pass=%s run_id=%s",
                attempt, l2_report.all_pass, run.run_id,
            )

            if l2_report.all_pass:
                return True  # L2 passed

            if attempt < MAX_L2_ATTEMPTS - 1:
                # Add L2 failures to register and ask builder to fix
                run.defect_register.add_from_l2_report(l2_report, iteration=attempt)
                repair_p = build_repair_prompt(run.defect_register, task.title)
                logger.info(
                    "review_runner: L2 failed, asking builder to repair attempt=%d run_id=%s",
                    attempt, run.run_id,
                )
                repaired, manifest = await self.builder.repair(
                    task, run.proposal, run.defect_register, repair_p, context
                )
                run.proposal = repaired
                run.repair_history.append(repaired)
                self.run_store.save_repair_manifest(run, manifest, attempt)
                self.run_store.save_repair_proposal(run, repaired, attempt)
                # Close defects that builder reported as FIXED (pending re-validation)
                run.defect_register.apply_repair_manifest(manifest)
            else:
                # Circuit breaker: max L2 attempts exhausted
                run.defect_register.add_from_l2_report(l2_report, iteration=attempt)
                for entry in run.defect_register.open_blockers:
                    entry.status = entry.status.__class__("HALTED")
                run.halted = True
                run.halt_reason = (
                    f"L2_CIRCUIT_BREAKER: {MAX_L2_ATTEMPTS} L2 attempts failed — "
                    f"requires architectural intervention. "
                    f"Last failure: {l2_report.failure_summary}"
                )
                run.approval_route = ApprovalRoute.BLOCKED
                run.mark_finished()
                self.run_store.save_manifest(run)
                logger.error(
                    "review_runner: L2 CIRCUIT_BREAKER run_id=%s reason=%s",
                    run.run_id, run.halt_reason,
                )
        return False

    async def _run_l1_loop(
        self,
        run: ProtocolRun,
        task: TaskPack,
        context: dict[str, Any],
    ) -> Any:
        """
        L1 critic loop (max 2 iterations).
        Returns final quality gate result.
        Populates run.final_verdicts, run.critiques, run.debate_verdicts.
        """
        register = run.defect_register
        current_proposal = run.proposal
        # Get latest L2 report for passing to critics
        latest_l2 = run.l2_reports[-1] if run.l2_reports else None

        for iteration in range(MAX_L1_ITERATIONS):
            run.l1_iteration = iteration
            logger.info(
                "review_runner: L1 iteration=%d starting run_id=%s",
                iteration, run.run_id,
            )

            if iteration == 0:
                # First iteration: fresh blind critique
                gate = await self._run_critique_cycle(
                    run, task, context, current_proposal, register, iteration, latest_l2
                )
            else:
                # Subsequent iterations: re-review with defect register context
                gate = await self._run_re_review_cycle(
                    run, task, context, current_proposal, register, iteration, latest_l2
                )

            # Save defect register after each L1 iteration
            self.run_store.save_defect_register(run, register, iteration)

            # Exit loop when gate passes OR register has no open blockers
            # Gate is authoritative: if gate passes (e.g. concerns with <3 warnings),
            # don't trigger repair loop even if register has MAJOR entries.
            if gate.passed or register.is_clean:
                logger.info(
                    "review_runner: L1 PASS iteration=%d gate=%s clean=%s run_id=%s",
                    iteration, gate.passed, register.is_clean, run.run_id,
                )
                return gate

            if iteration < MAX_L1_ITERATIONS - 1:
                # Repair and run L2 again before next L1 iteration
                repair_p = build_repair_prompt(register, task.title)
                logger.info(
                    "review_runner: L1 repair pass iteration=%d open_blockers=%d run_id=%s",
                    iteration, len(register.open_blockers), run.run_id,
                )
                repaired, manifest = await self.builder.repair(
                    task, current_proposal, register, repair_p, context
                )
                current_proposal = repaired
                run.proposal = repaired
                run.revised_proposal = repaired
                run.repair_history.append(repaired)
                self.run_store.save_repair_manifest(run, manifest, 100 + iteration)
                self.run_store.save_repair_proposal(run, repaired, 100 + iteration)
                register.apply_repair_manifest(manifest)

                # L2 re-run after repair
                diff_stat = self.execution_gate.get_git_diff_stat()
                l2_report = await self.execution_gate.run(task, git_diff_stat=diff_stat)
                run.l2_reports.append(l2_report)
                self.run_store.save_l2_report(run, l2_report, 100 + iteration)
                latest_l2 = l2_report

                if not l2_report.all_pass:
                    # L2 regression after repair: add new defects
                    register.add_from_l2_report(l2_report, iteration=100 + iteration)
                    logger.warning(
                        "review_runner: L2 regression after repair iteration=%d run_id=%s",
                        iteration, run.run_id,
                    )
            else:
                # Max L1 iterations exhausted — JUDGE or owner
                run.halted = True
                run.halt_reason = (
                    f"L1_CIRCUIT_BREAKER: {MAX_L1_ITERATIONS} L1 iterations — "
                    f"{len(register.open_blockers)} open blocker(s) remain. "
                    "Requires JUDGE or owner intervention."
                )
                run.approval_route = ApprovalRoute.INDIVIDUAL_REVIEW
                run.escalated = True
                run.escalation_reason = run.halt_reason
                logger.warning(
                    "review_runner: L1 CIRCUIT_BREAKER escalating to JUDGE run_id=%s",
                    run.run_id,
                )
                return gate

        return self.quality_gate.check_defect_register(register, run.l1_iteration)

    async def _run_critique_cycle(
        self,
        run: ProtocolRun,
        task: TaskPack,
        context: dict[str, Any],
        proposal: str,
        register: DefectRegister,
        iteration: int,
        latest_l2: Any,
    ) -> Any:
        """
        Full critique cycle: blind R1 → fast path check → debate → arbiter.
        Populates register with defects found.
        """
        # Build context with L2 report for critics
        critique_context = dict(context)
        if latest_l2:
            critique_context["l2_execution_summary"] = {
                "all_pass": latest_l2.all_pass,
                "exit_code": latest_l2.exit_code,
                "diff_stat": latest_l2.diff_stat[:300],
                "assertions": [a.model_dump() for a in latest_l2.assertions],
            }

        # Round 1: parallel isolated critique
        critique_tasks = [
            auditor.critique(proposal, task, critique_context)
            for auditor in self.auditors
        ]
        critiques = await self._gather_safe(critique_tasks, task, stage="critique")
        run.critiques = list(critiques)
        for i, verdict in enumerate(run.critiques, start=1):
            self.run_store.save_critique(run, verdict, i)
        logger.info(
            "review_runner: R1 critiques iter=%d run_id=%s verdicts=%s",
            iteration, run.run_id,
            {v.auditor_id: v.verdict.value for v in run.critiques},
        )

        # Fast path: all approve + no critical → skip debate
        if not should_debate(run.critiques, task.risk):
            logger.info(
                "review_runner: FAST PATH — all R1 approve, skip debate run_id=%s",
                run.run_id,
            )
            run.revised_proposal = proposal
            self.run_store.save_revised_proposal(run)
            run.final_verdicts = list(run.critiques)
            for i, verdict in enumerate(run.final_verdicts, start=1):
                self.run_store.save_final_verdict(run, verdict, i)
            gate = self.quality_gate.check(run.final_verdicts)
            run.quality_gate = gate
            self.run_store.save_quality_gate(run)
            # Add final verdict findings to register (fast path: all approve = no issues)
            consolidate_defects(run.final_verdicts, iteration, existing_register=register)
            return gate

        # Builder revision (fresh proposal from R1 critiques)
        run.revised_proposal = await self.builder.revise(
            task, proposal, run.critiques, context
        )
        self.run_store.save_revised_proposal(run)

        # Round 2: Debate (parallel, cross-visible)
        run.debate_triggered = True
        debate_tasks = self._build_debate_tasks(
            run.revised_proposal, task, critique_context, run.critiques,
        )
        debate_verdicts = await self._gather_safe(debate_tasks, task, stage="debate")
        run.debate_verdicts = list(debate_verdicts)
        run.final_verdicts = list(debate_verdicts)
        for i, verdict in enumerate(run.debate_verdicts, start=1):
            self.run_store.save_final_verdict(run, verdict, i)
        logger.info(
            "review_runner: R2 debate iter=%d run_id=%s verdicts=%s",
            iteration, run.run_id,
            {v.auditor_id: v.verdict.value for v in run.debate_verdicts},
        )

        gate = self.quality_gate.check(run.final_verdicts)
        run.quality_gate = gate
        self.run_store.save_quality_gate(run)

        # Round 3: Opus arbiter if still disagreement
        if needs_arbiter(run.debate_verdicts, gate) and self.arbiter is not None:
            run.arbiter_used = True
            logger.info("review_runner: R3 arbiter triggered run_id=%s", run.run_id)
            arbiter_pack = build_arbiter_pack(
                proposal, run.revised_proposal,
                run.critiques, run.debate_verdicts,
            )
            arbiter_verdict = await self.arbiter.arbitrate(task, context, arbiter_pack)
            run.arbiter_verdict = arbiter_verdict
            run.final_verdicts = [arbiter_verdict]
            gate = self.quality_gate.check(run.final_verdicts)
            run.quality_gate = gate
            self.run_store.save_quality_gate(run)
            logger.info(
                "review_runner: R3 arbiter verdict=%s run_id=%s",
                arbiter_verdict.verdict.value, run.run_id,
            )

        # Add FINAL verdict findings to register (only once, after all rounds complete)
        # This ensures debate/arbiter resolution is reflected in the register
        consolidate_defects(run.final_verdicts, iteration, existing_register=register)

        return gate

    async def _run_re_review_cycle(
        self,
        run: ProtocolRun,
        task: TaskPack,
        context: dict[str, Any],
        proposal: str,
        register: DefectRegister,
        iteration: int,
        latest_l2: Any,
    ) -> Any:
        """
        Re-review cycle (iterations 2+): critics get defect register + repair manifest.
        Both critics review ALL defects (not just own) and check for regressions.
        """
        from .hard_shell.contracts import L2Report
        l2 = latest_l2 or L2Report(output_sample="[no L2 report available]")

        # Get latest repair manifest from run history
        repair_manifest = []  # Builder's repair entries (from most recent repair)

        re_review_tasks = [
            auditor.re_review(
                proposal,
                task,
                context,
                register,
                repair_manifest,
                l2,
                original_diff=run.proposal[:2000],  # original diff anchor
            )
            for auditor in self.auditors
        ]
        re_review_verdicts = await self._gather_safe(
            re_review_tasks, task, stage=f"re_review_{iteration}"
        )
        run.final_verdicts = list(re_review_verdicts)
        for i, verdict in enumerate(run.final_verdicts, start=1):
            self.run_store.save_final_verdict(run, verdict, i)

        # Update register: add any new defects found in re-review
        consolidate_defects(re_review_verdicts, iteration, existing_register=register)

        # Close defects that both critics confirmed as resolved
        # (conservative: issue needs explicit "approve" and no matching open defect)
        self._update_register_from_re_review(register, re_review_verdicts, iteration)

        gate = self.quality_gate.check_defect_register(register, iteration)
        run.quality_gate = gate
        self.run_store.save_quality_gate(run)

        logger.info(
            "review_runner: re_review iter=%d verdicts=%s open_blockers=%d run_id=%s",
            iteration, {v.auditor_id: v.verdict.value for v in run.final_verdicts},
            len(register.open_blockers), run.run_id,
        )
        return gate

    def _update_register_from_re_review(
        self,
        register: DefectRegister,
        re_review_verdicts: list,
        iteration: int,
    ) -> None:
        """
        Update defect statuses based on re-review results.
        - ALL approve → close FIXED_PENDING (repair confirmed)
        - ANY reject or concerns with critical → reopen FIXED_PENDING (repair not confirmed)
        """
        from .hard_shell.contracts import AuditVerdictValue, DefectStatus
        all_approve = all(
            v.verdict == AuditVerdictValue.APPROVE for v in re_review_verdicts
        )
        any_critical_reject = any(
            v.verdict == AuditVerdictValue.REJECT and v.critical_count > 0
            for v in re_review_verdicts
        )
        if all_approve:
            for entry in register.entries:
                if entry.status == DefectStatus.FIXED_PENDING:
                    entry.status = DefectStatus.CLOSED
                    entry.validated_by = "+".join(v.auditor_id for v in re_review_verdicts)
                    entry.iteration_closed = iteration
            logger.info(
                "review_runner: all critics approve, closing FIXED_PENDING defects iter=%d",
                iteration,
            )
        elif any_critical_reject:
            # Repair not confirmed — reopen FIXED_PENDING defects
            for entry in register.entries:
                if entry.status == DefectStatus.FIXED_PENDING:
                    entry.status = DefectStatus.OPEN
            logger.info(
                "review_runner: critical reject in re_review, reopening FIXED_PENDING iter=%d",
                iteration,
            )

    async def _run_l3_gate(
        self,
        run: ProtocolRun,
        task: TaskPack,
        context: dict[str, Any],
        register: DefectRegister,
    ) -> None:
        """
        L3 integration gate: run golden dataset. Soft pass if not configured.
        On failure: add defects to register and try one more L2 pass.
        """
        l3_result = await self.integration_gate.run(task)

        if l3_result.skipped:
            logger.info("review_runner: L3 skipped (not configured) run_id=%s", run.run_id)
            return

        if l3_result.passed:
            logger.info(
                "review_runner: L3 PASSED cases=%d/%d run_id=%s",
                l3_result.cases_passed, l3_result.cases_total, run.run_id,
            )
            return

        # L3 failed: add regressions to register
        logger.warning(
            "review_runner: L3 FAILED cases=%d/%d run_id=%s",
            l3_result.cases_failed, l3_result.cases_total, run.run_id,
        )
        self.integration_gate.add_failures_to_register(l3_result, register, iteration=200)
        self.run_store.save_defect_register(run, register, iteration=200)

        # One repair + L2 attempt after L3 failure
        if register.open_blockers:
            repair_p = build_repair_prompt(register, task.title)
            repaired, manifest = await self.builder.repair(
                task, run.proposal, register, repair_p, context
            )
            run.proposal = repaired
            run.repair_history.append(repaired)
            self.run_store.save_repair_manifest(run, manifest, 200)
            register.apply_repair_manifest(manifest)

            # L2 re-run
            diff_stat = self.execution_gate.get_git_diff_stat()
            l2_report = await self.execution_gate.run(task, git_diff_stat=diff_stat)
            run.l2_reports.append(l2_report)
            self.run_store.save_l2_report(run, l2_report, 200)

            if not l2_report.all_pass:
                run.halted = True
                run.halt_reason = (
                    "L3_CIRCUIT_BREAKER: L3 regression and L2 repair failed — "
                    "requires architectural intervention."
                )
                run.approval_route = ApprovalRoute.BLOCKED
                run.mark_finished()
                self.run_store.save_manifest(run)
                logger.error(
                    "review_runner: L3 CIRCUIT_BREAKER run_id=%s", run.run_id
                )

    def _build_debate_tasks(
        self,
        proposal: str,
        task: TaskPack,
        context: dict[str, Any],
        round1_verdicts: list,
    ) -> list:
        """
        Build debate coroutines for Round 2.

        Each auditor gets the proposal + peer's Round 1 verdict (cross-visible).
        With 2 auditors: auditor[0] sees auditor[1]'s verdict and vice versa.
        With 1 auditor: falls back to final_audit (no peer to debate).
        """
        if len(self.auditors) < 2 or len(round1_verdicts) < 2:
            # Single auditor: no debate possible, use final_audit
            return [
                auditor.final_audit(proposal, task, context)
                for auditor in self.auditors
            ]

        tasks = []
        for i, auditor in enumerate(self.auditors):
            # Find peer verdict: the other auditor's R1 verdict
            peer_idx = 1 - i if len(self.auditors) == 2 else (i + 1) % len(self.auditors)
            peer_verdict = round1_verdicts[peer_idx]

            tasks.append(
                auditor.debate(proposal, task, context, peer_verdict)
            )
        return tasks

    def record_owner_verdict(
        self,
        run: ProtocolRun,
        verdict: str,
        notes: str = "",
        post_audit_clean: bool | None = None,
    ) -> None:
        """
        Записывает owner verdict и логирует в ExperienceSink.
        Вызывать СТРОГО после того как owner принял решение (SPEC §6.3).
        """
        run.owner_verdict = verdict
        run.owner_notes = notes
        run.post_audit_clean = post_audit_clean
        self.run_store.save_manifest(run)
        self.experience_sink.record(run)
        logger.info(
            "review_runner: owner_verdict recorded run_id=%s verdict=%s",
            run.run_id, verdict,
        )
