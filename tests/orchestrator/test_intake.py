"""
test_intake.py — deterministic unit tests for orchestrator/intake.py

All tests use tmp_path fixtures and in-memory JSON — no live files, no subprocess.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Follow project pattern: add orchestrator/ to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "orchestrator"))

import pytest
from intake import load, ContextBundle, _DNA_CONSTRAINTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _manifest(overrides: dict | None = None) -> dict:
    base = {
        "schema_version": "v1",
        "fsm_state": "ready",
        "current_sprint_goal": "Test sprint goal",
        "current_task_id": "TASK-001",
        "trace_id": "orch_20260406T120000Z_abc123",
        "attempt_count": 1,
        "last_verdict": None,
        "last_directive_hash": None,
        "pending_packet_id": None,
        "deadline_at": None,
        "default_option_id": None,
        "updated_at": "2026-04-06T12:00:00+00:00",
    }
    if overrides:
        base.update(overrides)
    return base


def _packet(overrides: dict | None = None) -> dict:
    base = {
        "schema_version": "v1",
        "trace_id": "orch_20260406T120000Z_abc123",
        "status": "completed",
        "changed_files": ["scripts/export_pipeline.py"],
        "diff_summary": "--- a/scripts/export_pipeline.py\n+++ new change",
        "diff_truncated": False,
        "test_results": {"passed": 10, "failed": 0, "skipped": 1},
        "affected_tiers": ["Tier-3"],
        "executor_notes": "All good",
        "questions": [],
        "blockers": [],
        "collected_at": "2026-04-06T12:01:00+00:00",
        "base_commit": "abc1234",
        "head_commit": "def5678",
    }
    if overrides:
        base.update(overrides)
    return base


def _verdict(overrides: dict | None = None) -> dict:
    base = {
        "schema_version": "v1",
        "trace_id": "orch_20260406T120000Z_abc123",
        "risk_assessment": "LOW",
        "governance_route": "none",
        "rationale": "Tier-3 only changes.",
        "next_step": "Continue",
        "scope": ["scripts/export_pipeline.py"],
        "issued_at": "2026-04-06T12:02:00+00:00",
    }
    if overrides:
        base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Basic load — all files present
# ---------------------------------------------------------------------------
class TestLoadFull:
    def test_returns_context_bundle(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet())
        _write_json(tmp_path / "verdict.json", _verdict())
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "verdict.json",
            config={},
        )
        assert isinstance(bundle, ContextBundle)

    def test_sprint_goal_loaded(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest({"current_sprint_goal": "My sprint"}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "absent.json",
            verdict_path=tmp_path / "absent2.json",
            config={},
        )
        assert bundle.sprint_goal == "My sprint"

    def test_task_id_loaded(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest({"current_task_id": "TASK-999"}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "x.json",
            verdict_path=tmp_path / "y.json",
            config={},
        )
        assert bundle.task_id == "TASK-999"

    def test_fsm_state_loaded(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest({"fsm_state": "awaiting_execution"}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "x.json",
            verdict_path=tmp_path / "y.json",
            config={},
        )
        assert bundle.fsm_state == "awaiting_execution"

    def test_packet_status_loaded(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet({"status": "partial"}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "x.json",
            config={},
        )
        assert bundle.last_status == "partial"

    def test_changed_files_loaded(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet({"changed_files": ["a.py", "b.py"]}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "x.json",
            config={},
        )
        assert bundle.last_changed_files == ["a.py", "b.py"]

    def test_verdict_risk_loaded(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet())
        _write_json(tmp_path / "verdict.json", _verdict({"risk_assessment": "SEMI"}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "verdict.json",
            config={},
        )
        assert bundle.last_verdict_risk == "SEMI"

    def test_verdict_route_loaded(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet())
        _write_json(tmp_path / "verdict.json", _verdict({"governance_route": "audit"}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "verdict.json",
            config={},
        )
        assert bundle.last_verdict_route == "audit"

    def test_dna_constraints_populated(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "x.json",
            verdict_path=tmp_path / "y.json",
            config={},
        )
        assert len(bundle.dna_constraints) == len(_DNA_CONSTRAINTS)
        assert all(isinstance(c, str) for c in bundle.dna_constraints)


# ---------------------------------------------------------------------------
# Soft failure — missing files produce warnings, not exceptions
# ---------------------------------------------------------------------------
class TestLoadSoftFailure:
    def test_missing_manifest_produces_warning(self, tmp_path):
        bundle = load(
            manifest_path=tmp_path / "missing.json",
            packet_path=tmp_path / "x.json",
            verdict_path=tmp_path / "y.json",
            config={},
        )
        assert any("manifest" in w.lower() for w in bundle.warnings)

    def test_missing_packet_no_exception(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        # packet does not exist — should not raise
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "missing_packet.json",
            verdict_path=tmp_path / "missing_verdict.json",
            config={},
        )
        assert bundle.last_status is None
        assert bundle.last_changed_files == []

    def test_invalid_json_manifest_produces_warning(self, tmp_path):
        bad = tmp_path / "manifest.json"
        bad.write_text("not json {{{", encoding="utf-8")
        bundle = load(
            manifest_path=bad,
            packet_path=tmp_path / "x.json",
            verdict_path=tmp_path / "y.json",
            config={},
        )
        assert any("manifest" in w.lower() for w in bundle.warnings)

    def test_invalid_json_packet_produces_warning(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        bad = tmp_path / "packet.json"
        bad.write_text("{{broken", encoding="utf-8")
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=bad,
            verdict_path=tmp_path / "y.json",
            config={},
        )
        assert any("packet" in w.lower() or "execution" in w.lower() for w in bundle.warnings)

    def test_missing_verdict_no_exception(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet())
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "missing.json",
            config={},
        )
        assert bundle.last_verdict_risk is None
        assert bundle.last_verdict_route is None


# ---------------------------------------------------------------------------
# Staleness warning — sprint_goal not updated in >N days
# ---------------------------------------------------------------------------
class TestStalenessWarning:
    def test_empty_sprint_goal_warns(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest({"current_sprint_goal": ""}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "x.json",
            verdict_path=tmp_path / "y.json",
            config={},
        )
        assert any("sprint_goal" in w.lower() or "empty" in w.lower() for w in bundle.warnings)

    def test_stale_sprint_goal_warns(self, tmp_path):
        # updated_at is far in the past
        _write_json(tmp_path / "manifest.json", _manifest({
            "current_sprint_goal": "Old goal",
            "updated_at": "2020-01-01T00:00:00+00:00",
        }))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "x.json",
            verdict_path=tmp_path / "y.json",
            config={"sprint_goal_staleness_warn_days": 7},
        )
        assert any("sprint_goal" in w.lower() or "stale" in w.lower() or "updated" in w.lower()
                   for w in bundle.warnings)

    def test_fresh_sprint_goal_no_staleness_warning(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest({
            "current_sprint_goal": "Current goal",
            "updated_at": "2026-04-06T12:00:00+00:00",
        }))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "x.json",
            verdict_path=tmp_path / "y.json",
            config={"sprint_goal_staleness_warn_days": 7},
        )
        staleness_warnings = [w for w in bundle.warnings
                              if "stale" in w.lower() or "not updated" in w.lower()]
        assert len(staleness_warnings) == 0


# ---------------------------------------------------------------------------
# Diff truncation
# ---------------------------------------------------------------------------
class TestDiffTruncation:
    def test_diff_not_truncated_when_short(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        short_diff = "small diff"
        _write_json(tmp_path / "packet.json", _packet({
            "diff_summary": short_diff,
            "diff_truncated": False,
        }))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "x.json",
            config={"diff_truncation_chars": 15000},
        )
        assert bundle.last_diff == short_diff
        assert bundle.last_diff_truncated is False

    def test_diff_truncated_when_exceeds_limit(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        long_diff = "x" * 200
        _write_json(tmp_path / "packet.json", _packet({
            "diff_summary": long_diff,
            "diff_truncated": False,
        }))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "x.json",
            config={"diff_truncation_chars": 100},
        )
        assert bundle.last_diff_truncated is True
        assert len(bundle.last_diff) <= 100 + len("\n[DIFF TRUNCATED]")
        assert "[DIFF TRUNCATED]" in bundle.last_diff

    def test_diff_already_truncated_flag_preserved(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet({
            "diff_summary": "small",
            "diff_truncated": True,
        }))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "x.json",
            config={},
        )
        assert bundle.last_diff_truncated is True


# ---------------------------------------------------------------------------
# to_advisor_prompt_context — rendering
# ---------------------------------------------------------------------------
class TestToAdvisorPromptContext:
    def test_renders_sprint_goal(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest({"current_sprint_goal": "Ship R1"}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "x.json",
            verdict_path=tmp_path / "y.json",
            config={},
        )
        ctx = bundle.to_advisor_prompt_context()
        assert "Ship R1" in ctx

    def test_renders_task_id(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest({"current_task_id": "TASK-42"}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "x.json",
            verdict_path=tmp_path / "y.json",
            config={},
        )
        ctx = bundle.to_advisor_prompt_context()
        assert "TASK-42" in ctx

    def test_renders_diff_section(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet({"diff_summary": "DIFF_CONTENT_HERE"}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "x.json",
            config={},
        )
        ctx = bundle.to_advisor_prompt_context()
        assert "DIFF_CONTENT_HERE" in ctx

    def test_renders_constraints(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "x.json",
            verdict_path=tmp_path / "y.json",
            config={},
        )
        ctx = bundle.to_advisor_prompt_context()
        assert "Tier-1" in ctx

    def test_no_last_execution_when_no_packet(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "missing.json",
            verdict_path=tmp_path / "missing2.json",
            config={},
        )
        ctx = bundle.to_advisor_prompt_context()
        # No status → Last Execution section should be absent
        assert "Last Execution Result" not in ctx

    def test_renders_warnings_when_present(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest({"current_sprint_goal": ""}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "x.json",
            verdict_path=tmp_path / "y.json",
            config={},
        )
        ctx = bundle.to_advisor_prompt_context()
        assert "Intake Warnings" in ctx or len(bundle.warnings) == 0 or "warning" in ctx.lower()

    def test_renders_verdict_when_present(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet())
        _write_json(tmp_path / "verdict.json", _verdict({"rationale": "UNIQUE_RATIONALE_STRING"}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "verdict.json",
            config={},
        )
        ctx = bundle.to_advisor_prompt_context()
        assert "UNIQUE_RATIONALE_STRING" in ctx


# ---------------------------------------------------------------------------
# Test results and extra packet fields
# ---------------------------------------------------------------------------
class TestPacketFields:
    def test_test_results_loaded(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet({
            "test_results": {"passed": 42, "failed": 3, "skipped": 0},
        }))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "x.json",
            config={},
        )
        assert bundle.last_test_results == {"passed": 42, "failed": 3, "skipped": 0}

    def test_questions_loaded(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet({"questions": ["Q1", "Q2"]}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "x.json",
            config={},
        )
        assert bundle.last_questions == ["Q1", "Q2"]

    def test_blockers_loaded(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet({"blockers": ["Need DB access"]}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "x.json",
            config={},
        )
        assert bundle.last_blockers == ["Need DB access"]

    def test_affected_tiers_loaded(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet({"affected_tiers": ["Tier-2", "Tier-3"]}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "x.json",
            config={},
        )
        assert "Tier-2" in bundle.last_affected_tiers

    def test_executor_notes_loaded(self, tmp_path):
        _write_json(tmp_path / "manifest.json", _manifest())
        _write_json(tmp_path / "packet.json", _packet({"executor_notes": "Note from executor"}))
        bundle = load(
            manifest_path=tmp_path / "manifest.json",
            packet_path=tmp_path / "packet.json",
            verdict_path=tmp_path / "x.json",
            config={},
        )
        assert bundle.last_executor_notes == "Note from executor"
