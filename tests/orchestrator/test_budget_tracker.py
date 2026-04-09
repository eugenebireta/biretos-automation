"""
test_budget_tracker.py — P7: Tests for budget_tracker.py.

All tests use tmp_path — no real shadow_log touched.
Covers:
  1. Cost estimation with known/unknown models
  2. Record writing and JSONL persistence
  3. Record loading with schema filtering
  4. Trace cost aggregation
  5. Daily summary breakdown
  6. Budget limit checking
  7. Idempotency key generation
  8. Corrupt/empty log handling
"""
from __future__ import annotations

import json
import sys
import os
from datetime import datetime, timezone, date
from pathlib import Path
from unittest.mock import patch

import pytest

_orch_dir = os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator")
if _orch_dir not in sys.path:
    sys.path.insert(0, _orch_dir)


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------

class TestEstimateCost:
    """Cost estimation from model pricing table."""

    def test_known_model_sonnet(self):
        import budget_tracker as bt
        # 1000 input + 500 output for claude-sonnet-4-6
        # input: (1000/1M) * 3.0 = 0.003
        # output: (500/1M) * 15.0 = 0.0075
        cost = bt.estimate_cost("claude-sonnet-4-6", 1000, 500)
        assert abs(cost - 0.0105) < 0.0001

    def test_known_model_opus(self):
        import budget_tracker as bt
        cost = bt.estimate_cost("claude-opus-4-6", 1000, 500)
        # input: (1000/1M) * 15.0 = 0.015
        # output: (500/1M) * 75.0 = 0.0375
        assert abs(cost - 0.0525) < 0.0001

    def test_unknown_model_returns_zero(self):
        import budget_tracker as bt
        assert bt.estimate_cost("totally-unknown-model", 1000, 500) == 0.0

    def test_partial_match(self):
        import budget_tracker as bt
        # "claude-sonnet-4-6" is in "claude-sonnet-4-6-20260301"
        cost = bt.estimate_cost("claude-sonnet-4-6-20260301", 1000, 500)
        assert cost > 0

    def test_zero_tokens(self):
        import budget_tracker as bt
        assert bt.estimate_cost("claude-sonnet-4-6", 0, 0) == 0.0

    def test_gemini_model(self):
        import budget_tracker as bt
        cost = bt.estimate_cost("gemini-2.5-pro", 10000, 5000)
        assert cost > 0


# ---------------------------------------------------------------------------
# record_call
# ---------------------------------------------------------------------------

class TestRecordCall:
    """Writing budget records to JSONL."""

    def test_writes_record(self, tmp_path):
        import budget_tracker as bt
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            rec = bt.record_call(
                trace_id="test-trace",
                provider="anthropic",
                model="claude-sonnet-4-6",
                stage="advisor",
                input_tokens=1000,
                output_tokens=500,
            )

        assert rec["schema_version"] == "budget_record_v1"
        assert rec["trace_id"] == "test-trace"
        assert rec["provider"] == "anthropic"
        assert rec["stage"] == "advisor"
        assert rec["cost_usd"] > 0

        # Verify JSONL written
        files = list(tmp_path.glob("budget_*.jsonl"))
        assert len(files) == 1
        line = files[0].read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert parsed["trace_id"] == "test-trace"

    def test_explicit_cost_override(self, tmp_path):
        import budget_tracker as bt
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            rec = bt.record_call(
                trace_id="t1", provider="anthropic",
                model="unknown", stage="executor",
                cost_usd=1.23,
            )
        assert rec["cost_usd"] == 1.23

    def test_requires_trace_id(self, tmp_path):
        import budget_tracker as bt
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            with pytest.raises(ValueError, match="trace_id"):
                bt.record_call(
                    trace_id="", provider="anthropic",
                    model="test", stage="test",
                )

    def test_idempotency_key_format(self, tmp_path):
        import budget_tracker as bt
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            rec = bt.record_call(
                trace_id="tr-123", provider="anthropic",
                model="test", stage="test", call_seq=5,
            )
        assert rec["idempotency_key"] == "budget_tr-123_5"

    def test_metadata_included(self, tmp_path):
        import budget_tracker as bt
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            rec = bt.record_call(
                trace_id="tr-1", provider="anthropic",
                model="test", stage="test",
                metadata={"attempt": 2},
            )
        assert rec["metadata"] == {"attempt": 2}

    def test_multiple_records_append(self, tmp_path):
        import budget_tracker as bt
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            bt.record_call(trace_id="t1", provider="a", model="m", stage="s", call_seq=0)
            bt.record_call(trace_id="t1", provider="a", model="m", stage="s", call_seq=1)
            bt.record_call(trace_id="t2", provider="a", model="m", stage="s", call_seq=0)

        files = list(tmp_path.glob("budget_*.jsonl"))
        lines = files[0].read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3


# ---------------------------------------------------------------------------
# _load_records
# ---------------------------------------------------------------------------

