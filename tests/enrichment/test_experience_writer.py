"""
Tests for Task 3: Unified Experience Schema v1 (infra/acceleration-bootstrap)

Covers:
- ExperienceRecord with required fields is valid
- Missing required field raises / is rejected
- summary > 200 chars is truncated
- write + read roundtrip (JSONL)
- each adapter maps real shadow_log record format
- adapt_auditor_sink maps ExperienceSink format
- invalid record is rejected with log (not written)
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

import pytest

# Ensure shadow_log/ is importable
_shadow_log_dir = Path(__file__).resolve().parent.parent.parent / "shadow_log"
if str(_shadow_log_dir) not in sys.path:
    sys.path.insert(0, str(_shadow_log_dir))

from experience_writer import (
    ExperienceRecord,
    adapt_auditor_sink,
    adapt_image_shadow,
    adapt_price_shadow,
    write_experience,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_record(**overrides) -> ExperienceRecord:
    defaults = dict(
        record_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        domain="enrichment",
        task_family="photo_validation",
        record_type="event",
        salience_score=7,
        summary="Test summary",
    )
    defaults.update(overrides)
    return ExperienceRecord(**defaults)


# ---------------------------------------------------------------------------
# Test 1: valid required fields
# ---------------------------------------------------------------------------

def test_valid_record_writes(tmp_path):
    out = tmp_path / "test.jsonl"
    record = _make_valid_record(summary="Valid record test")
    write_experience(record, file_path=out)
    assert out.exists()
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["summary"] == "Valid record test"
    assert data["domain"] == "enrichment"


# ---------------------------------------------------------------------------
# Test 2: missing required field → rejected (not written)
# ---------------------------------------------------------------------------

def test_missing_required_field_rejected(tmp_path, caplog):
    import logging
    out = tmp_path / "test.jsonl"
    # summary is empty string — treated as missing
    record = _make_valid_record(summary="")
    with caplog.at_level(logging.WARNING):
        write_experience(record, file_path=out)
    assert not out.exists() or out.read_text(encoding="utf-8").strip() == ""


# ---------------------------------------------------------------------------
# Test 3: summary > 200 chars → truncated to 200
# ---------------------------------------------------------------------------

def test_summary_truncated(tmp_path):
    out = tmp_path / "test.jsonl"
    long_summary = "X" * 250
    record = _make_valid_record(summary=long_summary)
    write_experience(record, file_path=out)
    data = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert len(data["summary"]) == 200


# ---------------------------------------------------------------------------
# Test 4: write + read roundtrip (JSONL)
# ---------------------------------------------------------------------------

def test_write_read_roundtrip(tmp_path):
    out = tmp_path / "unified.jsonl"
    records = [_make_valid_record(summary=f"Record {i}", salience_score=i) for i in range(1, 6)]
    for r in records:
        write_experience(r, file_path=out)

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    for i, line in enumerate(lines, start=1):
        data = json.loads(line)
        assert data["summary"] == f"Record {i}"
        assert data["salience_score"] == i


# ---------------------------------------------------------------------------
# Test 5: adapt_price_shadow maps real shadow_log record format
# ---------------------------------------------------------------------------

_PRICE_SAMPLE = {
    "schema_version": "photo_pipeline_shadow_log_record_v1",
    "ts": "2026-04-07T11:36:45.628274Z",
    "pn": "00020211",
    "brand": "Honeywell",
    "task_type": "price_extraction",
    "provider": "openai",
    "model": "claude-haiku-4-5",
    "model_alias": "claude-haiku-4-5",
    "model_resolved": "claude-haiku-4-5",
    "prompt": "extract",
    "response_raw": "",
    "response_parsed": {},
    "parse_success": False,
    "latency_ms": 0,
    "error_class": "RuntimeError",
    "human_correction": None,
    "correction_ts": None,
    "source_url": None,
    "source_type": None,
}


def test_adapt_price_shadow():
    record = adapt_price_shadow(_PRICE_SAMPLE)
    assert isinstance(record, ExperienceRecord)
    assert record.domain == "pricing"
    assert record.task_family == "price_extraction"
    assert record.entity_id == "00020211"
    assert record.entity_type == "sku"
    assert len(record.summary) <= 200
    assert record.record_type in {"event", "lesson", "decision", "rule", "golden_case", "failure_pattern"}


# ---------------------------------------------------------------------------
# Test 6: adapt_image_shadow maps real shadow_log image_validation format
# ---------------------------------------------------------------------------

_IMAGE_SAMPLE = {
    "schema_version": "photo_pipeline_shadow_log_record_v1",
    "ts": "2026-04-07T18:19:46.589532Z",
    "pn": "13960",
    "brand": "Honeywell",
    "task_type": "image_validation",
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "model_alias": "claude-sonnet-4-6",
    "model_resolved": "claude-sonnet-4-6",
    "prompt": "Assess image",
    "response_raw": '{"verdict": "KEEP", "reason": "product matches"}',
    "response_parsed": {"verdict": "KEEP", "reason": "product matches"},
    "parse_success": True,
    "latency_ms": 2858,
    "error_class": None,
    "human_correction": None,
    "correction_ts": None,
    "source_url": None,
    "source_type": None,
}


def test_adapt_image_shadow():
    record = adapt_image_shadow(_IMAGE_SAMPLE)
    assert isinstance(record, ExperienceRecord)
    assert record.domain == "enrichment"
    assert record.task_family == "photo_validation"
    assert record.entity_id == "13960"
    assert "KEEP" in record.summary
    assert len(record.summary) <= 200


# ---------------------------------------------------------------------------
# Test 7: adapt_auditor_sink maps ExperienceSink format
# ---------------------------------------------------------------------------

_AUDITOR_SINK_SAMPLE = {
    "trace_id": "test-trace-abc",
    "task": {
        "stage": "r1-catalog",
        "risk": "semi",
        "type": "catalog_enrichment",
        "mutation_surface": ["scripts/photo_pipeline.py"],
    },
    "context_summary": "Catalog enrichment batch 50",
    "rejected_solution": None,
    "chosen_solution": {
        "model": "sonnet",
        "effort": "medium",
        "proposal_hash": "sha256:abcdef01",
        "issues_found": [],
    },
    "escalation": False,
    "escalation_reason": None,
    "escalation_helped": False,
    "owner_override": False,
    "owner_verdict": "approved",
    "owner_role": "batch_approver",
    "post_audit_clean": True,
    "cost_usd": 0.05,
    "duration_minutes": 3.2,
    "timestamp": "2026-04-07T20:00:00+00:00",
    "surface_mismatch": False,
}


def test_adapt_auditor_sink():
    record = adapt_auditor_sink(_AUDITOR_SINK_SAMPLE)
    assert isinstance(record, ExperienceRecord)
    assert record.domain == "audit"
    assert record.task_family == "core_gate_review"
    assert record.trace_id == "test-trace-abc"
    assert "approved" in record.summary
    assert len(record.summary) <= 200
    assert record.salience_score >= 1


# ---------------------------------------------------------------------------
# Test 8: invalid record → rejected, file not written
# ---------------------------------------------------------------------------

def test_invalid_record_not_written(tmp_path, caplog):
    import logging
    out = tmp_path / "test.jsonl"
    record = _make_valid_record(salience_score=99)  # out of range 1-10
    with caplog.at_level(logging.WARNING):
        write_experience(record, file_path=out)
    # File should not exist or be empty
    assert not out.exists() or out.read_text(encoding="utf-8").strip() == ""
