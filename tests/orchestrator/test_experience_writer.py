"""Tests for orchestrator/experience_writer.py — trace-linked experience records."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "orchestrator"))

import experience_writer as ew
import pytest


class TestWriteExecutionExperience:
    def test_writes_record_with_trace_id(self, tmp_path):
        log_file = tmp_path / "experience_2026-04.jsonl"
        with patch.object(ew, "_log_path", return_value=log_file):
            record = ew.write_execution_experience(
                trace_id="orch_test_001",
                task_id="TEST-TASK",
                risk_class="LOW",
                acceptance_passed=True,
                acceptance_checks=[{"check_id": "A1", "passed": True, "detail": "ok"}],
                drift_detected=False,
                changed_files=["foo.py"],
                elapsed_seconds=25.3,
                executor_status="completed",
                gate_passed=True,
                gate_rule="G6:PASS",
            )
        assert record["trace_id"] == "orch_test_001"
        assert record["overall_verdict"] == "PASS"
        assert record["schema_version"] == "execution_experience_v1"
        # File written
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        written = json.loads(lines[0])
        assert written["trace_id"] == "orch_test_001"

    def test_rejects_null_trace_id(self):
        with pytest.raises(ValueError, match="trace_id is required"):
            ew.write_execution_experience(
                trace_id="",
                task_id="TEST",
                risk_class="LOW",
                acceptance_passed=True,
                acceptance_checks=[],
                drift_detected=False,
                changed_files=[],
                elapsed_seconds=0,
                executor_status="completed",
                gate_passed=True,
                gate_rule="G6:PASS",
            )

    def test_rejects_none_trace_id(self):
        with pytest.raises(ValueError, match="trace_id is required"):
            ew.write_execution_experience(
                trace_id=None,
                task_id="TEST",
                risk_class="LOW",
                acceptance_passed=True,
                acceptance_checks=[],
                drift_detected=False,
                changed_files=[],
                elapsed_seconds=0,
                executor_status="completed",
                gate_passed=True,
                gate_rule="G6:PASS",
            )

    def test_verdict_executor_failed(self, tmp_path):
        log_file = tmp_path / "exp.jsonl"
        with patch.object(ew, "_log_path", return_value=log_file):
            record = ew.write_execution_experience(
                trace_id="orch_test_002",
                task_id="TEST",
                risk_class="SEMI",
                acceptance_passed=False,
                acceptance_checks=[],
                drift_detected=False,
                changed_files=[],
                elapsed_seconds=10.0,
                executor_status="failed",
                gate_passed=False,
                gate_rule="G1:EMPTY",
            )
        assert record["overall_verdict"] == "EXECUTOR_FAILED"

    def test_verdict_gate_failed(self, tmp_path):
        log_file = tmp_path / "exp.jsonl"
        with patch.object(ew, "_log_path", return_value=log_file):
            record = ew.write_execution_experience(
                trace_id="orch_test_003",
                task_id="TEST",
                risk_class="LOW",
                acceptance_passed=True,
                acceptance_checks=[],
                drift_detected=False,
                changed_files=["x.py"],
                elapsed_seconds=5.0,
                executor_status="completed",
                gate_passed=False,
                gate_rule="G2:TIER1_VIOLATION",
            )
        assert record["overall_verdict"] == "GATE_FAILED"

    def test_verdict_acceptance_failed(self, tmp_path):
        log_file = tmp_path / "exp.jsonl"
        with patch.object(ew, "_log_path", return_value=log_file):
            record = ew.write_execution_experience(
                trace_id="orch_test_004",
                task_id="TEST",
                risk_class="LOW",
                acceptance_passed=False,
                acceptance_checks=[{"check_id": "A4", "passed": False, "detail": "drift"}],
                drift_detected=True,
                changed_files=["x.py", "y.py"],
                elapsed_seconds=30.0,
                executor_status="completed",
                gate_passed=True,
                gate_rule="G6:PASS",
                out_of_scope_files=["y.py"],
                correction_needed=True,
                correction_detail="drift detected",
            )
        assert record["overall_verdict"] == "ACCEPTANCE_FAILED"
        assert record["drift_detected"] is True
        assert record["correction_needed"] is True

    def test_verdict_audit_failed(self, tmp_path):
        log_file = tmp_path / "exp.jsonl"
        with patch.object(ew, "_log_path", return_value=log_file):
            record = ew.write_execution_experience(
                trace_id="orch_test_005",
                task_id="TEST",
                risk_class="SEMI",
                acceptance_passed=True,
                acceptance_checks=[],
                drift_detected=False,
                changed_files=["x.py"],
                elapsed_seconds=45.0,
                executor_status="completed",
                gate_passed=True,
                gate_rule="G6:PASS",
                audit_verdict="FAIL",
                audit_run_id="run_abc123",
            )
        assert record["overall_verdict"] == "AUDIT_FAILED"

    def test_idempotency_no_duplicate(self, tmp_path):
        log_file = tmp_path / "exp.jsonl"
        with patch.object(ew, "_log_path", return_value=log_file):
            ew.write_execution_experience(
                trace_id="orch_dup_001",
                task_id="TEST",
                risk_class="LOW",
                acceptance_passed=True,
                acceptance_checks=[],
                drift_detected=False,
                changed_files=["a.py"],
                elapsed_seconds=1.0,
                executor_status="completed",
                gate_passed=True,
                gate_rule="G6:PASS",
            )
            # Write again — should be idempotent
            ew.write_execution_experience(
                trace_id="orch_dup_001",
                task_id="TEST",
                risk_class="LOW",
                acceptance_passed=True,
                acceptance_checks=[],
                drift_detected=False,
                changed_files=["a.py"],
                elapsed_seconds=1.0,
                executor_status="completed",
                gate_passed=True,
                gate_rule="G6:PASS",
            )
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1  # only one record

    def test_changed_files_capped_at_20(self, tmp_path):
        log_file = tmp_path / "exp.jsonl"
        files = [f"file_{i}.py" for i in range(30)]
        with patch.object(ew, "_log_path", return_value=log_file):
            record = ew.write_execution_experience(
                trace_id="orch_cap_001",
                task_id="TEST",
                risk_class="LOW",
                acceptance_passed=True,
                acceptance_checks=[],
                drift_detected=False,
                changed_files=files,
                elapsed_seconds=1.0,
                executor_status="completed",
                gate_passed=True,
                gate_rule="G6:PASS",
            )
        assert len(record["changed_files"]) == 20
        assert record["changed_files_count"] == 30


class TestWriteFailureExperience:
    def test_writes_failure_record(self, tmp_path):
        log_file = tmp_path / "exp.jsonl"
        with patch.object(ew, "_log_path", return_value=log_file):
            record = ew.write_failure_experience(
                trace_id="orch_fail_001",
                task_id="FAIL-TASK",
                risk_class="SEMI",
                failure_reason="advisor escalation: parse error",
                failure_stage="advisor",
                elapsed_seconds=5.0,
            )
        assert record["trace_id"] == "orch_fail_001"
        assert record["overall_verdict"] == "EARLY_FAILURE"
        assert record["failure_stage"] == "advisor"
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

    def test_rejects_null_trace_id(self):
        with pytest.raises(ValueError, match="trace_id is required"):
            ew.write_failure_experience(
                trace_id=None,
                task_id="TEST",
                risk_class="LOW",
                failure_reason="test",
                failure_stage="test",
            )

    def test_idempotency(self, tmp_path):
        log_file = tmp_path / "exp.jsonl"
        with patch.object(ew, "_log_path", return_value=log_file):
            ew.write_failure_experience(
                trace_id="orch_dup_fail",
                task_id="TEST",
                risk_class="LOW",
                failure_reason="test",
                failure_stage="test",
            )
            ew.write_failure_experience(
                trace_id="orch_dup_fail",
                task_id="TEST",
                risk_class="LOW",
                failure_reason="test",
                failure_stage="test",
            )
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
