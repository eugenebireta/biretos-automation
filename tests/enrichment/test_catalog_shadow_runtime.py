"""Tests for bounded sanity shadow execution runtime."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

import catalog_shadow_runtime as csr
import photo_pipeline
from export_pipeline import build_evidence_bundle
from run_phase_a_v2_sanity_batch import build_report


def _profile(**limit_overrides):
    return {
        "schema_version": "catalog_shadow_execution_profile_v1",
        "profile_name": "test_shadow",
        "responses_only_verifier": True,
        "limits": {
            "MAX_SHADOW_SKUS": 2,
            "MAX_VERIFIER_CALLS_PER_RUN": 1,
            "MAX_VERIFIER_CALLS_PER_SKU": 1,
            "MAX_RUN_WALLCLOCK_SEC": 10,
            "MAX_CONSECUTIVE_TIMEOUTS": 2,
            "MAX_EXTERNAL_SOURCE_ATTEMPTS_PER_SKU": 2,
            "MAX_DATASHEET_ATTEMPTS_PER_SKU": 1,
            **limit_overrides,
        },
        "weak_marketplace_policy": {
            "allow_weak_marketplaces": False,
            "blocked_domain_keywords": ["ebay.", "manualslib."],
        },
        "execution_intent": {
            "audit_first": True,
            "coverage_maximization": False,
            "fast_failure": True,
            "partial_report_on_stop": True,
        },
    }


def _bundle() -> dict:
    return build_evidence_bundle(
        pn="00020211",
        name="Temperature Sensor",
        brand="Honeywell",
        photo_result={},
        vision_verdict={"verdict": "NO_PHOTO", "reason": "missing"},
        price_result={"price_status": "no_price_found"},
        datasheet_result={"datasheet_status": "skipped"},
        run_ts="2026-03-27T00:00:00Z",
    )


def test_budget_stop_after_max_shadow_skus(monkeypatch):
    monkeypatch.setattr(csr, "load_shadow_profile", lambda: _profile(MAX_SHADOW_SKUS=1))
    csr.activate_shadow_runtime(run_manifest_id="batch-1", planned_skus=3)
    csr.record_completed_sku("00020211")
    allowed, reason = csr.allow_next_sku("00020212")
    assert allowed is False
    assert reason == "max_shadow_skus_reached:1"
    assert csr.get_shadow_runtime_summary()["early_stop"] is True


def test_timeout_stop_sets_early_stop(monkeypatch):
    monkeypatch.setattr(csr, "load_shadow_profile", lambda: _profile(MAX_CONSECUTIVE_TIMEOUTS=2))
    csr.activate_shadow_runtime(run_manifest_id="batch-1", planned_skus=3)
    csr.record_source_failure("https://a.example/item", timed_out=True, channel="external_source")
    csr.record_source_failure("https://b.example/item", timed_out=True, channel="datasheet")
    summary = csr.get_shadow_runtime_summary()
    assert summary["early_stop"] is True
    assert summary["reason_for_early_stop"] == "max_consecutive_timeouts_reached:2"
    assert summary["timeout_count"] == 2


def test_wallclock_budget_stops_run(monkeypatch):
    monkeypatch.setattr(csr, "load_shadow_profile", lambda: _profile(MAX_RUN_WALLCLOCK_SEC=1))
    csr.activate_shadow_runtime(run_manifest_id="batch-1", planned_skus=3)
    csr._state["start_monotonic"] = 1.0
    monkeypatch.setattr(csr.time, "monotonic", lambda: 5.0)
    assert csr.check_wallclock_budget() is True
    assert csr.get_shadow_runtime_summary()["reason_for_early_stop"] == "wallclock_budget_reached:1"


def test_weak_marketplace_disabled_in_shadow_mode(monkeypatch):
    monkeypatch.setattr(csr, "load_shadow_profile", lambda: _profile())
    csr.activate_shadow_runtime(run_manifest_id="batch-1", planned_skus=3)
    assert csr.allow_external_source_candidate("https://www.ebay.com/itm/123") is False
    allowed, reason = csr.allow_external_source_attempt("00020211", "https://www.ebay.com/itm/123")
    assert allowed is False
    assert reason == "weak_marketplace_disabled"


def test_verifier_budget_counts_responses_only(monkeypatch):
    monkeypatch.setattr(csr, "load_shadow_profile", lambda: _profile(MAX_VERIFIER_CALLS_PER_RUN=1))
    csr.activate_shadow_runtime(run_manifest_id="batch-1", planned_skus=3)
    allowed, reason = csr.allow_verifier_call("00020211")
    assert allowed is True
    assert reason == ""
    csr.record_verifier_call("00020211", latency_sec=0.5, timed_out=False, success=True)
    allowed_next, reason_next = csr.allow_verifier_call("00020212")
    assert allowed_next is False
    assert reason_next == "max_verifier_calls_per_run_reached:1"
    summary = csr.get_shadow_runtime_summary()
    assert summary["responses_calls"] == 1
    assert summary["chat_completions_calls_verifier"] == 0


def test_shadow_mode_skips_google_ru_b2b_search_attempt(monkeypatch):
    calls: list[dict] = []

    class DummySearch:
        def __init__(self, params):
            calls.append(dict(params))

        def get_dict(self):
            return {"organic_results": []}

    monkeypatch.setattr(csr, "load_shadow_profile", lambda: _profile())
    csr.activate_shadow_runtime(run_manifest_id="batch-1", planned_skus=3)
    monkeypatch.setattr(photo_pipeline, "GoogleSearch", DummySearch)
    monkeypatch.setattr(photo_pipeline.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(photo_pipeline, "serpapi_key", "test-serpapi-key")
    photo_pipeline.step2_us_price("00020211", "Temperature Sensor")
    assert len(calls) == 2
    assert all(not (call.get("gl") == "ru" and call.get("hl") == "ru") for call in calls)


def test_partial_report_generation_on_early_stop(tmp_path: Path):
    manifest = {
        "batch_id": "phase_a_v2_sanity_test",
        "batch_size": 1,
        "selection_mode": "deterministic_head_1_prior_limited_run_alignment",
        "coverage_by_case_type": {"numeric": 1},
        "coverage_gaps": [],
    }
    paths = {
        "manifest_file": tmp_path / "batch_manifest.json",
        "report_file": tmp_path / "sanity_audit_report.json",
        "sidecar_file": tmp_path / "candidate_sidecar.jsonl",
        "stdout_first": tmp_path / "run_first_stdout.log",
        "stdout_resume": tmp_path / "run_resume_stdout.log",
        "checkpoint_file": tmp_path / "checkpoint.json",
        "evidence_dir": tmp_path / "evidence",
        "export_dir": tmp_path / "export",
    }
    paths["evidence_dir"].mkdir()
    paths["export_dir"].mkdir()
    paths["checkpoint_file"].write_text(json.dumps({"00020211": {"pn": "00020211"}}), encoding="utf-8")
    bundle = _bundle()
    first_shadow_summary = {
        "profile_name": "test_shadow",
        "active": True,
        "completed_skus": ["00020211"],
        "skipped_due_to_budget": [{"pn_primary": "00020212", "reason": "wallclock_budget_reached:1"}],
        "timed_out_sources": [{"channel": "external_source", "source": "example.com"}],
        "verifier_calls_used": 1,
        "responses_calls": 1,
        "chat_completions_calls_verifier": 0,
        "timeout_count": 1,
        "per_source_failure_summary": {"example.com": 1},
        "reason_for_early_stop": "wallclock_budget_reached:1",
        "early_stop": True,
        "total_wall_clock_sec": 1.2,
        "avg_verifier_latency_sec": 0.4,
        "max_verifier_latency_sec": 0.4,
        "limits": _profile()["limits"],
        "responses_only_verifier": True,
        "run_manifest_id": "phase_a_v2_sanity_test",
        "planned_skus": 1,
    }
    report = build_report(
        manifest=manifest,
        paths=paths,
        bundles=[bundle],
        sidecar_rows=[],
        first_stdout="",
        resume_stdout="",
        first_shadow_summary=first_shadow_summary,
        resume_shadow_summary=None,
    )
    assert report["shadow_run_summary"]["first_run"]["early_stop"] is True
    assert report["shadow_run_summary"]["first_run"]["responses_calls"] == 1
    assert report["shadow_run_summary"]["first_run"]["chat_completions_calls_verifier"] == 0
    assert report["resume_evidence"]["resume_skipped_due_to_early_stop"] is True
