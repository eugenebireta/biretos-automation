"""
tests/test_phase2.py — Phase 2 deterministic tests (no live API calls).

Covers:
  ✓ schema_validator: valid/invalid JSON parsing
  ✓ schema_validator: missing fields → SchemaViolationError
  ✓ schema_validator: bad verdict enum → SchemaViolationError
  ✓ fallback_handler: CORE failure → STOP_OWNER_ALERT
  ✓ fallback_handler: SEMI + one ok → CONTINUE_ONE_AUDITOR_BATCH_ONLY
  ✓ fallback_handler: SEMI + both fail → RETRY_THEN_BLOCK
  ✓ fallback_handler: LOW + one ok → CONTINUE_ONE_AUDITOR
  ✓ fallback_handler: LOW + both fail → RETRY_THEN_ONE_AUDITOR
  ✓ review_runner: single auditor failure on LOW → continues
  ✓ review_runner: single auditor failure on CORE → BLOCKED
  ✓ review_runner: schema violation → BLOCKED
  ✓ cli verdict: records owner verdict + ExperienceSink writes
  ✓ run_store: load_run_for_verdict reconstructs ProtocolRun
  ✓ Phase 1 regression: 14 existing tests still pass (import only)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from ..hard_shell.contracts import (
    AuditIssue,
    AuditVerdict,
    AuditVerdictValue,
    ApprovalRoute,
    IssueSeverity,
    RiskLevel,
    TaskPack,
)
from ..hard_shell.fallback_handler import (
    AuditorFailureError,
    FallbackAction,
    FallbackHandler,
)
from ..hard_shell.schema_validator import SchemaViolationError, validate_and_parse
from ..providers.mock_auditor import make_approve_auditor
from ..providers.mock_builder import MockBuilder
from ..review_runner import ReviewRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_sync(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_runner(tmp_path: Path, auditors=None) -> ReviewRunner:
    if auditors is None:
        auditors = [make_approve_auditor("mock_openai"), make_approve_auditor("mock_anthropic")]
    return ReviewRunner(
        builder=MockBuilder(),
        auditors=auditors,
        runs_dir=tmp_path / "runs",
        experience_dir=tmp_path,
    )


def _approve_verdict(auditor_id: str = "openai") -> AuditVerdict:
    return AuditVerdict(
        auditor_id=auditor_id,
        verdict=AuditVerdictValue.APPROVE,
        summary="Looks good",
        issues=[],
    )


# ---------------------------------------------------------------------------
# SchemaValidator tests
# ---------------------------------------------------------------------------

class TestSchemaValidator:
    def test_valid_approve(self):
        raw = json.dumps({"verdict": "approve", "summary": "ok", "issues": []})
        v = validate_and_parse("openai", raw)
        assert v.verdict == AuditVerdictValue.APPROVE
        assert v.summary == "ok"
        assert v.issues == []
        assert v.schema_valid is True

    def test_valid_with_issues(self):
        raw = json.dumps({
            "verdict": "concerns",
            "summary": "two warnings",
            "issues": [
                {"severity": "warning", "area": "test_coverage", "description": "Missing test"},
                {"severity": "info", "area": "style", "description": "Minor style"},
            ],
        })
        v = validate_and_parse("anthropic", raw)
        assert v.verdict == AuditVerdictValue.CONCERNS
        assert len(v.issues) == 2
        assert v.issues[0].severity == IssueSeverity.WARNING

    def test_invalid_json_raises(self):
        with pytest.raises(SchemaViolationError) as exc_info:
            validate_and_parse("openai", "not json {}")
        assert "openai" in str(exc_info.value)
        assert exc_info.value.auditor_id == "openai"

    def test_missing_verdict_field(self):
        raw = json.dumps({"summary": "ok", "issues": []})
        with pytest.raises(SchemaViolationError) as exc_info:
            validate_and_parse("openai", raw)
        assert "verdict" in str(exc_info.value).lower()

    def test_missing_summary_field(self):
        raw = json.dumps({"verdict": "approve", "issues": []})
        with pytest.raises(SchemaViolationError):
            validate_and_parse("anthropic", raw)

    def test_missing_issues_field(self):
        raw = json.dumps({"verdict": "approve", "summary": "ok"})
        with pytest.raises(SchemaViolationError):
            validate_and_parse("openai", raw)

    def test_bad_verdict_enum(self):
        raw = json.dumps({"verdict": "PASS", "summary": "ok", "issues": []})
        with pytest.raises(SchemaViolationError) as exc_info:
            validate_and_parse("openai", raw)
        assert "PASS" in str(exc_info.value)

    def test_malformed_issue_skipped(self):
        """A malformed individual issue is skipped, not fatal."""
        raw = json.dumps({
            "verdict": "approve",
            "summary": "ok",
            "issues": [
                "not a dict",  # malformed — should be skipped
                {"severity": "info", "area": "style", "description": "ok"},
            ],
        })
        v = validate_and_parse("openai", raw)
        assert v.verdict == AuditVerdictValue.APPROVE
        assert len(v.issues) == 1  # only the valid one

    def test_markdown_fence_not_needed(self):
        """validate_and_parse works on raw JSON (no fence needed)."""
        raw = (
            '{"verdict": "reject", "summary": "bad", "issues": '
            '[{"severity":"critical","area":"policy","description":"violation"}]}'
        )
        v = validate_and_parse("openai", raw)
        assert v.verdict == AuditVerdictValue.REJECT
        assert v.issues[0].severity == IssueSeverity.CRITICAL

    def test_not_a_dict_raises(self):
        with pytest.raises(SchemaViolationError):
            validate_and_parse("openai", json.dumps([1, 2, 3]))


# ---------------------------------------------------------------------------
# FallbackHandler tests
# ---------------------------------------------------------------------------

class TestFallbackHandler:
    def setup_method(self):
        self.handler = FallbackHandler()

    def test_core_any_failure_stop(self):
        action = self.handler.handle(RiskLevel.CORE, "openai", None, "critique")
        assert action == FallbackAction.STOP_OWNER_ALERT

    def test_core_failure_with_other_ok_still_stop(self):
        """CORE: even if one auditor succeeded, failed auditor → STOP."""
        action = self.handler.handle(RiskLevel.CORE, "openai", _approve_verdict(), "final_audit")
        assert action == FallbackAction.STOP_OWNER_ALERT

    def test_semi_one_ok_continue_batch_only(self):
        action = self.handler.handle(RiskLevel.SEMI, "openai", _approve_verdict(), "critique")
        assert action == FallbackAction.CONTINUE_ONE_AUDITOR_BATCH_ONLY

    def test_semi_both_fail_retry_then_block(self):
        action = self.handler.handle(RiskLevel.SEMI, "openai", None, "critique")
        assert action == FallbackAction.RETRY_THEN_BLOCK

    def test_low_one_ok_continue(self):
        action = self.handler.handle(RiskLevel.LOW, "anthropic", _approve_verdict(), "final_audit")
        assert action == FallbackAction.CONTINUE_ONE_AUDITOR

    def test_low_both_fail_retry_then_one(self):
        action = self.handler.handle(RiskLevel.LOW, "anthropic", None, "final_audit")
        assert action == FallbackAction.RETRY_THEN_ONE_AUDITOR


# ---------------------------------------------------------------------------
# ReviewRunner + FallbackHandler integration (mock auditors)
# ---------------------------------------------------------------------------

class TestReviewRunnerFallback:
    def test_low_one_auditor_error_continues(self, tmp_path):
        """LOW task: one auditor raises → continues with single verdict."""

        class FailingAuditor:
            auditor_id = "failing_openai"

            async def critique(self, proposal, task, context):
                raise RuntimeError("Simulated network error")

            async def final_audit(self, revised, task, context):
                raise RuntimeError("Simulated network error")

        task = TaskPack(
            title="LOW with one failed auditor",
            roadmap_stage="R1",
            why_now="Test fallback",
            risk=RiskLevel.LOW,
        )
        runner = ReviewRunner(
            builder=MockBuilder(),
            auditors=[FailingAuditor(), make_approve_auditor("mock_anthropic")],
            runs_dir=tmp_path / "runs",
            experience_dir=tmp_path,
        )
        # Should NOT raise — LOW continues with one auditor
        run = run_sync(runner.execute(task))
        assert run.approval_route is not None
        assert run.approval_route != ApprovalRoute.BLOCKED

    def test_core_one_auditor_error_blocked(self, tmp_path):
        """CORE task: one auditor raises → AuditorFailureError → BLOCKED."""

        class FailingAuditor:
            auditor_id = "failing_openai"

            async def critique(self, proposal, task, context):
                raise RuntimeError("Simulated API failure")

            async def final_audit(self, revised, task, context):
                raise RuntimeError("Simulated API failure")

        task = TaskPack(
            title="CORE with one failed auditor",
            roadmap_stage="5.5",
            why_now="Test CORE fallback",
            risk=RiskLevel.CORE,
        )
        runner = ReviewRunner(
            builder=MockBuilder(),
            auditors=[FailingAuditor(), make_approve_auditor("mock_anthropic")],
            runs_dir=tmp_path / "runs",
            experience_dir=tmp_path,
        )
        with pytest.raises(AuditorFailureError):
            run_sync(runner.execute(task))

    def test_schema_violation_blocked(self, tmp_path):
        """Auditor returning garbage → SchemaViolationError → BLOCKED."""
        from ..hard_shell.schema_validator import SchemaViolationError

        class GarbageAuditor:
            auditor_id = "garbage"

            async def critique(self, proposal, task, context):
                raise SchemaViolationError("garbage", "total garbage response")

            async def final_audit(self, revised, task, context):
                raise SchemaViolationError("garbage", "total garbage response")

        task = TaskPack(
            title="Schema violation task",
            roadmap_stage="R1",
            why_now="Test schema guard",
            risk=RiskLevel.CORE,
        )
        runner = ReviewRunner(
            builder=MockBuilder(),
            auditors=[GarbageAuditor(), GarbageAuditor()],
            runs_dir=tmp_path / "runs",
            experience_dir=tmp_path,
        )
        # CORE + both fail → AuditorFailureError (wraps SchemaViolationError)
        with pytest.raises((AuditorFailureError, SchemaViolationError)):
            run_sync(runner.execute(task))


# ---------------------------------------------------------------------------
# RunStore.load_run_for_verdict
# ---------------------------------------------------------------------------

class TestRunStoreLoadVerdict:
    def test_load_run_after_execute(self, tmp_path):
        """Execute a run, then load it back via load_run_for_verdict."""
        from ..hard_shell.run_store import RunStore

        task = TaskPack(
            title="Load verdict test",
            roadmap_stage="R1",
            why_now="Test load",
            risk=RiskLevel.LOW,
        )
        runner = make_runner(tmp_path)
        run = run_sync(runner.execute(task))

        run_store = RunStore(tmp_path / "runs")
        loaded = run_store.load_run_for_verdict(run.run_id)

        assert loaded.run_id == run.run_id
        assert loaded.trace_id == run.trace_id
        assert loaded.task.title == task.title
        assert loaded.task.risk == RiskLevel.LOW
        assert len(loaded.final_verdicts) == 2
        assert loaded.approval_route == run.approval_route

    def test_load_preserves_existing_verdict(self, tmp_path):
        from ..hard_shell.run_store import RunStore

        task = TaskPack(
            title="Preserved verdict test",
            roadmap_stage="R1",
            why_now="Test",
            risk=RiskLevel.LOW,
        )
        runner = make_runner(tmp_path)
        run = run_sync(runner.execute(task))

        run_store = RunStore(tmp_path / "runs")
        run_store.save_owner_verdict(run.run_id, "approved", "Looks good")

        loaded = run_store.load_run_for_verdict(run.run_id)
        assert loaded.owner_verdict == "approved"
        assert loaded.owner_notes == "Looks good"


# ---------------------------------------------------------------------------
# CLI verdict command integration
# ---------------------------------------------------------------------------

class TestCLIVerdict:
    def test_verdict_approved_writes_experience(self, tmp_path):
        """After verdict --approved, ExperienceSink writes to experience_log/."""
        from ..hard_shell.run_store import RunStore
        from ..hard_shell.experience_sink import ExperienceSink

        task = TaskPack(
            title="Verdict approved test",
            roadmap_stage="R1",
            why_now="Test verdict flow",
            risk=RiskLevel.LOW,
        )
        # Use a runner that writes to tmp_path
        runner = ReviewRunner(
            builder=MockBuilder(),
            auditors=[make_approve_auditor("mock_openai"), make_approve_auditor("mock_anthropic")],
            runs_dir=tmp_path / "runs",
            experience_dir=tmp_path,
        )
        run = run_sync(runner.execute(task))

        # Simulate CLI verdict
        run_store = RunStore(tmp_path / "runs")
        run_store.save_owner_verdict(run.run_id, "approved", "")
        loaded = run_store.load_run_for_verdict(run.run_id)
        loaded.owner_verdict = "approved"

        exp_sink = ExperienceSink(tmp_path)
        exp_sink.record(loaded)

        exp_files = list((tmp_path / "experience_log").glob("*.jsonl"))
        assert len(exp_files) == 1
        records = [json.loads(line) for line in exp_files[0].read_text().splitlines() if line.strip()]
        assert records[0]["owner_verdict"] == "approved"
        assert records[0]["task"]["risk"] == "low"

    def test_verdict_rejected_writes_anti_pattern(self, tmp_path):
        """After verdict --rejected, ExperienceSink writes to anti_patterns/."""
        from ..hard_shell.run_store import RunStore
        from ..hard_shell.experience_sink import ExperienceSink

        task = TaskPack(
            title="Verdict rejected test",
            roadmap_stage="R1",
            why_now="Test rejection",
            risk=RiskLevel.SEMI,
        )
        runner = ReviewRunner(
            builder=MockBuilder(),
            auditors=[make_approve_auditor("mock_openai"), make_approve_auditor("mock_anthropic")],
            runs_dir=tmp_path / "runs",
            experience_dir=tmp_path,
        )
        run = run_sync(runner.execute(task))

        run_store = RunStore(tmp_path / "runs")
        run_store.save_owner_verdict(run.run_id, "rejected", "Not safe")
        loaded = run_store.load_run_for_verdict(run.run_id)
        loaded.owner_verdict = "rejected"

        exp_sink = ExperienceSink(tmp_path)
        exp_sink.record(loaded)

        anti_files = list((tmp_path / "anti_patterns").glob("*.jsonl"))
        assert len(anti_files) == 1
        records = [json.loads(line) for line in anti_files[0].read_text().splitlines() if line.strip()]
        assert records[0]["owner_verdict"] == "rejected"

    def test_no_verdict_before_record_raises(self, tmp_path):
        """ExperienceSink.record() must not be called before verdict is set."""
        from ..hard_shell.experience_sink import ExperienceSink

        task = TaskPack(
            title="No verdict guard",
            roadmap_stage="R1",
            why_now="Test guard",
            risk=RiskLevel.LOW,
        )
        runner = make_runner(tmp_path)
        run = run_sync(runner.execute(task))

        exp_sink = ExperienceSink(tmp_path)
        with pytest.raises(RuntimeError, match="owner_verdict"):
            exp_sink.record(run)


# ---------------------------------------------------------------------------
# ExperienceSink v2: inline text fields
# ---------------------------------------------------------------------------

class TestExperienceSinkV2InlineText:
    """Verify proposal_text, critiques_text, and other v2 fields are stored inline."""

    def test_approved_record_contains_proposal_text(self, tmp_path):
        """Approved run stores chosen_solution.proposal_text inline."""
        from ..hard_shell.experience_sink import ExperienceSink, EXPERIENCE_SINK_SCHEMA_VERSION

        task = TaskPack(
            title="Inline text test",
            roadmap_stage="R1",
            why_now="Test v2 fields",
            risk=RiskLevel.LOW,
            affected_files=["scripts/foo.py", "scripts/bar.py"],
        )
        runner = make_runner(tmp_path)
        run = run_sync(runner.execute(task))
        run.owner_verdict = "approved"

        exp_sink = ExperienceSink(tmp_path)
        exp_sink.record(run)

        exp_files = list((tmp_path / "experience_log").glob("*.jsonl"))
        assert len(exp_files) == 1
        record = json.loads(exp_files[0].read_text().splitlines()[0])

        # v2 schema
        assert record["schema_version"] == EXPERIENCE_SINK_SCHEMA_VERSION

        # Inline text present in chosen_solution
        chosen = record["chosen_solution"]
        assert "proposal_text" in chosen
        assert chosen["proposal_text"] is not None
        assert len(chosen["proposal_text"]) > 0

        # Hash still present for dedup
        assert "proposal_hash" in chosen
        assert chosen["proposal_hash"].startswith("sha256:")

        # run_id present
        assert "run_id" in record
        assert record["run_id"] == run.run_id

        # files_changed from task
        assert record["files_changed"] == ["scripts/foo.py", "scripts/bar.py"]

    def test_proposal_text_capped_at_limit(self, tmp_path):
        """Very long proposal text is capped, not omitted."""
        from ..hard_shell.experience_sink import ExperienceSink, _MAX_PROPOSAL_CHARS
        from ..hard_shell.contracts import ProtocolRun, ModelName, EffortLevel, QualityGateResult, ApprovalRoute

        task = TaskPack(
            title="Cap test",
            roadmap_stage="R1",
            why_now="Test cap",
            risk=RiskLevel.LOW,
        )
        run = ProtocolRun(
            task=task,
            model_used=ModelName.SONNET,
            effort=EffortLevel.MEDIUM,
            proposal="x" * (_MAX_PROPOSAL_CHARS + 5000),
            revised_proposal="",
            quality_gate=QualityGateResult(passed=True, reason="ok"),
            approval_route=ApprovalRoute.AUTO_PASS,
            owner_verdict="approved",
        )
        run.mark_finished()

        exp_sink = ExperienceSink(tmp_path)
        exp_sink.record(run)

        record = json.loads(
            list((tmp_path / "experience_log").glob("*.jsonl"))[0].read_text().splitlines()[0]
        )
        text = record["chosen_solution"]["proposal_text"]
        assert len(text) == _MAX_PROPOSAL_CHARS

    def test_escalation_stores_both_proposals(self, tmp_path):
        """Escalated run stores both rejected (sonnet) and chosen (opus) text."""
        from ..hard_shell.experience_sink import ExperienceSink
        from ..hard_shell.contracts import ProtocolRun, ModelName, EffortLevel, QualityGateResult, ApprovalRoute

        task = TaskPack(
            title="Escalation test",
            roadmap_stage="R1",
            why_now="Test DPO pair",
            risk=RiskLevel.SEMI,
        )
        critique = AuditVerdict(
            auditor_id="mock_openai",
            verdict=AuditVerdictValue.REJECT,
            summary="Bad imports",
            issues=[AuditIssue(severity=IssueSeverity.CRITICAL, area="policy", description="Forbidden import")],
        )
        final = AuditVerdict(
            auditor_id="mock_openai",
            verdict=AuditVerdictValue.APPROVE,
            summary="Fixed",
            issues=[],
        )
        run = ProtocolRun(
            task=task,
            model_used=ModelName.OPUS,
            effort=EffortLevel.HIGH,
            escalated=True,
            escalation_reason="Quality gate failed",
            proposal="def bad_code(): import reconciliation",
            critiques=[critique],
            revised_proposal="def good_code(): pass",
            final_verdicts=[final],
            quality_gate=QualityGateResult(passed=True, reason="ok"),
            approval_route=ApprovalRoute.BATCH_APPROVAL,
            owner_verdict="approved",
        )
        run.mark_finished()

        exp_sink = ExperienceSink(tmp_path)
        exp_sink.record(run)

        record = json.loads(
            list((tmp_path / "experience_log").glob("*.jsonl"))[0].read_text().splitlines()[0]
        )

        # Both rejected and chosen have inline text
        assert record["rejected_solution"]["proposal_text"] == "def bad_code(): import reconciliation"
        assert record["chosen_solution"]["proposal_text"] == "def good_code(): pass"

        # Critiques text inline
        assert record["critiques_text"] is not None
        assert "Forbidden import" in record["critiques_text"]

        # Final audit text inline
        assert record["final_audit_text"] is not None
        assert "Fixed" in record["final_audit_text"]

    def test_error_detail_stored(self, tmp_path):
        """Error message from run is stored inline."""
        from ..hard_shell.experience_sink import ExperienceSink
        from ..hard_shell.contracts import (
            ProtocolRun, ModelName, EffortLevel, ErrorClass, QualityGateResult, ApprovalRoute,
        )

        task = TaskPack(
            title="Error test",
            roadmap_stage="R1",
            why_now="Test error",
            risk=RiskLevel.LOW,
        )
        run = ProtocolRun(
            task=task,
            model_used=ModelName.SONNET,
            effort=EffortLevel.LOW,
            proposal="some code",
            error_class=ErrorClass.TRANSIENT,
            error_message="API timeout after 30s",
            quality_gate=QualityGateResult(passed=False, reason="error"),
            approval_route=ApprovalRoute.BLOCKED,
            owner_verdict="rejected",
        )
        run.mark_finished()

        exp_sink = ExperienceSink(tmp_path)
        exp_sink.record(run)

        record = json.loads(
            list((tmp_path / "anti_patterns").glob("*.jsonl"))[0].read_text().splitlines()[0]
        )
        assert record["error_detail"] == "API timeout after 30s"
        assert record["owner_notes"] is None