class TestLoadRecords:
    """Loading records with filtering."""

    def test_loads_v1_only(self, tmp_path):
        import budget_tracker as bt
        now = datetime.now(timezone.utc)
        log_path = tmp_path / f"budget_{now.strftime('%Y-%m')}.jsonl"
        records = [
            {"schema_version": "budget_record_v1", "trace_id": "good", "ts": now.isoformat(), "cost_usd": 0.1},
            {"schema_version": "old_v0", "trace_id": "bad", "ts": now.isoformat()},
        ]
        log_path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n",
            encoding="utf-8",
        )

        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            loaded = bt._load_records(months=1)
        assert len(loaded) == 1
        assert loaded[0]["trace_id"] == "good"

    def test_empty_dir(self, tmp_path):
        import budget_tracker as bt
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            assert bt._load_records() == []

    def test_corrupt_lines_skipped(self, tmp_path):
        import budget_tracker as bt
        now = datetime.now(timezone.utc)
        log_path = tmp_path / f"budget_{now.strftime('%Y-%m')}.jsonl"
        log_path.write_text(
            "not json\n"
            + json.dumps({"schema_version": "budget_record_v1", "trace_id": "ok",
                          "ts": now.isoformat(), "cost_usd": 0.1}) + "\n",
            encoding="utf-8",
        )
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            loaded = bt._load_records(months=1)
        assert len(loaded) == 1

    def test_date_filter(self, tmp_path):
        import budget_tracker as bt
        now = datetime.now(timezone.utc)
        log_path = tmp_path / f"budget_{now.strftime('%Y-%m')}.jsonl"
        records = [
            {"schema_version": "budget_record_v1", "trace_id": "today",
             "ts": now.isoformat(), "cost_usd": 0.1},
            {"schema_version": "budget_record_v1", "trace_id": "yesterday",
             "ts": "2020-01-01T00:00:00+00:00", "cost_usd": 0.2},
        ]
        log_path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n",
            encoding="utf-8",
        )
        with patch.object(bt, "SHADOW_LOG_DIR", tmp_path):
            loaded = bt._load_records(months=1, target_date=now.date())
        assert len(loaded) == 1
        assert loaded[0]["trace_id"] == "today"


# ---------------------------------------------------------------------------
# get_trace_cost
# ---------------------------------------------------------------------------

class TestTraceCost:
    """Trace cost aggregation."""

    def test_sums_trace_records(self):
        import budget_tracker as bt
        records = [
            {"trace_id": "t1", "cost_usd": 0.5},
            {"trace_id": "t1", "cost_usd": 0.3},
            {"trace_id": "t2", "cost_usd": 1.0},
        ]
        assert bt.get_trace_cost("t1", records) == pytest.approx(0.8)
        assert bt.get_trace_cost("t2", records) == pytest.approx(1.0)
        assert bt.get_trace_cost("t3", records) == 0.0


# ---------------------------------------------------------------------------
# get_daily_summary
# ---------------------------------------------------------------------------

class TestDailySummary:
    """Daily cost breakdown."""

    def test_summary_structure(self):
        import budget_tracker as bt
        today = date.today()
        records = [
            {"trace_id": "t1", "cost_usd": 0.5, "stage": "advisor",
             "model": "claude-sonnet-4-6", "provider": "anthropic",
             "ts": datetime.now(timezone.utc).isoformat()},
            {"trace_id": "t1", "cost_usd": 0.3, "stage": "executor",
             "model": "claude-sonnet-4-6", "provider": "anthropic",
             "ts": datetime.now(timezone.utc).isoformat()},
            {"trace_id": "t1", "cost_usd": 0.1, "stage": "auditor",
             "model": "gemini-2.5-pro", "provider": "google",
             "ts": datetime.now(timezone.utc).isoformat()},
        ]
        summary = bt.get_daily_summary(target_date=today, records=records)
        assert summary["date"] == today.isoformat()
        assert summary["total_cost_usd"] == pytest.approx(0.9)
        assert summary["call_count"] == 3
        assert "advisor" in summary["by_stage"]
        assert "executor" in summary["by_stage"]
        assert "auditor" in summary["by_stage"]
        assert "anthropic" in summary["by_provider"]
        assert "google" in summary["by_provider"]

    def test_empty_records(self):
        import budget_tracker as bt
        summary = bt.get_daily_summary(records=[])
        assert summary["total_cost_usd"] == 0.0
        assert summary["call_count"] == 0


# ---------------------------------------------------------------------------
# check_budget
# ---------------------------------------------------------------------------

class TestCheckBudget:
    """Budget limit enforcement."""

    def test_within_budget(self):
        import budget_tracker as bt
        now = datetime.now(timezone.utc)
        records = [
            {"trace_id": "t1", "cost_usd": 0.5, "ts": now.isoformat()},
        ]
        result = bt.check_budget("t1", daily_limit=10.0, per_run_limit=2.0,
                                  records=records)
        assert result["within_budget"] is True
        assert result["daily_exceeded"] is False
        assert result["run_exceeded"] is False

    def test_daily_exceeded(self):
        import budget_tracker as bt
        now = datetime.now(timezone.utc)
        records = [
            {"trace_id": f"t{i}", "cost_usd": 3.0, "ts": now.isoformat()}
            for i in range(5)
        ]
        result = bt.check_budget("t0", daily_limit=10.0, per_run_limit=5.0,
                                  records=records)
        assert result["within_budget"] is False
        assert result["daily_exceeded"] is True
        assert result["daily_cost"] == pytest.approx(15.0)

    def test_per_run_exceeded(self):
        import budget_tracker as bt
        now = datetime.now(timezone.utc)
        records = [
            {"trace_id": "t1", "cost_usd": 1.5, "ts": now.isoformat()},
            {"trace_id": "t1", "cost_usd": 1.0, "ts": now.isoformat()},
        ]
        result = bt.check_budget("t1", daily_limit=100.0, per_run_limit=2.0,
                                  records=records)
        assert result["within_budget"] is False
        assert result["run_exceeded"] is True
        assert result["trace_cost"] == pytest.approx(2.5)

    def test_empty_records_within_budget(self):
        import budget_tracker as bt
        result = bt.check_budget("t1", records=[])
        assert result["within_budget"] is True
