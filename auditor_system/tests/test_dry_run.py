"""
tests/test_dry_run.py — Phase 1 dry-run тест.

Критерий готовности Phase 1 (SPEC Phase 1):
  ✓ Одна задача (mock) прошла полный цикл
  ✓ Артефакты лежат в runs/<run_id>/
  ✓ ModelSelector автоматически выбрал модель + effort
  ✓ QualityGate отработал
  ✓ ApprovalRouter дал маршрут
  ✓ owner_summary.md читается человеком
  ✓ ExperienceSink записал JSONL (после owner verdict)
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from ..hard_shell.contracts import (
    ApprovalRoute,
    AuditIssue,
    IssueSeverity,
    ModelName,
    ProtocolRun,
    RiskLevel,
    TaskPack,
)
from ..providers.mock_auditor import (
    make_approve_auditor,
    make_concerns_auditor,
    make_reject_auditor,
)
from ..providers.mock_builder import MockBuilder
from ..review_runner import ReviewRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_runner(tmp_path: Path, auditors=None) -> ReviewRunner:
    if auditors is None:
        auditors = [make_approve_auditor("mock_openai"), make_approve_auditor("mock_anthropic")]
    return ReviewRunner(
        builder=MockBuilder(),
        auditors=auditors,
        runs_dir=tmp_path / "runs",
        experience_dir=tmp_path,
    )


def run_sync(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Тест 1: полный цикл — артефакты на диске
# ---------------------------------------------------------------------------

def test_full_cycle_artifacts_exist(tmp_path):
    """Одна задача через полный цикл → все артефакты в runs/<run_id>/."""
    task = TaskPack(
        title="Test: update photo scout config",
        roadmap_stage="R1",
        why_now="Needed before next scout batch",
        risk=RiskLevel.LOW,
    )
    runner = make_runner(tmp_path)
    run = run_sync(runner.execute(task))

    run_dir = tmp_path / "runs" / run.run_id
    assert run_dir.exists(), f"Run dir missing: {run_dir}"

    expected_files = [
        "task_pack.json",
        "policy_context.json",
        "builder_proposal.md",
        "auditor_1_critique.json",
        "auditor_2_critique.json",
        "revised_proposal.md",
        "auditor_1_final.json",
        "auditor_2_final.json",
        "quality_gate_result.json",
        "approval_routing.json",
        "owner_summary.md",
        "run_manifest.json",
    ]
    for fname in expected_files:
        fpath = run_dir / fname
        assert fpath.exists(), f"Missing artifact: {fname}"


# ---------------------------------------------------------------------------
# Тест 2: ModelSelector — LOW → Sonnet low
# ---------------------------------------------------------------------------

def test_model_selector_low_risk(tmp_path):
    task = TaskPack(
        title="LOW task",
        roadmap_stage="R1",
        why_now="Test",
        risk=RiskLevel.LOW,
    )
    runner = make_runner(tmp_path)
    run = run_sync(runner.execute(task))

    assert run.model_used == ModelName.SONNET
    assert not run.escalated


# ---------------------------------------------------------------------------
# Тест 3: ModelSelector — CORE surface → Opus high
# ---------------------------------------------------------------------------

def test_model_selector_opus_for_core_surface(tmp_path):
    task = TaskPack(
        title="Update FSM state transitions",
        roadmap_stage="5.5",
        why_now="Iron Fence before Revenue",
        risk=RiskLevel.SEMI,
        keywords=["fsm", "guardian"],  # тригеррит OPUS_SURFACES
    )
    runner = make_runner(tmp_path)
    run = run_sync(runner.execute(task))

    assert run.model_used == ModelName.OPUS
    assert not run.escalated  # Surface-based, не escalation


# ---------------------------------------------------------------------------
# Тест 4: Quality Gate — critical reject → INDIVIDUAL_REVIEW
# ---------------------------------------------------------------------------

def test_quality_gate_critical_reject(tmp_path):
    task = TaskPack(
        title="SEMI task with critical issue",
        roadmap_stage="R1",
        why_now="Test",
        risk=RiskLevel.SEMI,
    )
    runner = make_runner(
        tmp_path,
        auditors=[
            make_reject_auditor("mock_openai", critical=True),
            make_approve_auditor("mock_anthropic"),
        ],
    )
    run = run_sync(runner.execute(task))

    assert run.approval_route == ApprovalRoute.INDIVIDUAL_REVIEW
    assert run.quality_gate is not None
    assert not run.quality_gate.passed


# ---------------------------------------------------------------------------
# Тест 5: Escalation — Sonnet fails → Opus escalation
# ---------------------------------------------------------------------------

def test_escalation_sonnet_to_opus(tmp_path):
    """Sonnet + reject → escalation to Opus → если Opus approve → route решается."""
    task = TaskPack(
        title="SEMI task needing escalation",
        roadmap_stage="R1",
        why_now="Test escalation",
        risk=RiskLevel.SEMI,
    )

    # Первый аудитор всегда reject (для Sonnet раунда)
    # Второй approve — но reject с critical всё равно проваливает gate
    # После escalation оба approve
    call_count = {"n": 0}

    class ToggleAuditor:
        auditor_id = "toggle"

        async def critique(self, proposal, task, context):
            from ..hard_shell.contracts import AuditVerdict, AuditVerdictValue
            call_count["n"] += 1
            # Первые 4 вызова (critique+final, Sonnet) → reject; следующие (Opus) → approve
            if call_count["n"] <= 4:
                return AuditVerdict(
                    auditor_id=self.auditor_id,
                    verdict=AuditVerdictValue.REJECT,
                    summary="reject round 1",
                    issues=[AuditIssue(severity=IssueSeverity.CRITICAL, area="test", description="critical")],
                )
            return AuditVerdict(
                auditor_id=self.auditor_id,
                verdict=AuditVerdictValue.APPROVE,
                summary="approve round 2",
                issues=[],
            )

        async def final_audit(self, revised, task, context):
            return await self.critique(revised, task, context)

    runner = ReviewRunner(
        builder=MockBuilder(),
        auditors=[ToggleAuditor(), ToggleAuditor()],
        runs_dir=tmp_path / "runs",
        experience_dir=tmp_path,
    )
    run = run_sync(runner.execute(task))

    assert run.escalated
    assert run.model_used == ModelName.OPUS


# ---------------------------------------------------------------------------
# Тест 6: ApprovalRouter — LOW + approve → AUTO_PASS
# ---------------------------------------------------------------------------

def test_approval_low_auto_pass(tmp_path):
    task = TaskPack(
        title="LOW approved task",
        roadmap_stage="R1",
        why_now="Test auto pass",
        risk=RiskLevel.LOW,
    )
    runner = make_runner(tmp_path)
    run = run_sync(runner.execute(task))

    assert run.approval_route == ApprovalRoute.AUTO_PASS


# ---------------------------------------------------------------------------
# Тест 7: ApprovalRouter — SEMI + approve → BATCH_APPROVAL
# ---------------------------------------------------------------------------

def test_approval_semi_batch(tmp_path):
    task = TaskPack(
        title="SEMI approved task",
        roadmap_stage="R1",
        why_now="Test batch",
        risk=RiskLevel.SEMI,
    )
    runner = make_runner(tmp_path)
    run = run_sync(runner.execute(task))

    assert run.approval_route == ApprovalRoute.BATCH_APPROVAL


# ---------------------------------------------------------------------------
# Тест 8: CORE → INDIVIDUAL_REVIEW (всегда)
# ---------------------------------------------------------------------------

def test_approval_core_individual(tmp_path):
    task = TaskPack(
        title="CORE task always individual",
        roadmap_stage="5.5",
        why_now="Core change",
        risk=RiskLevel.CORE,
    )
    runner = make_runner(tmp_path)
    run = run_sync(runner.execute(task))

    assert run.approval_route == ApprovalRoute.INDIVIDUAL_REVIEW


# ---------------------------------------------------------------------------
# Тест 9: owner_summary.md читается (содержит ключевые поля)
# ---------------------------------------------------------------------------

def test_owner_summary_readable(tmp_path):
    task = TaskPack(
        title="Readable summary task",
        roadmap_stage="R1",
        why_now="Test readability",
        risk=RiskLevel.LOW,
    )
    runner = make_runner(tmp_path)
    run = run_sync(runner.execute(task))

    summary_path = tmp_path / "runs" / run.run_id / "owner_summary.md"
    assert summary_path.exists()
    content = summary_path.read_text(encoding="utf-8")
    assert "Owner Summary" in content
    assert "AUTO_PASS" in content or "BATCH" in content or "INDIVIDUAL" in content
    assert task.title in content


# ---------------------------------------------------------------------------
# Тест 10: ExperienceSink записывает JSONL после owner verdict
# ---------------------------------------------------------------------------

def test_experience_sink_after_verdict(tmp_path):
    task = TaskPack(
        title="Experience logging task",
        roadmap_stage="R1",
        why_now="Test exp log",
        risk=RiskLevel.LOW,
    )
    runner = make_runner(tmp_path)
    run = run_sync(runner.execute(task))

    # Устанавливаем owner verdict
    runner.record_owner_verdict(run, verdict="approved", post_audit_clean=True)

    # Проверяем что JSONL записался
    exp_files = list((tmp_path / "experience_log").glob("*.jsonl"))
    assert len(exp_files) == 1, f"Expected 1 JSONL, got {exp_files}"

    records = [json.loads(line) for line in exp_files[0].read_text().splitlines() if line.strip()]
    assert len(records) == 1
    rec = records[0]
    assert rec["owner_verdict"] == "approved"
    assert rec["task"]["risk"] == "low"
    assert rec["trace_id"] == run.trace_id


# ---------------------------------------------------------------------------
# Тест 11: ExperienceSink бросает ошибку если verdict не установлен
# ---------------------------------------------------------------------------

def test_experience_sink_requires_verdict(tmp_path):
    task = TaskPack(
        title="No verdict task",
        roadmap_stage="R1",
        why_now="Test guard",
        risk=RiskLevel.LOW,
    )
    runner = make_runner(tmp_path)
    run = run_sync(runner.execute(task))

    # owner_verdict не установлен → должна быть ошибка
    with pytest.raises(RuntimeError, match="owner_verdict"):
        runner.experience_sink.record(run)


# ---------------------------------------------------------------------------
# Тест 12: Surface mismatch логируется
# ---------------------------------------------------------------------------

def test_surface_mismatch_detected(tmp_path):
    task = TaskPack(
        title="Surface mismatch task",
        roadmap_stage="R1",
        why_now="Test mismatch",
        risk=RiskLevel.SEMI,
        keywords=["fsm"],                    # ContextAssembler → fsm_core_states
        declared_surface=["ledger_money"],   # Builder объявил другое
    )
    runner = make_runner(tmp_path)
    run = run_sync(runner.execute(task))

    assert run.surface is not None
    assert run.surface.mismatch
    # Эффективная поверхность = union
    assert "fsm_core_states" in run.surface.effective_surface
    assert "ledger_money" in run.surface.effective_surface
    # При mismatch → Opus (OPUS_SURFACES hit)
    assert run.model_used == ModelName.OPUS


# ---------------------------------------------------------------------------
# Тест 13: TaskPack без why_now → ошибка валидации
# ---------------------------------------------------------------------------

def test_task_requires_why_now():
    with pytest.raises(Exception):
        TaskPack(
            title="No why now",
            roadmap_stage="R1",
            why_now="",  # пустой → ошибка
            risk=RiskLevel.LOW,
        )


# ---------------------------------------------------------------------------
# Тест 14: Tier-1 file → tier1_files surface
# ---------------------------------------------------------------------------

def test_tier1_file_triggers_opus_surface(tmp_path):
    task = TaskPack(
        title="Touch tier-1 file",
        roadmap_stage="5.5",
        why_now="Emergency fix",
        risk=RiskLevel.CORE,
        affected_files=[".cursor/windmill-core-v1/domain/reconciliation_service.py"],
    )
    runner = make_runner(tmp_path)
    run = run_sync(runner.execute(task))

    assert run.surface is not None
    assert "tier1_files" in run.surface.classified_surface
    assert run.model_used == ModelName.OPUS
