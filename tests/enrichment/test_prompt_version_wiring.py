"""Tests for prompt_version end-to-end wiring through call_gpt → shadow_log.

Proves that the real production code path emits non-null prompt_version in
shadow log records for both price_extraction and image_validation tasks.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


class _MockAdapter:
    """Minimal ChatCompletionAdapter that returns a canned JSON response."""

    def __init__(self, response: str = '{"pn_found": true}'):
        self._response = response
        self.last_call_metadata = {
            "provider": "mock",
            "model_alias": "mock-model",
            "model_resolved": "mock-model-v1",
            "latency_ms": 42,
            "error_class": None,
        }

    def complete(self, *, model: str, messages: list[dict], **api_kwargs) -> str:
        return self._response


class _FailingAdapter:
    """Adapter that always raises."""

    last_call_metadata = {
        "provider": "mock",
        "model_alias": "mock-model",
        "model_resolved": "mock-model-v1",
        "latency_ms": None,
        "error_class": "RuntimeError",
    }

    def complete(self, *, model: str, messages: list[dict], **api_kwargs) -> str:
        raise RuntimeError("Simulated API failure")


def _read_shadow_record(tmp_dir: str, task_type: str) -> dict:
    month = datetime.datetime.utcnow().strftime("%Y-%m")
    path = Path(tmp_dir) / f"{task_type}_{month}.jsonl"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return json.loads(lines[-1])


class TestPromptVersionInCallGpt:
    """call_gpt() threads prompt_version into shadow_log records."""

    def test_price_extraction_gets_prompt_version(self):
        """Price extraction call emits non-null prompt_version."""
        import photo_pipeline as pp

        with tempfile.TemporaryDirectory() as tmp:
            orig_dir = pp.SHADOW_LOG_DIR
            pp.SHADOW_LOG_DIR = Path(tmp)
            try:
                pp.call_gpt(
                    task_type="price_extraction",
                    pn="TEST-PN",
                    brand="Honeywell",
                    messages=[{"role": "user", "content": "test"}],
                    model="mock-model",
                    adapter=_MockAdapter(),
                    prompt_version=pp.PRICE_EXTRACTION_PROMPT_VERSION,
                )
            finally:
                pp.SHADOW_LOG_DIR = orig_dir

            record = _read_shadow_record(tmp, "price_extraction")

        assert record["prompt_version"] == "price_extraction_v11"
        assert record["pipeline_stage"] == "price_extraction"
        assert record["schema_version"] == "photo_pipeline_shadow_log_record_v2"

    def test_image_validation_gets_prompt_version(self):
        """Image validation call emits non-null prompt_version."""
        import photo_pipeline as pp

        with tempfile.TemporaryDirectory() as tmp:
            orig_dir = pp.SHADOW_LOG_DIR
            pp.SHADOW_LOG_DIR = Path(tmp)
            try:
                pp.call_gpt(
                    task_type="image_validation",
                    pn="TEST-PN",
                    brand="Honeywell",
                    messages=[{"role": "user", "content": "test"}],
                    model="mock-model",
                    adapter=_MockAdapter('{"verdict": "KEEP", "reason": "ok"}'),
                    prompt_version=pp.VISION_PROMPT_VERSION,
                )
            finally:
                pp.SHADOW_LOG_DIR = orig_dir

            record = _read_shadow_record(tmp, "image_validation")

        assert record["prompt_version"] == "vision_verdict_v3"
        assert record["pipeline_stage"] == "image_validation"

    def test_api_failure_still_logs_prompt_version(self):
        """Even on API failure, prompt_version is captured in the error record."""
        import photo_pipeline as pp

        with tempfile.TemporaryDirectory() as tmp:
            orig_dir = pp.SHADOW_LOG_DIR
            pp.SHADOW_LOG_DIR = Path(tmp)
            try:
                with pytest.raises(RuntimeError, match="Simulated"):
                    pp.call_gpt(
                        task_type="price_extraction",
                        pn="TEST-PN",
                        brand="Honeywell",
                        messages=[{"role": "user", "content": "test"}],
                        model="mock-model",
                        adapter=_FailingAdapter(),
                        prompt_version=pp.PRICE_EXTRACTION_PROMPT_VERSION,
                    )
            finally:
                pp.SHADOW_LOG_DIR = orig_dir

            record = _read_shadow_record(tmp, "price_extraction")

        assert record["prompt_version"] == "price_extraction_v11"
        assert record["response_raw"] is None  # failure path
        assert record["pipeline_stage"] == "price_extraction"

    def test_omitted_prompt_version_stays_none(self):
        """Backward compat: callers that don't pass prompt_version get None."""
        import photo_pipeline as pp

        with tempfile.TemporaryDirectory() as tmp:
            orig_dir = pp.SHADOW_LOG_DIR
            pp.SHADOW_LOG_DIR = Path(tmp)
            try:
                pp.call_gpt(
                    task_type="price_extraction",
                    pn="TEST-PN",
                    brand="Honeywell",
                    messages=[{"role": "user", "content": "test"}],
                    model="mock-model",
                    adapter=_MockAdapter(),
                    # no prompt_version kwarg
                )
            finally:
                pp.SHADOW_LOG_DIR = orig_dir

            record = _read_shadow_record(tmp, "price_extraction")

        assert record["prompt_version"] is None


