"""
review_runner.py — главный protocol brain.

Orchestrates bounded 2-round protocol (SPEC §4):
  1. Builder proposal
  2. Dual critique (parallel, auditors don't see each other)
  3. Builder revision (once)
  4. Dual final audit
  5. Quality Gate → escalation if needed (max 1)
  6. ApprovalRouter → route
  7. Save artifacts + owner_summary

Один прогон = одна чистая сессия (SPEC §19.1).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from .hard_shell.approval_router import ApprovalRouter
from .hard_shell.context_assembler import ContextAssembler
from .hard_shell.contracts import (
    ApprovalRoute,
    ModelName,
    ProtocolRun,
    RiskLevel,
    TaskPack,
)
from .hard_shell.experience_sink import ExperienceSink
from .hard_shell.model_selector import ModelSelector
from .hard_shell.quality_gate import QualityGate
from .hard_shell.run_store import RunStore
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
    ):
        if len(auditors) < 1:
            raise ValueError("At least one auditor required")

        self.builder = builder
        self.auditors = auditors
        self.run_store = RunStore(runs_dir)
        self.experience_sink = ExperienceSink(experience_dir)
        self.context_assembler = ContextAssembler()
        self.model_selector = ModelSelector(model_config_path)
        self.quality_gate = QualityGate()
        self.approval_router = ApprovalRouter()

    async def execute(
        self,
        task: TaskPack,
        owner_model_override: str | None = None,
    ) -> ProtocolRun:
        """
        Полный цикл: proposal → critique → revision → final → gate → route.
        Возвращает ProtocolRun с артефактами.
        """
        run = ProtocolRun(task=task)
        logger.info(
            "review_runner: START run_id=%s trace_id=%s task=%s risk=%s",
            run.run_id, run.trace_id, task.title, task.risk.value,
        )

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

        # --- Шаг 4: Dual critique (параллельно, аудиторы не видят друг друга) ---
        critique_tasks = [
            auditor.critique(run.proposal, task, context)
            for auditor in self.auditors
        ]
        critiques = await asyncio.gather(*critique_tasks)
        run.critiques = list(critiques)
        for i, verdict in enumerate(run.critiques, start=1):
            self.run_store.save_critique(run, verdict, i)
        logger.info(
            "review_runner: critiques received run_id=%s verdicts=%s",
            run.run_id, {v.auditor_id: v.verdict.value for v in run.critiques},
        )

        # --- Шаг 5: Builder revision (один раз) ---
        run.revised_proposal = await self.builder.revise(
            task, run.proposal, run.critiques, context
        )
        self.run_store.save_revised_proposal(run)

        # --- Шаг 6: Dual final audit (параллельно) ---
        final_tasks = [
            auditor.final_audit(run.revised_proposal, task, context)
            for auditor in self.auditors
        ]
        final_verdicts = await asyncio.gather(*final_tasks)
        run.final_verdicts = list(final_verdicts)
        for i, verdict in enumerate(run.final_verdicts, start=1):
            self.run_store.save_final_verdict(run, verdict, i)
        logger.info(
            "review_runner: final verdicts run_id=%s verdicts=%s",
            run.run_id, {v.auditor_id: v.verdict.value for v in run.final_verdicts},
        )

        # --- Шаг 7: Quality Gate ---
        gate = self.quality_gate.check(run.final_verdicts)
        run.quality_gate = gate
        self.run_store.save_quality_gate(run)

        # --- Шаг 8: Escalation (Trigger B, max 1 раз) ---
        if not gate.passed and not run.escalated:
            escalation = self.model_selector.escalate(run.model_used)
            if escalation is not None:
                new_model, new_effort = escalation
                run.escalated = True
                run.escalation_reason = f"quality_gate_failed: {gate.reason}"
                run.model_used = new_model
                run.effort = new_effort
                logger.info(
                    "review_runner: ESCALATING to %s run_id=%s reason=%s",
                    new_model.value, run.run_id, gate.reason,
                )
                # Повторяем proposal → critique → revision → final с Opus
                run.proposal = await self.builder.propose(task, context)
                critiques_opus = await asyncio.gather(*[
                    a.critique(run.proposal, task, context) for a in self.auditors
                ])
                run.critiques = list(critiques_opus)
                run.revised_proposal = await self.builder.revise(
                    task, run.proposal, run.critiques, context
                )
                final_opus = await asyncio.gather(*[
                    a.final_audit(run.revised_proposal, task, context) for a in self.auditors
                ])
                run.final_verdicts = list(final_opus)
                gate = self.quality_gate.check(run.final_verdicts)
                run.quality_gate = gate
                self.run_store.save_quality_gate(run)
                logger.info(
                    "review_runner: post-escalation gate passed=%s run_id=%s",
                    gate.passed, run.run_id,
                )

        # --- Шаг 9: ApprovalRouter ---
        route = self.approval_router.route(
            risk=task.risk,
            verdicts=run.final_verdicts,
            gate=gate,
            model_used=run.model_used,
        )
        run.approval_route = route
        self.run_store.save_approval_routing(run)

        # --- Шаг 10: Owner summary ---
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
            "review_runner: DONE run_id=%s route=%s duration_min=%.1f",
            run.run_id,
            route.value,
            run.duration_minutes or 0,
        )
        return run

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
