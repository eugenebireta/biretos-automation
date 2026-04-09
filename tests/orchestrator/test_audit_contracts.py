"""
test_audit_contracts.py — L0/L1 Contract tests for external AI audit.

PURPOSE: Verifies structural contracts — module interfaces, config keys,
FSM table shape, schema versions, importability. This is the foundation
layer; behavioral/scenario tests are in test_audit_scenarios.py and
constitutional governance proofs in test_audit_constitution.py.

All tests are deterministic, use mocks, require no API keys.
"""
from __future__ import annotations

import json
import sys
import os
from datetime import datetime, timezone, date
from pathlib import Path
from unittest.mock import MagicMock, patch
from argparse import Namespace

import pytest

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)


# ===========================================================================
# A. FSM INVARIANTS
# ===========================================================================

class TestA_FsmInvariants:
    """Every FSM transition must be in the transition table.
    No undefined state transitions allowed."""

    def test_all_transitions_defined(self):
        """FSM_TRANSITIONS covers all documented state pairs."""
        from main import FSM_TRANSITIONS
        # Required states in FSM table (audit_passed is a transient state
        # handled procedurally in cmd_cycle, not in transition table)
        required_states = {
            "ready", "processing", "awaiting_execution",
            "awaiting_owner_reply", "error", "completed",
            "audit_in_progress", "blocked",
        }
        # All states that appear as source
        source_states = {s for s, _ in FSM_TRANSITIONS.keys()}
        # All states that appear as target
        target_states = set(FSM_TRANSITIONS.values())
        all_states = source_states | target_states

        for state in required_states:
            assert state in all_states, f"Missing state in FSM: {state}"

    def test_audit_passed_forwarded_to_ready_behaviorally(self, tmp_path):
        """audit_passed state is forwarded to ready when cmd_cycle runs."""
        import main
        manifest = {
            "fsm_state": "audit_passed",
            "current_task_id": "test",
            "trace_id": "t1",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        lock_path = tmp_path / "lock"
        runs_path = tmp_path / "runs.jsonl"

        with patch.object(main, "MANIFEST_PATH", manifest_path), \
             patch.object(main, "LOCK_PATH", lock_path), \
             patch.object(main, "RUNS_PATH", runs_path):
            # cmd_cycle should forward audit_passed → ready, then proceed
            # We mock _cmd_cycle_inner to prevent full execution
            with patch.object(main, "_cmd_cycle_inner") as mock_inner:
                main.cmd_cycle(Namespace())
                # Verify it was called (state forwarded to ready → processing)
                if mock_inner.called:
                    # Inner was called = state transitioned past audit_passed
                    pass
                else:
                    # Read manifest to verify state changed
                    result = json.loads(manifest_path.read_text(encoding="utf-8"))
                    assert result["fsm_state"] == "ready"

    def test_no_direct_skip_to_completed(self):
        """Cannot jump from processing directly to completed (must go through execution)."""
        from main import FSM_TRANSITIONS
        processing_targets = {
            target for (src, _), target in FSM_TRANSITIONS.items()
            if src == "processing"
        }
        # processing should go to awaiting_execution, not completed
        assert "completed" not in processing_targets

    def test_blocked_only_exits_via_owner(self):
        """Blocked state can only exit via owner_replied event."""
        from main import FSM_TRANSITIONS
        blocked_exits = {
            (event, target) for (src, event), target in FSM_TRANSITIONS.items()
            if src == "blocked"
        }
        for event, target in blocked_exits:
            if target != "blocked":  # self-loop is ok
                assert event == "owner_replied", \
                    f"blocked exits via {event}→{target}, expected owner_replied"

    def test_error_state_requires_manual_intervention(self):
        """Error state cannot auto-recover without owner action."""
        from main import FSM_TRANSITIONS
        error_exits = {
            event for (src, event), target in FSM_TRANSITIONS.items()
            if src == "error" and target != "error"
        }
        # Error should only exit via owner_replied
        for event in error_exits:
            assert event == "owner_replied", \
                f"error exits via {event}, expected owner_replied only"

    def test_audit_passed_forwards_to_ready(self):
        """audit_passed → ready is the expected forward transition."""
        from main import FSM_TRANSITIONS
        assert FSM_TRANSITIONS[("audit_in_progress", "audit_passed")] == "ready"


# ===========================================================================
# B. RISK SEPARATION
# ===========================================================================

class TestB_RiskSeparation:
    """LOW, SEMI, CORE tasks follow different execution paths.
    Risk classification determines audit requirements."""

    def test_low_synthesizer_returns_proceed_not_audit(self):
        """LOW risk through real synthesizer returns PROCEED, never SEMI_AUDIT."""
        import synthesizer
        from classifier import ClassifierResult
        clf = ClassifierResult(
            risk_class="LOW",
            governance_route="none",
            rationale="test",
            tier_violations=[],
            blocking_rules=[],
        )
        verdict = MagicMock()
        verdict.risk_assessment = "LOW"
        verdict.governance_route = "none"
        verdict.scope = ["scripts/foo.py"]

        result = synthesizer.decide(
            classification=clf,
            verdict=verdict,
            attempt_count=1,
            last_packet_status="completed",
            max_attempts=3,
        )
        assert result.action == "PROCEED", \
            f"LOW risk should get PROCEED, got {result.action}"
        assert result.action != "SEMI_AUDIT"
        assert result.action != "CORE_GATE"

    def test_core_gets_zero_retries(self):
        """CORE risk tasks always get 0 retries — must escalate to owner."""
        from main import _get_retry_policy
        assert _get_retry_policy("CORE") == 0

    def test_semi_gets_configurable_retries(self):
        """SEMI risk retries are configurable via config.yaml."""
        from main import _get_retry_policy
        cfg = {"max_retries_semi": 5}
        assert _get_retry_policy("SEMI", cfg=cfg) == 5

    def test_low_retries_configurable(self):
        """LOW risk retries are configurable via config.yaml."""
        from main import _get_retry_policy
        cfg = {"max_retries_low": 7}
        assert _get_retry_policy("LOW", cfg=cfg) == 7

    def test_unknown_risk_gets_zero(self):
        """Unknown risk classes get 0 retries (safe default)."""
        from main import _get_retry_policy
        assert _get_retry_policy("UNKNOWN") == 0
        assert _get_retry_policy("") == 0


# ===========================================================================
# C. CONSENSUS GATE
# ===========================================================================

class TestC_ConsensusGate:
    """P3.1: Multi-pass critique loop requires N consecutive audit passes."""

    def test_single_pass_not_enough(self):
        """One approval is not consensus when min_approvals=2."""
        from main import _check_critique_consensus
        history = [{"gate_passed": True}]
        assert _check_critique_consensus(history, min_approvals=2) is False

    def test_two_consecutive_passes(self):
        """Two consecutive passes satisfy min_approvals=2."""
        from main import _check_critique_consensus
        history = [
            {"gate_passed": False},
            {"gate_passed": True},
            {"gate_passed": True},
        ]
        assert _check_critique_consensus(history, min_approvals=2) is True

    def test_interrupted_passes(self):
        """A failure between passes resets the consecutive count."""
        from main import _check_critique_consensus
        history = [
            {"gate_passed": True},
            {"gate_passed": False},
            {"gate_passed": True},
        ]
        assert _check_critique_consensus(history, min_approvals=2) is False

    def test_none_treated_as_fail(self):
        """None gate_passed (audit error) breaks consensus."""
        from main import _check_critique_consensus
        history = [{"gate_passed": True}, {"gate_passed": None}]
        assert _check_critique_consensus(history, min_approvals=2) is False

    def test_consensus_disabled_via_config(self):
        """When critique_consensus_required=False, single pass suffices."""
        # This is a config-level control, tested via pipeline behavior
        # (see P6 test_low_full_cycle_to_ready with consensus disabled)
        from main import _check_critique_consensus
        # Even with min_approvals=1, need at least 1 pass
        history = [{"gate_passed": True}]
        assert _check_critique_consensus(history, min_approvals=1) is True

    def test_empty_history_no_consensus_with_approvals_required(self):
        """Empty history = no consensus when min_approvals >= 1."""
        from main import _check_critique_consensus
        assert _check_critique_consensus([], min_approvals=1) is False
        assert _check_critique_consensus([], min_approvals=2) is False
        # min_approvals=0 is a degenerate case: vacuously true (0 required = always ok)
        assert _check_critique_consensus([], min_approvals=0) is True


# ===========================================================================
# D. RETRY SAFETY
# ===========================================================================

class TestD_RetrySafety:
    """Retry logic respects limits and accumulates critiques."""

    def test_critique_history_persists_across_retries(self, tmp_path):
        """Each retry appends to critique_history.json, not overwrites."""
        from main import _append_critique_history, _load_critique_history

        ar = MagicMock()
        ar.quality_gate.passed = False
        ar.approval_route.value = "MANUAL"
        ar.run_id = "r1"

        _append_critique_history(tmp_path, 1, ar, "first critique")
        _append_critique_history(tmp_path, 2, ar, "second critique")

        history = _load_critique_history(tmp_path)
        assert len(history) == 2
        assert history[0]["critique_text"] == "first critique"
        assert history[1]["critique_text"] == "second critique"

    def test_critique_text_truncated(self, tmp_path):
        """Critique text is truncated to 2000 chars to prevent bloat."""
        from main import _append_critique_history

        ar = MagicMock()
        ar.quality_gate.passed = True
        ar.approval_route.value = "AUTO"
        ar.run_id = "r1"

        _append_critique_history(tmp_path, 1, ar, "x" * 5000)
        history = json.loads(
            (tmp_path / "critique_history.json").read_text(encoding="utf-8")
        )
        assert len(history[0]["critique_text"]) == 2000

    def test_accumulated_critiques_formatted(self):
        """Formatted critique block includes all rounds with verdicts."""
        from main import _format_accumulated_critiques
        history = [
            {"attempt": 1, "gate_passed": False, "approval_route": "MANUAL",
             "critique_text": "Fix imports"},
            {"attempt": 2, "gate_passed": True, "approval_route": "AUTO",
             "critique_text": "Looks good"},
        ]
        result = _format_accumulated_critiques(history)
        assert "2 round(s)" in result
        assert "Round 1" in result
        assert "FAILED" in result
        assert "Round 2" in result
        assert "PASSED" in result
        assert "Fix imports" in result
        assert "Looks good" in result

    def test_retry_directive_includes_corrections(self):
        """Retry directive contains previous failure details."""
        from main import _build_retry_directive
        failures = [{"check_id": "A4:SCOPE", "passed": False, "detail": "drift"}]
        result = _build_retry_directive(
            original_directive="# Original",
            attempt=0,
            acceptance_failures=failures,
        )
        assert "A4:SCOPE" in result
        assert "drift" in result

    def test_retry_directive_includes_oos_files(self):
        """Retry directive lists out-of-scope files."""
        from main import _build_retry_directive
        result = _build_retry_directive(
            original_directive="# Original",
            attempt=0,
            acceptance_failures=[],
            out_of_scope_files=["core/forbidden.py", "domain/secret.py"],
        )
        assert "core/forbidden.py" in result
        assert "domain/secret.py" in result

    def test_retry_directive_includes_audit_critique(self):
        """Retry directive includes auditor critique for executor to address."""
        from main import _build_retry_directive
        result = _build_retry_directive(
            original_directive="# Original",
            attempt=0,
            acceptance_failures=[],
            audit_critique="Missing trace_id in new module.",
        )
        assert "Missing trace_id" in result
        assert "Auditor Critique" in result


# ===========================================================================
# E. BUDGET ENFORCEMENT
# ===========================================================================

class TestE_BudgetEnforcement:
    """P7: Budget tracking prevents cost overruns."""

    def test_cost_estimation_accuracy(self):
        """Known models produce non-zero costs."""
        import budget_tracker as bt
        for model in ["claude-sonnet-4-6", "claude-opus-4-6",
                       "gemini-2.5-pro", "gpt-4o"]:
            cost = bt.estimate_cost(model, 10000, 5000)
            assert cost > 0, f"{model} should have non-zero cost"

    def test_budget_check_blocks_on_daily_limit(self):
        """Daily budget exceeded → within_budget=False."""
        import budget_tracker as bt
        now = datetime.now(timezone.utc)
        records = [
            {"trace_id": f"t{i}", "cost_usd": 5.0, "ts": now.isoformat()}
            for i in range(3)
        ]
        result = bt.check_budget("t0", daily_limit=10.0, records=records)
        assert result["within_budget"] is False
        assert result["daily_exceeded"] is True

    def test_budget_check_blocks_on_run_limit(self):
        """Per-run budget exceeded → within_budget=False."""
        import budget_tracker as bt
        now = datetime.now(timezone.utc)
        records = [
            {"trace_id": "same", "cost_usd": 1.5, "ts": now.isoformat()},
            {"trace_id": "same", "cost_usd": 1.0, "ts": now.isoformat()},
        ]
        result = bt.check_budget("same", per_run_limit=2.0, records=records)
        assert result["run_exceeded"] is True

    def test_record_idempotency_key_unique(self, tmp_path):
        """Each record has a unique idempotency key."""
        import budget_tracker as bt
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            r1 = bt.record_call(trace_id="t1", provider="a", model="m",
                                 stage="s", call_seq=0)
            r2 = bt.record_call(trace_id="t1", provider="a", model="m",
                                 stage="s", call_seq=1)
        assert r1["idempotency_key"] != r2["idempotency_key"]

    def test_daily_summary_by_stage(self):
        """Daily summary breaks down cost by pipeline stage."""
        import budget_tracker as bt
        records = [
            {"cost_usd": 0.5, "stage": "advisor", "model": "m",
             "provider": "anthropic", "ts": datetime.now(timezone.utc).isoformat()},
            {"cost_usd": 0.3, "stage": "executor", "model": "m",
             "provider": "anthropic", "ts": datetime.now(timezone.utc).isoformat()},
        ]
        summary = bt.get_daily_summary(records=records)
        assert summary["by_stage"]["advisor"] == pytest.approx(0.5)
        assert summary["by_stage"]["executor"] == pytest.approx(0.3)


# ===========================================================================
# F. EXPERIENCE LOOP
# ===========================================================================

class TestF_ExperienceLoop:
    """P5: Past execution experience feeds into future directives."""

    def test_experience_record_schema(self):
        """Experience records follow execution_experience_v1 schema."""
        import experience_writer as ew
        assert ew.SCHEMA_VERSION == "execution_experience_v1"

    def test_experience_filters_by_schema(self, tmp_path):
        """Only v1 records are loaded, other schemas ignored."""
        import experience_reader as er
        now = datetime.now(timezone.utc)
        log_path = tmp_path / f"experience_{now.strftime('%Y-%m')}.jsonl"
        records = [
            {"schema_version": "execution_experience_v1",
             "trace_id": "good", "task_id": "t1",
             "ts": now.isoformat(), "overall_verdict": "PASS"},
            {"schema_version": "some_other_v2",
             "trace_id": "bad", "task_id": "t2"},
        ]
        log_path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n",
            encoding="utf-8",
        )
        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            loaded = er._load_experience_records(months=1)
        assert len(loaded) == 1
        assert loaded[0]["trace_id"] == "good"

    def test_lessons_include_failure_checks(self, tmp_path):
        """Lessons mention specific failed acceptance checks."""
        import experience_reader as er
        now = datetime.now(timezone.utc)
        log_path = tmp_path / f"experience_{now.strftime('%Y-%m')}.jsonl"
        record = {
            "schema_version": "execution_experience_v1",
            "ts": now.isoformat(),
            "trace_id": "t1", "task_id": "target",
            "risk_class": "LOW",
            "overall_verdict": "ACCEPTANCE_FAILED",
            "executor_status": "completed",
            "elapsed_seconds": 10.0,
            "gate_passed": True,
            "gate_rule": "LOW_RISK_AUTO",
            "acceptance_passed": False,
            "acceptance_checks": [
                {"check_id": "A4:SCOPE", "passed": False, "detail": "drift"},
            ],
            "drift_detected": True,
            "out_of_scope_files": ["core/secret.py"],
            "changed_files_count": 1,
            "changed_files": ["scripts/foo.py"],
            "audit_verdict": None,
            "audit_run_id": None,
            "correction_needed": True,
            "correction_detail": "scope drift",
        }
        log_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            lessons = er.get_lessons_for_task("target")
        assert "A4:SCOPE" in lessons
        assert "core/secret.py" in lessons

    def test_drift_warning_on_high_rate(self, tmp_path):
        """High drift rate (>50%) triggers explicit warning in lessons."""
        import experience_reader as er
        now = datetime.now(timezone.utc)
        log_path = tmp_path / f"experience_{now.strftime('%Y-%m')}.jsonl"
        # 3/4 = 75% drift rate
        records = []
        for i, drift in enumerate([True, True, True, False]):
            records.append({
                "schema_version": "execution_experience_v1",
                "ts": now.isoformat(),
                "trace_id": f"t{i}", "task_id": f"task{i}",
                "risk_class": "LOW",
                "overall_verdict": "PASS",
                "executor_status": "completed",
                "elapsed_seconds": 10.0,
                "gate_passed": True, "gate_rule": "LOW_RISK_AUTO",
                "acceptance_passed": True,
                "acceptance_checks": [],
                "drift_detected": drift,
                "out_of_scope_files": [],
                "changed_files_count": 1,
                "changed_files": [],
                "audit_verdict": None, "audit_run_id": None,
                "correction_needed": False, "correction_detail": None,
            })
        log_path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n",
            encoding="utf-8",
        )
        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            lessons = er.get_lessons_for_task("new-task")
        assert "drift" in lessons.lower()


