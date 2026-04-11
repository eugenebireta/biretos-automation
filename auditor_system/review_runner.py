"""
review_runner.py — главный protocol brain.

Orchestrates multi-round debate protocol:
  Round 1: Dual critique (parallel, isolated — auditors don't see each other)
  Fast path: all approve + no critical → skip to gate
  Round 2: Debate (parallel, cross-visible — each sees peer's Round 1 verdict)
  Round 3: Opus arbiter if still disagree after debate
  Quality Gate → ApprovalRouter → route

Design based on 7 external critiques consensus:
  - Debate instead of voting
  - Compact context, not 69KB blob
  - Cross-visibility in Round 2, not Round 1
  - Opus arbiter as separate black box module

Один прогон = одна чистая сессия (SPEC §19.1).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from .debate import build_arbiter_pack, needs_arbiter, should_debate
from .hard_shell.approval_router import ApprovalRouter
from .hard_shell.context_assembler import ContextAssembler
from .hard_shell.contracts import (
    ApprovalRoute,
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
from .providers.base import AuditorProvider, BuilderProvider

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
        # Round 1: Dual critique (parallel, isolated — no cross-visibility)
        # =====================================================================
        critique_tasks = [
            auditor.critique(run.proposal, task, context)
            for auditor in self.auditors
        ]
        critiques = await self._gather_safe(critique_tasks, task, stage="critique")
        run.critiques = list(critiques)
        for i, verdict in enumerate(run.critiques, start=1):
            self.run_store.save_critique(run, verdict, i)
        logger.info(
            "review_runner: R1 critiques run_id=%s verdicts=%s",
            run.run_id, {v.auditor_id: v.verdict.value for v in run.critiques},
        )

        # =====================================================================
        # Fast path: all approve + no critical → skip debate, use R1 as final
        # =====================================================================
        if not should_debate(run.critiques, task.risk):
            logger.info(
                "review_runner: FAST PATH — all R1 approve, skip debate run_id=%s",
                run.run_id,
            )
            run.revised_proposal = run.proposal  # no revision needed
            self.run_store.save_revised_proposal(run)
            run.final_verdicts = list(run.critiques)  # promote R1 to final
            for i, verdict in enumerate(run.final_verdicts, start=1):
                self.run_store.save_final_verdict(run, verdict, i)
            gate = self.quality_gate.check(run.final_verdicts)
            run.quality_gate = gate
            self.run_store.save_quality_gate(run)
        else:
            # =================================================================
            # Builder revision (fresh proposal from R1 critiques)
            # =================================================================
            run.revised_proposal = await self.builder.revise(
                task, run.proposal, run.critiques, context
            )
            self.run_store.save_revised_proposal(run)

            # =================================================================
            # Round 2: Debate (parallel, cross-visible)
            # Each auditor sees the revised proposal + peer's R1 verdict
            # =================================================================
            run.debate_triggered = True
            debate_tasks = self._build_debate_tasks(
                run.revised_proposal, task, context, run.critiques,
            )
            debate_verdicts = await self._gather_safe(
                debate_tasks, task, stage="debate",
            )
            run.debate_verdicts = list(debate_verdicts)
            run.final_verdicts = list(debate_verdicts)  # R2 becomes final by default
            for i, verdict in enumerate(run.debate_verdicts, start=1):
                self.run_store.save_final_verdict(run, verdict, i)
            logger.info(
                "review_runner: R2 debate run_id=%s verdicts=%s",
                run.run_id, {v.auditor_id: v.verdict.value for v in run.debate_verdicts},
            )

            # =============================================================
            # Gate check after Round 2
            # =============================================================
            gate = self.quality_gate.check(run.final_verdicts)
            run.quality_gate = gate
            self.run_store.save_quality_gate(run)

            # =============================================================
            # Round 3: Opus arbiter if still disagreement
            # =============================================================
            if needs_arbiter(run.debate_verdicts, gate) and self.arbiter is not None:
                run.arbiter_used = True
                logger.info(
                    "review_runner: R3 arbiter triggered run_id=%s",
                    run.run_id,
                )
                arbiter_pack = build_arbiter_pack(
                    run.proposal, run.revised_proposal,
                    run.critiques, run.debate_verdicts,
                )
                arbiter_verdict = await self.arbiter.arbitrate(
                    task, context, arbiter_pack,
                )
                run.arbiter_verdict = arbiter_verdict
                run.final_verdicts = [arbiter_verdict]  # arbiter overrides
                gate = self.quality_gate.check(run.final_verdicts)
                run.quality_gate = gate
                self.run_store.save_quality_gate(run)
                logger.info(
                    "review_runner: R3 arbiter verdict=%s run_id=%s",
                    arbiter_verdict.verdict.value, run.run_id,
                )

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
            "review_runner: DONE run_id=%s route=%s debate=%s arbiter=%s duration_min=%.1f",
            run.run_id,
            route.value,
            run.debate_triggered,
            run.arbiter_used,
            run.duration_minutes or 0,
        )
        return run

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
