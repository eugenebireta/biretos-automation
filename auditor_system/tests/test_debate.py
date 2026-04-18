"""
tests/test_debate.py — Deterministic tests for debate layer (no live API calls).

Covers:
  - debate.should_debate: fast path vs debate trigger
  - debate.needs_arbiter: arbiter trigger conditions
  - debate.build_debate_context: peer verdict inclusion
  - debate.build_arbiter_pack: compact critic pack
  - ReviewRunner fast path: all approve → skip debate
  - ReviewRunner debate: disagreement → Round 2 debate
  - ReviewRunner arbiter: persistent disagreement → Round 3
  - ReviewRunner no arbiter: skips Round 3 when arbiter=None
"""
from __future__ import annotations

import asyncio


from ..debate import (
    build_arbiter_pack,
    build_debate_context,
    needs_arbiter,
    should_debate,
)
from ..hard_shell.contracts import (
    AuditIssue,
    AuditVerdict,
    AuditVerdictValue,
    IssueSeverity,
    QualityGateResult,
    RiskLevel,
    TaskPack,
)
from ..providers.mock_auditor import (
    MockAuditor,
    make_approve_auditor,
    make_concerns_auditor,
    make_reject_auditor,
)
from ..providers.mock_builder import MockBuilder
from ..review_runner import ReviewRunner