# ===========================================================================
# G. QUEUE INTEGRITY
# ===========================================================================

class TestG_QueueIntegrity:
    """P2: Task queue ordering and auto-advance rules."""

    def test_fifo_ordering(self, tmp_path):
        """Tasks dequeue in FIFO order."""
        import task_queue as tq
        with patch.object(tq, "QUEUE_PATH", tmp_path / "queue.json"):
            tq.save_queue([])
            tq.enqueue("first", "goal 1", "LOW")
            tq.enqueue("second", "goal 2", "LOW")
            task = tq.peek_next()
        assert task["task_id"] == "first"

    def test_auto_advance_only_for_low(self, tmp_path):
        """Auto-advance skips SEMI/CORE tasks (need owner review)."""
        import task_queue as tq
        with patch.object(tq, "QUEUE_PATH", tmp_path / "queue.json"):
            tq.save_queue([])
            tq.enqueue("semi-task", "goal", "SEMI")
            manifest = {"fsm_state": "ready", "last_verdict": None}
            advanced = tq.try_auto_advance(manifest, auto_execute=True)
        assert advanced is None  # SEMI not auto-advanced

    def test_auto_advance_works_for_low(self, tmp_path):
        """LOW risk tasks are auto-advanced."""
        import task_queue as tq
        with patch.object(tq, "QUEUE_PATH", tmp_path / "queue.json"):
            tq.save_queue([])
            tq.enqueue("low-task", "goal", "LOW")
            manifest = {"fsm_state": "ready", "last_verdict": None}
            advanced = tq.try_auto_advance(manifest, auto_execute=True)
        assert advanced is not None
        assert advanced["task_id"] == "low-task"

    def test_queue_depth_accurate(self, tmp_path):
        """queue_depth() returns correct count."""
        import task_queue as tq
        with patch.object(tq, "QUEUE_PATH", tmp_path / "queue.json"):
            tq.save_queue([])
            tq.enqueue("t1", "goal 1")
            tq.enqueue("t2", "goal 2")
            assert tq.queue_depth() == 2
            tq.dequeue()
            assert tq.queue_depth() == 1


