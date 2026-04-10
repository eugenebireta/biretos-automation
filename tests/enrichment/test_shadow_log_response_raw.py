"""Tests for shadow_log response_raw preservation (Block 1 fix)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
import datetime

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def _write_shadow_log(tmp_dir, response_raw, error_class=None):
    """Helper: invoke shadow_log() and return the written record."""
    import photo_pipeline as pp
    orig_dir = pp.SHADOW_LOG_DIR
    pp.SHADOW_LOG_DIR = Path(tmp_dir)
    try:
        pp.shadow_log(
            task_type="price_extraction",
            pn="TEST123",
            brand="Honeywell",
            model="claude-haiku-4-5",
            provider="anthropic",
            model_alias="claude-haiku-4-5",
            model_resolved="claude-haiku-4-5-20251001",
            prompt="test prompt",
            response_raw=response_raw,
            response_parsed={},
            parse_success=False,
            latency_ms=100,
            error_class=error_class,
        )
    finally:
        pp.SHADOW_LOG_DIR = orig_dir

    month = datetime.datetime.utcnow().strftime("%Y-%m")
    path = Path(tmp_dir) / f"price_extraction_{month}.jsonl"
    with open(path, encoding="utf-8") as f:
        return json.loads(f.read().strip())


class TestResponseRawPreservation:
    def test_successful_response_preserved(self):
        """Successful LLM response is stored in full."""
        with tempfile.TemporaryDirectory() as tmp:
            record = _write_shadow_log(tmp, '{"pn_found": true}')
        assert record["response_raw"] == '{"pn_found": true}'
        assert record["response_raw_present"] is True
        assert record["response_raw_truncated"] is False

    def test_none_for_api_failure(self):
        """API failure path stores response_raw=None."""
        with tempfile.TemporaryDirectory() as tmp:
            record = _write_shadow_log(tmp, None, error_class="RuntimeError")
        assert record["response_raw"] is None
        assert record["response_raw_present"] is False

    def test_empty_string_stored_as_empty(self):
        """Empty string response stored as-is (unexpected but non-fatal)."""
        with tempfile.TemporaryDirectory() as tmp:
            record = _write_shadow_log(tmp, "")
        assert record["response_raw"] == ""
        assert record["response_raw_present"] is False

    def test_long_response_truncated(self):
        """Response longer than _MAX_RESPONSE_RAW_CHARS is truncated."""
        import photo_pipeline as pp
        long_resp = "x" * (pp._MAX_RESPONSE_RAW_CHARS + 500)
        with tempfile.TemporaryDirectory() as tmp:
            record = _write_shadow_log(tmp, long_resp)
        assert len(record["response_raw"]) == pp._MAX_RESPONSE_RAW_CHARS
        assert record["response_raw_truncated"] is True

    def test_normal_length_not_truncated(self):
        """Normal response is NOT truncated."""
        response = '{"pn_found": true, "price": 42.0, "currency": "EUR"}'
        with tempfile.TemporaryDirectory() as tmp:
            record = _write_shadow_log(tmp, response)
        assert record["response_raw"] == response
        assert record["response_raw_truncated"] is False

    def test_response_raw_present_field_exists(self):
        """response_raw_present field always present in record."""
        with tempfile.TemporaryDirectory() as tmp:
            record = _write_shadow_log(tmp, "some text")
        assert "response_raw_present" in record
        assert "response_raw_truncated" in record

    def test_failure_distinguishable_from_empty(self):
        """None (API failure) is distinguishable from '' (empty response)."""
        with tempfile.TemporaryDirectory() as tmp1:
            rec_none = _write_shadow_log(tmp1, None, error_class="RuntimeError")
        with tempfile.TemporaryDirectory() as tmp2:
            rec_empty = _write_shadow_log(tmp2, "")
        # Both have response_raw_present=False, but different raw values
        assert rec_none["response_raw"] is None
        assert rec_empty["response_raw"] == ""
        assert rec_none["response_raw"] != rec_empty["response_raw"]


class TestShadowLogV2Fields:
    """v2 fields: prompt_version, trace_id, pipeline_stage, schema_version bump."""

    def test_v2_schema_version(self):
        """Schema version is v2."""
        with tempfile.TemporaryDirectory() as tmp:
            record = _write_shadow_log(tmp, '{"ok": true}')
        assert record["schema_version"] == "photo_pipeline_shadow_log_record_v2"

    def test_prompt_version_stored(self):
        """prompt_version kwarg is stored in record."""
        import photo_pipeline as pp
        orig_dir = pp.SHADOW_LOG_DIR
        with tempfile.TemporaryDirectory() as tmp:
            pp.SHADOW_LOG_DIR = Path(tmp)
            try:
                pp.shadow_log(
                    task_type="price_extraction",
                    pn="TEST123", brand="Honeywell",
                    model="claude-haiku-4-5", provider="anthropic",
                    model_alias="claude-haiku-4-5",
                    model_resolved="claude-haiku-4-5-20251001",
                    prompt="test", response_raw="ok",
                    response_parsed={}, parse_success=True,
                    prompt_version="v11",
                    trace_id="trace_abc123",
                    pipeline_stage="price_extraction",
                )
            finally:
                pp.SHADOW_LOG_DIR = orig_dir

            month = datetime.datetime.utcnow().strftime("%Y-%m")
            path = Path(tmp) / f"price_extraction_{month}.jsonl"
            record = json.loads(path.read_text(encoding="utf-8").strip())

        assert record["prompt_version"] == "v11"
        assert record["trace_id"] == "trace_abc123"
        assert record["pipeline_stage"] == "price_extraction"

    def test_defaults_when_v2_fields_omitted(self):
        """When v2 kwargs are not passed, fields are null/derived."""
        with tempfile.TemporaryDirectory() as tmp:
            record = _write_shadow_log(tmp, '{"ok": true}')
        assert record["prompt_version"] is None
        assert record["trace_id"] is None
        # pipeline_stage defaults to task_type
        assert record["pipeline_stage"] == "price_extraction"

    def test_backward_compatible_with_existing_callers(self):
        """Existing callers without v2 kwargs still work (no TypeError)."""
        import photo_pipeline as pp
        orig_dir = pp.SHADOW_LOG_DIR
        with tempfile.TemporaryDirectory() as tmp:
            pp.SHADOW_LOG_DIR = Path(tmp)
            try:
                # Call without any v2 kwargs — must not raise
                pp.shadow_log(
                    task_type="image_validation",
                    pn="PN", brand="B",
                    model="m", provider="p",
                    model_alias="m", model_resolved="m",
                    prompt="p", response_raw="r",
                    response_parsed={}, parse_success=True,
                )
            finally:
                pp.SHADOW_LOG_DIR = orig_dir

            month = datetime.datetime.utcnow().strftime("%Y-%m")
            path = Path(tmp) / f"image_validation_{month}.jsonl"
            record = json.loads(path.read_text(encoding="utf-8").strip())

        assert record["prompt_version"] is None
        assert record["trace_id"] is None
