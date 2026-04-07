"""
Tests for enrichment_experience_log.py and providers.py cost counters.

Deterministic — no live API, no I/O side-effects beyond tmp directories.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

# ─────────────────────────────────────────────────────────────────────────────
# enrichment_experience_log
# ─────────────────────────────────────────────────────────────────────────────

from enrichment_experience_log import (
    append_experience_record,
    append_batch_experience,
    _classify_outcome,
    SCHEMA_VERSION,
)


class TestClassifyOutcome:
    def test_auto_publish(self):
        assert _classify_outcome("AUTO_PUBLISH", "KEEP", "public_price") == "publishable"

    def test_review_strong(self):
        assert _classify_outcome("REVIEW_REQUIRED", "KEEP", "public_price") == "review_required_strong"

    def test_review_weak(self):
        assert _classify_outcome("REVIEW_REQUIRED", "REJECT", "public_price") == "review_required_weak"

    def test_no_evidence(self):
        assert _classify_outcome("DRAFT_ONLY", "REJECT", "no_price_found") == "no_evidence"

    def test_identity_mismatch(self):
        assert _classify_outcome("DRAFT_ONLY", "KEEP", "mismatch_detected") == "identity_mismatch"

    def test_draft_incomplete(self):
        assert _classify_outcome("DRAFT_ONLY", "NO_PHOTO", "public_price") == "draft_incomplete"


class TestAppendExperienceRecord:
    def test_record_written(self, tmp_path):
        append_experience_record(
            shadow_log_dir=tmp_path,
            pn="TEST-001",
            task_type="card_finalization",
            decision="AUTO_PUBLISH",
            reason_code=[],
            evidence_refs=["https://example.com/product"],
            outcome="publishable",
            batch_id="batch-001",
        )
        files = list(tmp_path.glob("experience_*.jsonl"))
        assert len(files) == 1
        record = json.loads(files[0].read_text(encoding="utf-8"))
        assert record["pn"] == "TEST-001"
        assert record["schema_version"] == SCHEMA_VERSION
        assert record["outcome"] == "publishable"
        # URL normalised to domain only
        assert record["evidence_refs"] == ["example.com"]

    def test_url_normalised_to_domain(self, tmp_path):
        append_experience_record(
            shadow_log_dir=tmp_path,
            pn="PN-X",
            task_type="price_extraction",
            decision="public_price",
            reason_code="none",
            evidence_refs=["https://shop.example.ru/product/123?ref=abc"],
            outcome="publishable",
        )
        files = list(tmp_path.glob("experience_*.jsonl"))
        record = json.loads(files[0].read_text(encoding="utf-8"))
        assert record["evidence_refs"] == ["shop.example.ru"]

    def test_reason_code_list_joined(self, tmp_path):
        append_experience_record(
            shadow_log_dir=tmp_path,
            pn="PN-Y",
            task_type="card_finalization",
            decision="REVIEW_REQUIRED",
            reason_code=["low_confidence", "price_mismatch"],
            outcome="review_required_weak",
        )
        files = list(tmp_path.glob("experience_*.jsonl"))
        record = json.loads(files[0].read_text(encoding="utf-8"))
        assert record["reason_code"] == "low_confidence|price_mismatch"

    def test_multiple_records_appended(self, tmp_path):
        for i in range(3):
            append_experience_record(
                shadow_log_dir=tmp_path,
                pn=f"PN-{i}",
                task_type="card_finalization",
                decision="DRAFT_ONLY",
                reason_code="none",
                outcome="draft_incomplete",
            )
        files = list(tmp_path.glob("experience_*.jsonl"))
        lines = files[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

    def test_write_failure_is_silent(self, tmp_path):
        # Use a path that cannot be created (file where dir should be)
        blocker = tmp_path / "shadow_log"
        blocker.write_text("I am a file, not a dir")
        # Should not raise
        append_experience_record(
            shadow_log_dir=blocker,
            pn="PN-Z",
            task_type="card_finalization",
            decision="DRAFT_ONLY",
            reason_code="none",
            outcome="draft_incomplete",
        )


class TestAppendBatchExperience:
    def _make_bundle(self, pn, card_status, photo_verdict="NO_PHOTO", price_status="no_price_found"):
        return {
            "pn": pn,
            "card_status": card_status,
            "photo": {"verdict": photo_verdict},
            "price": {"price_status": price_status},
            "review_reasons_v2": [],
        }

    def test_skips_bundle_without_card_status(self, tmp_path):
        bundles = [{"pn": "PN-1"}]  # no card_status
        append_batch_experience(shadow_log_dir=tmp_path, bundles=bundles, batch_id="b1")
        files = list(tmp_path.glob("experience_*.jsonl"))
        assert not files  # nothing written

    def test_writes_one_record_per_bundle(self, tmp_path):
        bundles = [
            self._make_bundle("PN-A", "DRAFT_ONLY"),
            self._make_bundle("PN-B", "AUTO_PUBLISH", "KEEP", "public_price"),
        ]
        append_batch_experience(shadow_log_dir=tmp_path, bundles=bundles, batch_id="b2")
        files = list(tmp_path.glob("experience_*.jsonl"))
        lines = files[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_batch_id_propagated(self, tmp_path):
        bundles = [self._make_bundle("PN-C", "DRAFT_ONLY")]
        append_batch_experience(shadow_log_dir=tmp_path, bundles=bundles, batch_id="my-batch-id")
        files = list(tmp_path.glob("experience_*.jsonl"))
        record = json.loads(files[0].read_text(encoding="utf-8"))
        assert record["batch_id"] == "my-batch-id"


# ─────────────────────────────────────────────────────────────────────────────
# providers — batch cost counters
# ─────────────────────────────────────────────────────────────────────────────

from providers import (
    reset_batch_usage,
    get_batch_usage_summary,
    _record_usage,
    _COST_RATES,
    _COST_ANOMALY_THRESHOLD_USD,
)


class TestBatchCostCounters:
    def setup_method(self):
        reset_batch_usage()

    def test_initial_state_after_reset(self):
        s = get_batch_usage_summary()
        assert s["calls"] == 0
        assert s["input_tokens"] == 0
        assert s["output_tokens"] == 0
        assert s["estimated_cost_usd"] == 0.0
        assert s["cost_anomaly"] is False

    def test_record_usage_accumulates(self):
        _record_usage("claude-haiku-4-5-20251001", input_tokens=1000, output_tokens=500)
        s = get_batch_usage_summary()
        assert s["calls"] == 1
        assert s["input_tokens"] == 1000
        assert s["output_tokens"] == 500
        rates = _COST_RATES["claude-haiku-4-5-20251001"]
        expected_cost = (1000 * rates["input"] + 500 * rates["output"]) / 1_000_000
        assert abs(s["estimated_cost_usd"] - expected_cost) < 1e-9

    def test_multiple_calls_accumulate(self):
        _record_usage("claude-haiku-4-5-20251001", 1000, 200)
        _record_usage("claude-haiku-4-5-20251001", 500, 100)
        s = get_batch_usage_summary()
        assert s["calls"] == 2
        assert s["input_tokens"] == 1500
        assert s["output_tokens"] == 300

    def test_by_model_breakdown(self):
        _record_usage("claude-haiku-4-5-20251001", 1000, 100)
        _record_usage("claude-sonnet-4-6", 200, 50)
        s = get_batch_usage_summary()
        assert "claude-haiku-4-5-20251001" in s["by_model"]
        assert "claude-sonnet-4-6" in s["by_model"]
        assert s["by_model"]["claude-haiku-4-5-20251001"]["calls"] == 1
        assert s["by_model"]["claude-sonnet-4-6"]["calls"] == 1

    def test_cost_anomaly_flag(self):
        # Force anomaly by large token counts
        threshold = _COST_ANOMALY_THRESHOLD_USD
        rates = _COST_RATES["claude-opus-4-6"]
        # tokens needed to exceed threshold
        tokens = int(threshold * 1_000_000 / rates["output"]) + 1
        _record_usage("claude-opus-4-6", input_tokens=0, output_tokens=tokens)
        s = get_batch_usage_summary()
        assert s["cost_anomaly"] is True

    def test_reset_clears_all(self):
        _record_usage("claude-haiku-4-5-20251001", 5000, 2000)
        reset_batch_usage()
        s = get_batch_usage_summary()
        assert s["calls"] == 0
        assert s["estimated_cost_usd"] == 0.0
        assert s["by_model"] == {}

    def test_unknown_model_uses_fallback_rate(self):
        _record_usage("unknown-model-xyz", 1000, 500)
        s = get_batch_usage_summary()
        assert s["calls"] == 1
        # fallback rate = input 1.00, output 5.00
        expected = (1000 * 1.00 + 500 * 5.00) / 1_000_000
        assert abs(s["estimated_cost_usd"] - expected) < 1e-9

    def test_summary_returns_copy(self):
        s1 = get_batch_usage_summary()
        s1["calls"] = 999
        s2 = get_batch_usage_summary()
        assert s2["calls"] == 0  # original not mutated