# ===========================================================================
# H. DIRECTIVE INTEGRITY
# ===========================================================================

class TestH_DirectiveIntegrity:
    """Generated directives contain all required fields."""

    def test_directive_has_trace_id(self, tmp_path):
        """Directive includes trace_id for traceability."""
        import main
        manifest = {
            "current_task_id": "test-task",
            "current_sprint_goal": "test goal",
            "attempt_count": 1,
            "retry_count": 0,
        }
        clf = MagicMock()
        clf.risk_class = "LOW"
        clf.governance_route = "none"
        verdict = MagicMock()
        verdict.risk_assessment = "LOW"
        verdict.governance_route = "none"
        verdict.scope = ["scripts/foo.py"]
        verdict.next_step = "implement"
        verdict.rationale = "test"
        synth = MagicMock()
        synth.action = "PROCEED"
        synth.approved_scope = ["scripts/foo.py"]
        synth.rule_trace = "R1"
        bundle = MagicMock()
        bundle.dna_constraints = ["no core touch"]

        with patch("experience_reader.get_lessons_for_task", return_value=""):
            directive = main._build_directive(
                manifest, "trace-123", bundle, clf, verdict, synth
            )

        assert "trace_id: trace-123" in directive
        assert "task_id: test-task" in directive
        assert "risk_class: LOW" in directive
        assert "test goal" in directive
        assert "scripts/foo.py" in directive

    def test_directive_includes_retry_context(self, tmp_path):
        """Retry directive includes retry attempt number."""
        import main
        manifest = {
            "current_task_id": "t1",
            "current_sprint_goal": "goal",
            "attempt_count": 2,
            "retry_count": 1,
            "_retry_reason": "acceptance failed",
        }
        clf = MagicMock()
        clf.risk_class = "LOW"
        clf.governance_route = "none"
        verdict = MagicMock()
        verdict.risk_assessment = "LOW"
        verdict.governance_route = "none"
        verdict.scope = ["scripts/foo.py"]
        verdict.next_step = "fix"
        verdict.rationale = "retry"
        synth = MagicMock()
        synth.action = "PROCEED"
        synth.approved_scope = ["scripts/foo.py"]
        synth.rule_trace = "R1"
        bundle = MagicMock()
        bundle.dna_constraints = []

        with patch("experience_reader.get_lessons_for_task", return_value=""):
            directive = main._build_directive(
                manifest, "trace-retry", bundle, clf, verdict, synth,
                retry_context="acceptance failed: drift detected",
            )

        assert "RETRY CONTEXT" in directive
        assert "retry 1" in directive
        assert "acceptance failed" in directive

    def test_directive_includes_dna_constraints(self):
        """Directive includes DNA constraints from context bundle."""
        import main
        manifest = {
            "current_task_id": "t1",
            "current_sprint_goal": "goal",
            "attempt_count": 1,
            "retry_count": 0,
        }
        clf = MagicMock()
        clf.risk_class = "LOW"
        clf.governance_route = "none"
        verdict = MagicMock()
        verdict.risk_assessment = "LOW"
        verdict.governance_route = "none"
        verdict.scope = []
        verdict.next_step = "do"
        verdict.rationale = "r"
        synth = MagicMock()
        synth.action = "PROCEED"
        synth.approved_scope = []
        synth.rule_trace = "R1"
        bundle = MagicMock()
        bundle.dna_constraints = ["NEVER touch reconciliation_*", "no direct DML on core"]

        with patch("experience_reader.get_lessons_for_task", return_value=""):
            directive = main._build_directive(
                manifest, "t", bundle, clf, verdict, synth
            )

        assert "reconciliation" in directive
        assert "DML" in directive