class TestPromptVersionConstants:
    """Version constants exist and are non-empty strings."""

    def test_price_extraction_version_defined(self):
        import photo_pipeline as pp
        assert isinstance(pp.PRICE_EXTRACTION_PROMPT_VERSION, str)
        assert len(pp.PRICE_EXTRACTION_PROMPT_VERSION) > 0
        assert pp.PRICE_EXTRACTION_PROMPT_VERSION.startswith("price_extraction_")

    def test_vision_version_defined(self):
        import photo_pipeline as pp
        assert isinstance(pp.VISION_PROMPT_VERSION, str)
        assert len(pp.VISION_PROMPT_VERSION) > 0
        assert pp.VISION_PROMPT_VERSION.startswith("vision_verdict_")

    def test_changing_version_changes_record(self):
        """If version constant is changed, emitted record reflects it."""
        import photo_pipeline as pp

        with tempfile.TemporaryDirectory() as tmp:
            orig_dir = pp.SHADOW_LOG_DIR
            pp.SHADOW_LOG_DIR = Path(tmp)
            try:
                pp.call_gpt(
                    task_type="price_extraction",
                    pn="TEST-PN",
                    brand="B",
                    messages=[{"role": "user", "content": "t"}],
                    model="m",
                    adapter=_MockAdapter(),
                    prompt_version="price_extraction_v99_experimental",
                )
            finally:
                pp.SHADOW_LOG_DIR = orig_dir

            record = _read_shadow_record(tmp, "price_extraction")

        assert record["prompt_version"] == "price_extraction_v99_experimental"


class TestExporterV2Fields:
    """training_dataset_export passes through v2 fields from shadow_log."""

    def test_price_export_includes_prompt_version(self):
        from training_dataset_export import export_price_extraction_dataset

        with tempfile.TemporaryDirectory() as tmp:
            month = datetime.datetime.utcnow().strftime("%Y-%m")
            path = Path(tmp) / f"price_extraction_{month}.jsonl"
            record = {
                "pn": "PN1", "brand": "B",
                "prompt": "p", "response_raw": '{"pn_found": true}',
                "response_parsed": {"pn_found": True, "pn_exact_confirmed": True},
                "parse_success": True,
                "model": "m", "model_resolved": "m-v1",
                "prompt_version": "price_extraction_v11",
                "pipeline_stage": "price_extraction",
                "ts": "2026-04-10T00:00:00Z",
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            dataset = export_price_extraction_dataset(Path(tmp))

        assert len(dataset) == 1
        assert dataset[0]["prompt_version"] == "price_extraction_v11"
        assert dataset[0]["model_resolved"] == "m-v1"
        assert dataset[0]["pipeline_stage"] == "price_extraction"

    def test_photo_export_includes_prompt_version(self):
        from training_dataset_export import export_photo_verdict_dataset

        with tempfile.TemporaryDirectory() as tmp:
            month = datetime.datetime.utcnow().strftime("%Y-%m")
            path = Path(tmp) / f"image_validation_{month}.jsonl"
            record = {
                "pn": "PN1", "brand": "B",
                "prompt": "p",
                "response_raw": '{"verdict": "KEEP", "reason": "ok"}',
                "response_parsed": {"verdict": "KEEP", "reason": "ok"},
                "model": "m", "model_resolved": "m-v1",
                "prompt_version": "vision_verdict_v3",
                "pipeline_stage": "image_validation",
                "ts": "2026-04-10T00:00:00Z",
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            dataset = export_photo_verdict_dataset(Path(tmp))

        assert len(dataset) == 1
        assert dataset[0]["prompt_version"] == "vision_verdict_v3"
        assert dataset[0]["model_resolved"] == "m-v1"
        assert dataset[0]["pipeline_stage"] == "image_validation"

    def test_export_handles_old_records_without_v2_fields(self):
        """Old records without v2 fields export gracefully with None/empty."""
        from training_dataset_export import export_price_extraction_dataset

        with tempfile.TemporaryDirectory() as tmp:
            month = datetime.datetime.utcnow().strftime("%Y-%m")
            path = Path(tmp) / f"price_extraction_{month}.jsonl"
            record = {
                "pn": "PN1", "brand": "B",
                "prompt": "p", "response_raw": '{"pn_found": true}',
                "response_parsed": {"pn_found": True, "pn_exact_confirmed": True},
                "parse_success": True,
                "model": "m",
                "ts": "2026-04-10T00:00:00Z",
                # NO prompt_version, model_resolved, pipeline_stage
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            dataset = export_price_extraction_dataset(Path(tmp))

        assert len(dataset) == 1
        assert dataset[0]["prompt_version"] is None
        assert dataset[0]["model_resolved"] == ""
        assert dataset[0]["pipeline_stage"] == ""
