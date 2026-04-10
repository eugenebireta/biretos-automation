"""
test_experience_reader.py — P5: Tests for experience_reader.py.

All tests use tmp_path — no real shadow_log touched.
Covers:
  1. Loading records by schema version
  2. Task-specific history extraction
  3. Failure pattern analysis
  4. Lessons generation with various failure types
  5. Empty/missing log handling
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

import pytest

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)


def _write_records(path: Path, records: list[dict]) -> None:
    """Write records to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _make_record(
    trace_id="test-trace",
    task_id="test-task",
    verdict="PASS",
    risk="LOW",
    drift=False,
    checks=None,
    oos_files=None,
    changed_files=None,
    elapsed=10.0,
    correction_detail=None,
):
    """Create a mock execution_experience_v1 record."""
    return {
        "schema_version": "execution_experience_v1",
        "ts": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "task_id": task_id,
        "risk_class": risk,
        "overall_verdict": verdict,
        "executor_status": "completed",
        "elapsed_seconds": elapsed,
        "gate_passed": True,
        "gate_rule": "LOW_RISK_AUTO",
        "acceptance_passed": verdict == "PASS",
        "acceptance_checks": checks or [],
        "drift_detected": drift,
        "out_of_scope_files": oos_files or [],
        "changed_files_count": len(changed_files or []),
        "changed_files": changed_files or [],
        "audit_verdict": None,
        "audit_run_id": None,
        "correction_needed": verdict != "PASS",
        "correction_detail": correction_detail,
    }


# ---------------------------------------------------------------------------
# _load_experience_records
# ---------------------------------------------------------------------------

class TestLoadRecords:
    """Loading records filters by schema version."""

    def test_loads_v1_records_only(self, tmp_path):
        import experience_reader as er

        now = datetime.now(timezone.utc)
        log_name = f"experience_{now.strftime('%Y-%m')}.jsonl"
        log_path = tmp_path / log_name

        records = [
            _make_record(trace_id="good"),
            {"schema_version": "experience_log_v1", "trace_id": None, "task_id": "old"},
            {"schema_version": "brand_experience_v1", "brand": "test"},
        ]
        _write_records(log_path, records)

        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            loaded = er._load_experience_records(months=1)

        assert len(loaded) == 1
        assert loaded[0]["trace_id"] == "good"

    def test_empty_dir_returns_empty(self, tmp_path):
        import experience_reader as er
        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            assert er._load_experience_records() == []

    def test_corrupt_lines_skipped(self, tmp_path):
        import experience_reader as er

        now = datetime.now(timezone.utc)
        log_path = tmp_path / f"experience_{now.strftime('%Y-%m')}.jsonl"
        log_path.write_text(
            'not json\n'
            + json.dumps(_make_record(trace_id="ok")) + '\n'
            + '{"broken": true\n',
            encoding="utf-8",
        )

        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            loaded = er._load_experience_records(months=1)

        assert len(loaded) == 1
        assert loaded[0]["trace_id"] == "ok"


# ---------------------------------------------------------------------------
# get_task_history
# ---------------------------------------------------------------------------

class TestTaskHistory:
    """Task-specific history extraction."""

    def test_filters_by_task_id(self):
        import experience_reader as er
        records = [
            _make_record(task_id="target"),
            _make_record(task_id="other"),
            _make_record(task_id="target", verdict="ACCEPTANCE_FAILED"),
        ]
        history = er.get_task_history("target", records)
        assert len(history) == 2
        assert all(r["task_id"] == "target" for r in history)

    def test_empty_if_no_match(self):
        import experience_reader as er
        records = [_make_record(task_id="other")]
        assert er.get_task_history("missing", records) == []


# ---------------------------------------------------------------------------
# get_failure_patterns
# ---------------------------------------------------------------------------

