"""Tests for research_runner.py — deterministic, no live API calls."""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from research_runner import (
    MockResearchProvider,
    build_research_prompt,
    parse_research_response,
    run_research_for_packet,
    run_batch_research,
    audit_research_results,
    prepare_merge_candidates,
    RESULT_VERSION,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

_SAMPLE_PACKET = {
    "packet_version": "v1",
    "task_id": "enrichment_research_TEST001",
    "entity_id": "TEST001",
    "brand_hint": "Honeywell",
    "goal": "Close enrichment gaps for TEST001",
    "research_reason": "identity_weak",
    "priority": "medium",
    "questions_to_resolve": [
        "Confirm identity for Honeywell TEST001",
        "Find market price",
    ],
    "current_state": {"card_status": "DRAFT_ONLY"},
    "known_facts": {
        "brand": "Honeywell",
        "name": "Test Sensor",
        "expected_category": "Датчики",
        "our_price_raw": "1500,00",
    },
    "constraints": ["Use public web evidence only"],
    "required_output": {"identity": True, "title_ru": True},
    "generated_at": "2026-04-08T00:00:00Z",
}

_GOOD_RESPONSE = json.dumps({
    "identity_confirmed": True,
    "brand": "Honeywell",
    "title_ru": "Датчик давления Honeywell TEST001",
    "description_ru": "Промышленный датчик давления.",
    "category_suggestion": "Датчики давления",
    "price_assessment": "no_public_price",
    "price_evidence": "Нет публичных цен.",
    "photo_assessment": "not_found",
    "specs_assessment": "partial",
    "key_findings": ["Found on manufacturer site"],
    "ambiguities": [],
    "sources": [{"url": "https://example.com", "type": "manufacturer", "supports": ["identity"]}],
    "confidence": "medium",
    "confidence_notes": "Identity confirmed via manufacturer site.",
}, ensure_ascii=False)


# ── MockResearchProvider ──────────────────────────────────────────────────────

class TestMockResearchProvider:
    def test_returns_valid_json(self):
        provider = MockResearchProvider()
        response, model, cost = provider.call("test prompt")
        assert model == "mock"
        assert cost == 0.0
        parsed = json.loads(response)
        assert "identity_confirmed" in parsed

    def test_custom_response(self):
        custom = '{"confidence": "high", "title_ru": "Custom"}'
        provider = MockResearchProvider(fixed_response=custom)
        response, _, _ = provider.call("any")
        assert json.loads(response)["confidence"] == "high"


# ── build_research_prompt ─────────────────────────────────────────────────────

class TestBuildResearchPrompt:
    def test_prompt_contains_pn(self):
        prompt = build_research_prompt(_SAMPLE_PACKET)
        assert "TEST001" in prompt

    def test_prompt_contains_brand(self):
        prompt = build_research_prompt(_SAMPLE_PACKET)
        assert "Honeywell" in prompt

    def test_prompt_contains_questions(self):
        prompt = build_research_prompt(_SAMPLE_PACKET)
        assert "Confirm identity" in prompt

    def test_prompt_contains_json_format_instructions(self):
        prompt = build_research_prompt(_SAMPLE_PACKET)
        assert "identity_confirmed" in prompt
        assert "title_ru" in prompt
        assert "confidence" in prompt

    def test_prompt_is_string(self):
        prompt = build_research_prompt(_SAMPLE_PACKET)
        assert isinstance(prompt, str)
        assert len(prompt) > 200


# ── parse_research_response ───────────────────────────────────────────────────

class TestParseResearchResponse:
    def test_valid_json_response(self):
        result = parse_research_response(_GOOD_RESPONSE, _SAMPLE_PACKET)
        assert result["result_version"] == RESULT_VERSION
        assert result["entity_id"] == "TEST001"
        assert result["confidence"] == "medium"
        assert result["parse_error"] == ""
        rec = result["final_recommendation"]
        assert rec["title_ru"] == "Датчик давления Honeywell TEST001"

    def test_response_with_no_json_block(self):
        result = parse_research_response("Just plain text, no JSON here.", _SAMPLE_PACKET)
        assert result["parse_error"] != ""
        assert result["entity_id"] == "TEST001"

    def test_response_with_invalid_json(self):
        result = parse_research_response("{ invalid json {{", _SAMPLE_PACKET)
        assert result["parse_error"] != ""

    def test_response_wrapped_in_text(self):
        wrapped = f"Here is my analysis:\n{_GOOD_RESPONSE}\nHope this helps."
        result = parse_research_response(wrapped, _SAMPLE_PACKET)
        # Should extract JSON from within text
        assert result["confidence"] == "medium"

    def test_result_has_all_required_fields(self):
        result = parse_research_response(_GOOD_RESPONSE, _SAMPLE_PACKET)
        required = ["result_version", "task_id", "entity_id", "research_reason",
                    "final_recommendation", "confidence", "timestamp", "provider"]
        for field in required:
            assert field in result, f"Missing: {field}"


# ── run_research_for_packet ───────────────────────────────────────────────────

class TestRunResearchForPacket:
    def test_creates_result_file(self, tmp_path, monkeypatch):
        import research_runner
        monkeypatch.setattr(research_runner, "RESULTS_DIR", tmp_path / "results")
        monkeypatch.setattr(research_runner, "DAILY_BUDGET_USD", 1000.0)
        monkeypatch.setattr(research_runner, "BUDGET_FILE", tmp_path / "budget.json")

        # Write packet to tmp dir
        packet_path = tmp_path / "research_packet_TEST001.json"
        packet_path.write_text(json.dumps(_SAMPLE_PACKET, ensure_ascii=False), encoding="utf-8")

        provider = MockResearchProvider(fixed_response=_GOOD_RESPONSE)
        result = run_research_for_packet(str(packet_path), provider=provider)

        assert result["entity_id"] == "TEST001"
        result_file = tmp_path / "results" / "result_TEST001.json"
        assert result_file.exists()
        loaded = json.loads(result_file.read_text(encoding="utf-8"))
        assert loaded["entity_id"] == "TEST001"

    def test_result_format_is_correct(self, tmp_path, monkeypatch):
        import research_runner
        monkeypatch.setattr(research_runner, "RESULTS_DIR", tmp_path / "results")
        monkeypatch.setattr(research_runner, "DAILY_BUDGET_USD", 1000.0)
        monkeypatch.setattr(research_runner, "BUDGET_FILE", tmp_path / "budget.json")

        packet_path = tmp_path / "research_packet_TEST001.json"
        packet_path.write_text(json.dumps(_SAMPLE_PACKET, ensure_ascii=False), encoding="utf-8")

        provider = MockResearchProvider(fixed_response=_GOOD_RESPONSE)
        result = run_research_for_packet(str(packet_path), provider=provider)

        assert result["result_version"] == RESULT_VERSION
        assert "final_recommendation" in result
        assert "timestamp" in result


# ── run_batch_research ────────────────────────────────────────────────────────

class TestRunBatchResearch:
    def _write_queue(self, tmp_path: Path, entries: list[dict]) -> Path:
        queue_file = tmp_path / "queue.jsonl"
        with open(queue_file, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return queue_file

    def _write_packet(self, tmp_path: Path, pn: str) -> str:
        packet = {**_SAMPLE_PACKET, "entity_id": pn, "task_id": f"enrichment_research_{pn}"}
        p = tmp_path / "packets" / f"research_packet_{pn}.json"
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
        return str(p)

    def test_processes_high_priority_items(self, tmp_path, monkeypatch):
        import research_runner
        monkeypatch.setattr(research_runner, "RESULTS_DIR", tmp_path / "results")
        monkeypatch.setattr(research_runner, "DAILY_BUDGET_USD", 1000.0)
        monkeypatch.setattr(research_runner, "BUDGET_FILE", tmp_path / "budget.json")

        packet_path = self._write_packet(tmp_path, "HIGH001")
        queue = self._write_queue(tmp_path, [
            {"pn": "HIGH001", "priority": "high", "packet_path": packet_path},
        ])

        provider = MockResearchProvider(fixed_response=_GOOD_RESPONSE)
        stats = run_batch_research(
            queue_path=queue,
            max_items=10,
            priority_filter="high",
            provider=provider,
        )
        assert stats["success"] == 1
        assert stats["total"] == 1
        assert not stats["budget_stop"]

    def test_skips_medium_when_high_filter(self, tmp_path, monkeypatch):
        import research_runner
        monkeypatch.setattr(research_runner, "RESULTS_DIR", tmp_path / "results")
        monkeypatch.setattr(research_runner, "DAILY_BUDGET_USD", 1000.0)
        monkeypatch.setattr(research_runner, "BUDGET_FILE", tmp_path / "budget.json")

        queue = self._write_queue(tmp_path, [
            {"pn": "MED001", "priority": "medium", "packet_path": "/nonexistent"},
        ])
        provider = MockResearchProvider()
        stats = run_batch_research(
            queue_path=queue, max_items=10, priority_filter="high", provider=provider
        )
        assert stats["total"] == 0  # filtered out

    def test_budget_stop_halts_batch(self, tmp_path, monkeypatch):
        import research_runner
        monkeypatch.setattr(research_runner, "RESULTS_DIR", tmp_path / "results")
        monkeypatch.setattr(research_runner, "DAILY_BUDGET_USD", 0.0)  # zero budget
        monkeypatch.setattr(research_runner, "BUDGET_FILE", tmp_path / "budget.json")

        packet_path = self._write_packet(tmp_path, "P1")
        queue = self._write_queue(tmp_path, [
            {"pn": "P1", "priority": "high", "packet_path": packet_path},
        ])
        provider = MockResearchProvider()
        stats = run_batch_research(queue_path=queue, max_items=5, provider=provider)
        assert stats["budget_stop"] is True

    def test_returns_stats_dict(self, tmp_path, monkeypatch):
        import research_runner
        monkeypatch.setattr(research_runner, "DAILY_BUDGET_USD", 1000.0)
        monkeypatch.setattr(research_runner, "BUDGET_FILE", tmp_path / "budget.json")

        queue = tmp_path / "empty_queue.jsonl"
        queue.write_text("", encoding="utf-8")
        stats = run_batch_research(queue_path=queue, provider=MockResearchProvider())
        assert "total" in stats
        assert "success" in stats
        assert "budget_stop" in stats


# ── audit_research_results ────────────────────────────────────────────────────

class TestAuditResearchResults:
    def test_counts_confidence_levels(self, tmp_path, monkeypatch):
        import research_runner
        monkeypatch.setattr(research_runner, "RESULTS_DIR", tmp_path)

        for pn, conf in [("A", "high"), ("B", "medium"), ("C", "low")]:
            r = {
                "entity_id": pn, "confidence": conf,
                "result_version": "v1", "parse_error": "",
                "final_recommendation": {"title_ru": "X", "identity_confirmed": True},
                "sources": [{"url": "http://example.com"}],
            }
            (tmp_path / f"result_{pn}.json").write_text(
                json.dumps(r, ensure_ascii=False), encoding="utf-8"
            )

        audit = audit_research_results(results_dir=tmp_path)
        assert audit["total_results"] == 3
        assert audit["high_confidence"] == 1
        assert audit["medium_confidence"] == 1
        assert audit["low_confidence"] == 1

    def test_empty_dir_returns_zero(self, tmp_path):
        audit = audit_research_results(results_dir=tmp_path)
        assert audit["total_results"] == 0


# ── prepare_merge_candidates ──────────────────────────────────────────────────

class TestPrepareMergeCandidates:
    def _write_result(self, path: Path, pn: str, conf: str, title: str, identity: bool) -> None:
        r = {
            "entity_id": pn,
            "confidence": conf,
            "result_version": "v1",
            "parse_error": "",
            "final_recommendation": {
                "identity_confirmed": identity,
                "title_ru": title,
                "category_suggestion": "Test category",
                "price_assessment": "no_public_price",
            },
            "sources": [{"url": "https://example.com"}],
            "research_reason": "identity_weak",
        }
        (path / f"result_{pn}.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")

    def test_high_confidence_complete_is_candidate(self, tmp_path, monkeypatch):
        import research_runner
        monkeypatch.setattr(research_runner, "RESULTS_DIR", tmp_path)

        self._write_result(tmp_path, "A", "high", "Title A", True)
        candidates = prepare_merge_candidates(results_dir=tmp_path)
        assert len(candidates) == 1
        assert candidates[0]["pn"] == "A"

    def test_medium_confidence_not_candidate(self, tmp_path, monkeypatch):
        import research_runner
        monkeypatch.setattr(research_runner, "RESULTS_DIR", tmp_path)

        self._write_result(tmp_path, "B", "medium", "Title B", True)
        candidates = prepare_merge_candidates(results_dir=tmp_path)
        assert len(candidates) == 0

    def test_high_confidence_no_identity_not_candidate(self, tmp_path, monkeypatch):
        import research_runner
        monkeypatch.setattr(research_runner, "RESULTS_DIR", tmp_path)

        self._write_result(tmp_path, "C", "high", "Title C", False)
        candidates = prepare_merge_candidates(results_dir=tmp_path)
        assert len(candidates) == 0