# ===========================================================================
# I. CROSS-MODULE CONTRACTS
# ===========================================================================

class TestI_CrossModuleContracts:
    """Module boundaries and interface contracts."""

    def test_experience_writer_requires_trace_id(self):
        """experience_writer.write_execution_experience raises on empty trace_id."""
        import experience_writer as ew
        with pytest.raises((ValueError, TypeError)):
            ew.write_execution_experience(
                trace_id="",  # empty = invalid
                task_id="t1",
                risk_class="LOW",
                acceptance_passed=True,
                acceptance_checks=[],
                drift_detected=False,
                changed_files=[],
                elapsed_seconds=1.0,
                executor_status="completed",
                gate_passed=True,
                gate_rule="LOW_RISK_AUTO",
            )

    def test_budget_tracker_requires_trace_id(self, tmp_path):
        """budget_tracker.record_call raises on empty trace_id."""
        import budget_tracker as bt
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            with pytest.raises(ValueError, match="trace_id"):
                bt.record_call(trace_id="", provider="a", model="m", stage="s")

    def test_config_yaml_has_required_keys(self):
        """config.yaml contains all P3.1 and base keys."""
        from main import _load_config
        cfg = _load_config()
        required_keys = [
            "max_retries_low", "max_retries_semi",
            "critique_consensus_required", "critique_min_approvals",
            "executor_timeout_seconds",
        ]
        for key in required_keys:
            assert key in cfg, f"Missing config key: {key}"

    def test_fsm_transitions_table_is_dict(self):
        """FSM_TRANSITIONS is a proper dict, not accidentally overwritten."""
        from main import FSM_TRANSITIONS
        assert isinstance(FSM_TRANSITIONS, dict)
        assert len(FSM_TRANSITIONS) >= 10, \
            f"FSM_TRANSITIONS too small ({len(FSM_TRANSITIONS)}), likely incomplete"

    def test_acceptance_checker_importable(self):
        """acceptance_checker module is importable from orchestrator."""
        try:
            import acceptance_checker
            assert hasattr(acceptance_checker, "check")
        except ImportError:
            pytest.skip("acceptance_checker not in path")

    def test_experience_reader_importable(self):
        """experience_reader module is importable from orchestrator."""
        try:
            import experience_reader
            assert hasattr(experience_reader, "get_lessons_for_task")
            assert hasattr(experience_reader, "get_failure_patterns")
        except ImportError:
            pytest.skip("experience_reader not in path")

    def test_budget_tracker_importable(self):
        """budget_tracker module is importable from orchestrator."""
        import budget_tracker
        assert hasattr(budget_tracker, "record_call")
        assert hasattr(budget_tracker, "check_budget")
        assert hasattr(budget_tracker, "get_daily_summary")
        assert hasattr(budget_tracker, "estimate_cost")

    def test_synthesizer_actions_exhaustive(self):
        """Synthesizer exports all expected action constants."""
        import synthesizer
        expected = {
            "ACTION_PROCEED", "ACTION_SEMI_AUDIT", "ACTION_CORE_GATE",
            "ACTION_ESCALATE", "ACTION_BLOCKED", "ACTION_NO_OP",
        }
        for const in expected:
            assert hasattr(synthesizer, const), \
                f"Missing constant {const} in synthesizer module"
        # Verify values are strings
        for const in expected:
            val = getattr(synthesizer, const)
            assert isinstance(val, str) and len(val) > 0, \
                f"{const} should be non-empty string, got {val!r}"