class TestFailurePatterns:
    """Global failure pattern analysis."""

    def test_drift_rate_calculation(self):
        import experience_reader as er
        records = [
            _make_record(drift=True),
            _make_record(drift=True),
            _make_record(drift=False),
            _make_record(drift=False),
        ]
        patterns = er.get_failure_patterns(records)
        assert patterns["drift_rate"] == 0.5

    def test_common_oos_files(self):
        import experience_reader as er
        records = [
            _make_record(oos_files=["core/a.py", "domain/b.py"]),
            _make_record(oos_files=["core/a.py"]),
            _make_record(oos_files=["core/a.py", "domain/c.py"]),
        ]
        patterns = er.get_failure_patterns(records)
        assert "core/a.py" in patterns["common_oos_files"]

    def test_common_failures(self):
        import experience_reader as er
        records = [
            _make_record(checks=[
                {"check_id": "A2:TIER1_SAFE", "passed": False, "detail": "touched core"},
            ]),
            _make_record(checks=[
                {"check_id": "A2:TIER1_SAFE", "passed": False, "detail": "touched core"},
                {"check_id": "A4:SCOPE", "passed": False, "detail": "drift"},
            ]),
        ]
        patterns = er.get_failure_patterns(records)
        assert "A2:TIER1_SAFE" in patterns["common_failures"]
        assert patterns["common_failures"]["A2:TIER1_SAFE"] == 2

    def test_empty_records(self):
        import experience_reader as er
        patterns = er.get_failure_patterns([])
        assert patterns["drift_rate"] == 0.0
        assert patterns["common_failures"] == {}

    def test_avg_elapsed(self):
        import experience_reader as er
        records = [
            _make_record(elapsed=10.0),
            _make_record(elapsed=20.0),
        ]
        patterns = er.get_failure_patterns(records)
        assert patterns["avg_elapsed"] == 15.0


# ---------------------------------------------------------------------------
# get_lessons_for_task
# ---------------------------------------------------------------------------

class TestGetLessons:
    """Lessons generation for directive injection."""

    def test_no_records_returns_empty(self, tmp_path):
        import experience_reader as er
        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            lessons = er.get_lessons_for_task("new-task")
        assert lessons == ""

    def test_task_failure_produces_lesson(self, tmp_path):
        import experience_reader as er

        now = datetime.now(timezone.utc)
        log_path = tmp_path / f"experience_{now.strftime('%Y-%m')}.jsonl"
        records = [
            _make_record(
                task_id="retry-task",
                verdict="ACCEPTANCE_FAILED",
                checks=[
                    {"check_id": "A4:SCOPE_COMPLIANCE", "passed": False,
                     "detail": "drift detected"},
                ],
                correction_detail="drift: touched out-of-scope files",
            ),
        ]
        _write_records(log_path, records)

        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            lessons = er.get_lessons_for_task("retry-task")

        assert "Lessons from Past Runs" in lessons
        assert "A4:SCOPE_COMPLIANCE" in lessons

    def test_drift_warning_included(self, tmp_path):
        import experience_reader as er

        now = datetime.now(timezone.utc)
        log_path = tmp_path / f"experience_{now.strftime('%Y-%m')}.jsonl"
        # 3 out of 4 records have drift → 75% drift rate
        records = [
            _make_record(drift=True, task_id="a"),
            _make_record(drift=True, task_id="b"),
            _make_record(drift=True, task_id="c"),
            _make_record(drift=False, task_id="d"),
        ]
        _write_records(log_path, records)

        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            lessons = er.get_lessons_for_task("new-task")

        assert "scope drift" in lessons.lower()

    def test_oos_files_listed(self, tmp_path):
        import experience_reader as er

        now = datetime.now(timezone.utc)
        log_path = tmp_path / f"experience_{now.strftime('%Y-%m')}.jsonl"
        records = [
            _make_record(oos_files=["core/forbidden.py"]),
        ]
        _write_records(log_path, records)

        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            lessons = er.get_lessons_for_task("other-task")

        assert "core/forbidden.py" in lessons

    def test_successful_run_shows_changed_files(self, tmp_path):
        import experience_reader as er

        now = datetime.now(timezone.utc)
        log_path = tmp_path / f"experience_{now.strftime('%Y-%m')}.jsonl"
        records = [
            _make_record(
                task_id="repeat-task",
                verdict="PASS",
                changed_files=["scripts/widget.py", "tests/test_widget.py"],
            ),
        ]
        _write_records(log_path, records)

        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            lessons = er.get_lessons_for_task("repeat-task")

        assert "scripts/widget.py" in lessons

    def test_max_lessons_cap(self, tmp_path):
        import experience_reader as er

        now = datetime.now(timezone.utc)
        log_path = tmp_path / f"experience_{now.strftime('%Y-%m')}.jsonl"
        # Create many failure records to generate many lessons
        records = [
            _make_record(
                task_id="many-fails",
                verdict="ACCEPTANCE_FAILED",
                trace_id=f"trace-{i}",
                drift=True,
                checks=[{"check_id": f"A{i}", "passed": False, "detail": f"fail {i}"}],
                oos_files=[f"bad/file{i}.py"],
            )
            for i in range(10)
        ]
        _write_records(log_path, records)

        with patch.object(er, "SHADOW_LOG_DIR", tmp_path):
            lessons = er.get_lessons_for_task("many-fails", max_lessons=3)

        # Count bullet points
        bullet_count = lessons.count("- ")
        assert bullet_count <= 3