def run_sync(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _approve(auditor_id: str = "mock_a") -> AuditVerdict:
    return AuditVerdict(
        auditor_id=auditor_id,
        verdict=AuditVerdictValue.APPROVE,
        summary="Looks good",
        issues=[],
    )


def _reject(auditor_id: str = "mock_b") -> AuditVerdict:
    return AuditVerdict(
        auditor_id=auditor_id,
        verdict=AuditVerdictValue.REJECT,
        summary="Policy violation found",
        issues=[
            AuditIssue(
                severity=IssueSeverity.CRITICAL,
                area="policy",
                description="Forbidden import detected",
            )
        ],
    )


def _concerns(auditor_id: str = "mock_c", warnings: int = 2) -> AuditVerdict:
    return AuditVerdict(
        auditor_id=auditor_id,
        verdict=AuditVerdictValue.CONCERNS,
        summary=f"{warnings} warnings",
        issues=[
            AuditIssue(
                severity=IssueSeverity.WARNING,
                area="test_coverage",
                description=f"Warning {i+1}",
            )
            for i in range(warnings)
        ],
    )


def _task(risk: RiskLevel = RiskLevel.LOW) -> TaskPack:
    return TaskPack(
        title="Test task",
        roadmap_stage="R1",
        why_now="Test debate",
        risk=risk,
    )


# ---------------------------------------------------------------------------
# should_debate tests
# ---------------------------------------------------------------------------

class TestShouldDebate:
    def test_all_approve_no_debate(self):
        assert should_debate([_approve("a"), _approve("b")], RiskLevel.LOW) is False

    def test_single_approve_no_debate(self):
        assert should_debate([_approve("a")], RiskLevel.SEMI) is False

    def test_one_reject_triggers_debate(self):
        assert should_debate([_approve("a"), _reject("b")], RiskLevel.LOW) is True

    def test_both_reject_triggers_debate(self):
        assert should_debate([_reject("a"), _reject("b")], RiskLevel.CORE) is True

    def test_concerns_triggers_debate(self):
        assert should_debate([_approve("a"), _concerns("b")], RiskLevel.LOW) is True

    def test_approve_with_critical_triggers_debate(self):
        v = AuditVerdict(
            auditor_id="a",
            verdict=AuditVerdictValue.APPROVE,
            summary="approve but critical",
            issues=[AuditIssue(severity=IssueSeverity.CRITICAL, area="policy", description="critical")],
        )
        assert should_debate([v, _approve("b")], RiskLevel.LOW) is True

    def test_empty_verdicts_triggers_debate(self):
        assert should_debate([], RiskLevel.LOW) is True


# ---------------------------------------------------------------------------
# needs_arbiter tests
# ---------------------------------------------------------------------------

class TestNeedsArbiter:
    def test_gate_passed_no_arbiter(self):
        gate = QualityGateResult(passed=True, reason="ok")
        assert needs_arbiter([_approve("a"), _approve("b")], gate) is False

    def test_conflict_needs_arbiter(self):
        gate = QualityGateResult(passed=False, reason="conflict")
        assert needs_arbiter([_approve("a"), _reject("b")], gate) is True

    def test_both_reject_gate_fail_needs_arbiter(self):
        gate = QualityGateResult(passed=False, reason="reject")
        assert needs_arbiter([_reject("a"), _reject("b")], gate) is True

    def test_single_auditor_no_arbiter(self):
        gate = QualityGateResult(passed=False, reason="reject")
        assert needs_arbiter([_reject("a")], gate) is False


# ---------------------------------------------------------------------------
# build_debate_context tests
# ---------------------------------------------------------------------------

class TestBuildDebateContext:
    def test_includes_peer_verdict(self):
        base = {"risk": "low", "effective_surface": []}
        peer = _reject("gemini")
        ctx = build_debate_context(base, peer)

        assert ctx["debate_round"] == 2
        assert ctx["peer_verdict"]["auditor_id"] == "gemini"
        assert ctx["peer_verdict"]["verdict"] == "reject"
        assert ctx["peer_verdict"]["critical_count"] == 1
        assert len(ctx["peer_verdict"]["issues"]) == 1

    def test_preserves_base_context(self):
        base = {"risk": "semi", "effective_surface": ["tier1_files"], "extra": 42}
        ctx = build_debate_context(base, _approve("peer"))
        assert ctx["risk"] == "semi"
        assert ctx["extra"] == 42
        assert ctx["effective_surface"] == ["tier1_files"]


# ---------------------------------------------------------------------------
# build_arbiter_pack tests
# ---------------------------------------------------------------------------

class TestBuildArbiterPack:
    def test_contains_all_fields(self):
        pack = build_arbiter_pack(
            proposal="original code",
            revised_proposal="revised code",
            round1_verdicts=[_approve("a"), _reject("b")],
            round2_verdicts=[_approve("a"), _concerns("b")],
        )
        assert "original_proposal_excerpt" in pack
        assert "revised_proposal_excerpt" in pack
        assert len(pack["round1_verdicts"]) == 2
        assert len(pack["round2_verdicts"]) == 2
        assert "dispute_summary" in pack

    def test_truncates_long_proposal(self):
        long = "x" * 10000
        pack = build_arbiter_pack(long, long, [], [])
        assert len(pack["original_proposal_excerpt"]) == 4000
        assert len(pack["revised_proposal_excerpt"]) == 4000


# ---------------------------------------------------------------------------
# ReviewRunner integration tests
# ---------------------------------------------------------------------------

class TestReviewRunnerFastPath:
    def test_all_approve_skips_debate(self, tmp_path):
        """Both auditors approve in R1 → fast path, no debate."""
        task = _task(RiskLevel.LOW)
        runner = ReviewRunner(
            builder=MockBuilder(),
            auditors=[make_approve_auditor("mock_a"), make_approve_auditor("mock_b")],
            runs_dir=tmp_path / "runs",
            experience_dir=tmp_path,
        )
        run = run_sync(runner.execute(task))

        assert run.debate_triggered is False
        assert run.arbiter_used is False
        assert len(run.debate_verdicts) == 0
        assert run.arbiter_verdict is None
        assert run.quality_gate.passed is True
        assert run.approval_route is not None

    def test_semi_all_approve_also_fast_path(self, tmp_path):
        """SEMI risk: all approve → still uses fast path."""
        task = _task(RiskLevel.SEMI)
        runner = ReviewRunner(
            builder=MockBuilder(),
            auditors=[make_approve_auditor("mock_a"), make_approve_auditor("mock_b")],
            runs_dir=tmp_path / "runs",
            experience_dir=tmp_path,
        )
        run = run_sync(runner.execute(task))

        assert run.debate_triggered is False
        assert run.quality_gate.passed is True


class TestReviewRunnerDebate:
    def test_disagreement_triggers_debate(self, tmp_path):
        """One approve + one reject → debate triggered, no arbiter (no arbiter configured)."""
        task = _task(RiskLevel.SEMI)

        class ApproveR1RejectR1(MockAuditor):
            """Approves in R1, still approves in debate."""
            pass

        runner = ReviewRunner(
            builder=MockBuilder(),
            auditors=[
                make_approve_auditor("mock_a"),
                make_reject_auditor("mock_b", critical=True),
            ],
            runs_dir=tmp_path / "runs",
            experience_dir=tmp_path,
            arbiter=None,  # no arbiter
        )
        run = run_sync(runner.execute(task))

        assert run.debate_triggered is True
        assert len(run.debate_verdicts) == 2
        assert run.arbiter_used is False  # no arbiter configured

    def test_concerns_triggers_debate(self, tmp_path):
        """One approve + one concerns → debate triggered."""
        task = _task(RiskLevel.LOW)
        runner = ReviewRunner(
            builder=MockBuilder(),
            auditors=[
                make_approve_auditor("mock_a"),
                make_concerns_auditor("mock_b", warning_count=2),
            ],
            runs_dir=tmp_path / "runs",
            experience_dir=tmp_path,
        )
        run = run_sync(runner.execute(task))

        assert run.debate_triggered is True


class TestReviewRunnerArbiter:
    def test_arbiter_called_on_persistent_disagreement(self, tmp_path):
        """Approve vs reject persists → arbiter called → verdict becomes final."""
        task = _task(RiskLevel.SEMI)

        class MockArbiter:
            """Mock arbiter that always approves."""
            auditor_id = "mock_arbiter"

            async def arbitrate(self, task, context, arbiter_pack):
                return AuditVerdict(
                    auditor_id="mock_arbiter",
                    verdict=AuditVerdictValue.APPROVE,
                    summary="Arbiter: approve after reviewing both sides",
                    issues=[],
                )

        runner = ReviewRunner(
            builder=MockBuilder(),
            auditors=[
                make_approve_auditor("mock_a"),
                make_reject_auditor("mock_b", critical=True),
            ],
            runs_dir=tmp_path / "runs",
            experience_dir=tmp_path,
            arbiter=MockArbiter(),
        )
        run = run_sync(runner.execute(task))

        assert run.debate_triggered is True
        assert run.arbiter_used is True
        assert run.arbiter_verdict is not None
        assert run.arbiter_verdict.auditor_id == "mock_arbiter"
        assert run.arbiter_verdict.verdict == AuditVerdictValue.APPROVE
        # Final verdicts should be the arbiter's verdict
        assert len(run.final_verdicts) == 1
        assert run.final_verdicts[0].auditor_id == "mock_arbiter"

    def test_no_arbiter_skips_round3(self, tmp_path):
        """Persistent disagreement but no arbiter → Round 3 skipped."""
        task = _task(RiskLevel.SEMI)
        runner = ReviewRunner(
            builder=MockBuilder(),
            auditors=[
                make_approve_auditor("mock_a"),
                make_reject_auditor("mock_b", critical=True),
            ],
            runs_dir=tmp_path / "runs",
            experience_dir=tmp_path,
            arbiter=None,
        )
        run = run_sync(runner.execute(task))

        assert run.debate_triggered is True
        assert run.arbiter_used is False
        assert run.arbiter_verdict is None


class TestReviewRunnerDebateContext:
    def test_debate_verdicts_stored_separately(self, tmp_path):
        """Debate verdicts are stored in debate_verdicts field."""
        task = _task(RiskLevel.LOW)
        runner = ReviewRunner(
            builder=MockBuilder(),
            auditors=[
                make_approve_auditor("mock_a"),
                make_concerns_auditor("mock_b", warning_count=1),
            ],
            runs_dir=tmp_path / "runs",
            experience_dir=tmp_path,
        )
        run = run_sync(runner.execute(task))

        assert run.debate_triggered is True
        assert len(run.debate_verdicts) > 0
        # debate_verdicts should match final_verdicts (no arbiter)
        assert run.debate_verdicts == run.final_verdicts
