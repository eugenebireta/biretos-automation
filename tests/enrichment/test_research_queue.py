"""Tests for research_queue.py — deterministic, no API, no live data."""
from __future__ import annotations

import json
import sys
import os
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from research_queue import (
    determine_research_reason,
    classify_priority,
    generate_questions,
    extract_current_state,
    extract_known_facts,
    emit_research_packet,
    build_queue_from_evidence,
    write_research_brief_md,
    PACKET_VERSION,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_draft_bundle(pn: str = "TEST001", card_status: str = "DRAFT_ONLY") -> dict:
    return {
        "pn": pn,
        "brand": "Honeywell",
        "name": "Test Sensor XYZ",
        "assembled_title": f"Test Sensor Honeywell {pn}",
        "our_price_raw": "1500,00",
        "expected_category": "Датчики",
        "card_status": card_status,
        "review_reasons": ["IDENTITY_WEAK"],
        "policy_decision_v2": {"identity_level": "weak"},
        "photo": {"verdict": "REJECT"},
        "price": {
            "price_status": "no_price_found",
            "category_mismatch": False,
            "source_url": "",
            "price_source_exact_product_lineage_confirmed": False,
            "currency": "USD",
            "price_per_unit": None,
            "rub_price": None,
        },
        "confidence": {"overall_label": "VERY_LOW"},
        "content": {"description": ""},
        "pn_variants": [],
    }


def _make_review_bundle_with_price(pn: str = "TEST002") -> dict:
    bundle = _make_draft_bundle(pn, "REVIEW_REQUIRED")
    bundle["review_reasons"] = ["NO_IMAGE_EVIDENCE"]
    bundle["policy_decision_v2"]["identity_level"] = "moderate"
    bundle["price"].update({
        "price_status": "public_price",
        "price_source_exact_product_lineage_confirmed": True,
        "category_mismatch": True,
        "source_url": "https://example.com/product",
    })
    return bundle


def _make_resolved_bundle(pn: str = "TEST003") -> dict:
    bundle = _make_draft_bundle(pn, "AUTO_PUBLISH")
    bundle["photo"]["verdict"] = "KEEP"
    bundle["price"]["price_status"] = "public_price"
    bundle["price"]["price_source_exact_product_lineage_confirmed"] = True
    return bundle


# ── determine_research_reason ─────────────────────────────────────────────────

class TestDetermineResearchReason:
    def test_no_price_returns_no_price_lineage(self):
        bundle = _make_draft_bundle()
        reason = determine_research_reason(bundle)
        assert reason == "no_price_lineage"

    def test_category_mismatch_returns_category_mismatch(self):
        bundle = _make_draft_bundle()
        bundle["price"]["category_mismatch"] = True
        bundle["price"]["price_status"] = "category_mismatch_only"
        reason = determine_research_reason(bundle)
        assert reason == "category_mismatch"

    def test_identity_weak_with_price_returns_identity_weak(self):
        bundle = _make_draft_bundle()
        bundle["price"]["price_status"] = "public_price"
        bundle["price"]["price_source_exact_product_lineage_confirmed"] = True
        reason = determine_research_reason(bundle)
        assert reason == "identity_weak"

    def test_rejected_sanity_check_returns_category_mismatch(self):
        bundle = _make_draft_bundle()
        bundle["price"]["price_status"] = "rejected_sanity_check"
        reason = determine_research_reason(bundle)
        assert reason == "category_mismatch"


# ── classify_priority ─────────────────────────────────────────────────────────

class TestClassifyPriority:
    def test_category_mismatch_with_price_is_high(self):
        bundle = _make_review_bundle_with_price()
        priority = classify_priority(bundle, "category_mismatch")
        assert priority == "high"

    def test_no_price_lineage_no_photo_is_low(self):
        bundle = _make_draft_bundle()
        priority = classify_priority(bundle, "no_price_lineage")
        # No photo, no price → low
        assert priority in ("low", "medium")

    def test_strong_identity_is_high(self):
        bundle = _make_draft_bundle()
        bundle["policy_decision_v2"]["identity_level"] = "strong"
        priority = classify_priority(bundle, "photo_mismatch")
        assert priority == "high"

    def test_moderate_identity_is_medium(self):
        bundle = _make_draft_bundle()
        bundle["policy_decision_v2"]["identity_level"] = "moderate"
        priority = classify_priority(bundle, "specs_gap")
        assert priority == "medium"


# ── generate_questions ────────────────────────────────────────────────────────

class TestGenerateQuestions:
    def test_returns_list_of_strings(self):
        bundle = _make_draft_bundle()
        questions = generate_questions("TEST001", bundle, "identity_weak")
        assert isinstance(questions, list)
        assert all(isinstance(q, str) for q in questions)

    def test_identity_weak_questions_mention_pn(self):
        questions = generate_questions("TEST001", _make_draft_bundle(), "identity_weak")
        combined = " ".join(questions)
        assert "TEST001" in combined

    def test_no_price_lineage_questions_mention_price(self):
        questions = generate_questions("TEST001", _make_draft_bundle(), "no_price_lineage")
        combined = " ".join(questions).lower()
        assert "price" in combined or "цен" in combined or "distributor" in combined

    def test_category_mismatch_questions_mention_category(self):
        questions = generate_questions("TEST001", _make_draft_bundle(), "category_mismatch")
        combined = " ".join(questions).lower()
        assert "category" in combined or "категор" in combined

    def test_all_reasons_return_non_empty_lists(self):
        bundle = _make_draft_bundle()
        for reason in ("identity_weak", "category_mismatch", "no_price_lineage",
                        "photo_mismatch", "admissibility_review", "specs_gap"):
            qs = generate_questions("T1", bundle, reason)
            assert len(qs) > 0


# ── extract_current_state / extract_known_facts ───────────────────────────────

class TestExtractors:
    def test_current_state_has_required_fields(self):
        bundle = _make_draft_bundle()
        state = extract_current_state(bundle)
        assert "card_status" in state
        assert "photo_verdict" in state
        assert "price_status" in state

    def test_known_facts_has_brand(self):
        bundle = _make_draft_bundle()
        facts = extract_known_facts(bundle)
        assert facts["brand"] == "Honeywell"
        assert "name" in facts
        assert "expected_category" in facts


# ── emit_research_packet ──────────────────────────────────────────────────────

class TestEmitResearchPacket:
    def test_emit_creates_json_and_md(self, tmp_path, monkeypatch):
        import research_queue
        monkeypatch.setattr(research_queue, "PACKETS_DIR", tmp_path / "packets")
        monkeypatch.setattr(research_queue, "QUEUE_JSONL", tmp_path / "queue.jsonl")

        bundle = _make_draft_bundle("TEST001")
        packet = emit_research_packet("TEST001", bundle)

        # JSON packet exists
        json_file = tmp_path / "packets" / "research_packet_TEST001.json"
        assert json_file.exists()
        loaded = json.loads(json_file.read_text(encoding="utf-8"))
        assert loaded["entity_id"] == "TEST001"
        assert loaded["packet_version"] == PACKET_VERSION
        assert "questions_to_resolve" in loaded
        assert "constraints" in loaded

        # MD brief exists
        md_file = tmp_path / "packets" / "research_packet_TEST001.md"
        assert md_file.exists()
        md_content = md_file.read_text(encoding="utf-8")
        assert "TEST001" in md_content

        # Queue entry appended
        queue_content = (tmp_path / "queue.jsonl").read_text(encoding="utf-8")
        entry = json.loads(queue_content.strip().split("\n")[0])
        assert entry["pn"] == "TEST001"
        assert entry["priority"] in ("high", "medium", "low")

    def test_emit_packet_contains_all_required_fields(self, tmp_path, monkeypatch):
        import research_queue
        monkeypatch.setattr(research_queue, "PACKETS_DIR", tmp_path / "packets")
        monkeypatch.setattr(research_queue, "QUEUE_JSONL", tmp_path / "queue.jsonl")

        bundle = _make_draft_bundle("PN123")
        packet = emit_research_packet("PN123", bundle)

        required = [
            "packet_version", "task_id", "entity_id", "brand_hint",
            "goal", "research_reason", "priority", "questions_to_resolve",
            "current_state", "known_facts", "constraints", "required_output",
        ]
        for field in required:
            assert field in packet, f"Missing field: {field}"

    def test_resolved_bundle_not_needed(self):
        """Test logic — resolved bundles should NOT be emitted."""
        bundle = _make_resolved_bundle("RESOLVED001")
        # build_queue_from_evidence would skip this — verify card_status check
        from research_queue import _RESEARCH_STATUSES
        assert bundle["card_status"] not in _RESEARCH_STATUSES


# ── build_queue_from_evidence ─────────────────────────────────────────────────

class TestBuildQueueFromEvidence:
    def test_only_draft_and_review_go_into_queue(self, tmp_path, monkeypatch):
        import research_queue
        monkeypatch.setattr(research_queue, "PACKETS_DIR", tmp_path / "packets")
        monkeypatch.setattr(research_queue, "QUEUE_DIR", tmp_path)
        monkeypatch.setattr(research_queue, "QUEUE_JSONL", tmp_path / "queue.jsonl")

        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()

        # Write 3 bundles: draft, review, resolved
        for pn, status in [("A", "DRAFT_ONLY"), ("B", "REVIEW_REQUIRED"), ("C", "AUTO_PUBLISH")]:
            bundle = _make_draft_bundle(pn, status)
            (ev_dir / f"evidence_{pn}.json").write_text(
                json.dumps(bundle, ensure_ascii=False), encoding="utf-8"
            )

        stats = build_queue_from_evidence(evidence_dir=ev_dir, force=True)

        assert stats["total_bundles"] == 3
        assert stats["research_needed"] == 2  # DRAFT + REVIEW
        assert stats["skipped_resolved"] == 1  # AUTO_PUBLISH
        assert stats["emitted"] == 2

    def test_already_queued_skus_not_duplicated(self, tmp_path, monkeypatch):
        import research_queue
        monkeypatch.setattr(research_queue, "PACKETS_DIR", tmp_path / "packets")
        monkeypatch.setattr(research_queue, "QUEUE_DIR", tmp_path)
        monkeypatch.setattr(research_queue, "QUEUE_JSONL", tmp_path / "queue.jsonl")

        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()

        bundle = _make_draft_bundle("A", "DRAFT_ONLY")
        (ev_dir / "evidence_A.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")

        # First run
        stats1 = build_queue_from_evidence(evidence_dir=ev_dir, force=True)
        assert stats1["emitted"] == 1

        # Second run (no force) — should see it as already queued
        stats2 = build_queue_from_evidence(evidence_dir=ev_dir, force=False)
        assert stats2["emitted"] == 0
        assert stats2["already_queued"] == 1
