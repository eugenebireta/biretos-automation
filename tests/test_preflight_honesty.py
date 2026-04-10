"""Preflight Honesty Patch — verify all guards are implemented.

Originally batch 0: stubs marked as "stub_not_checked".
Updated batch #2: all guards now implemented — no stubs remain.

Deterministic tests — no live API, no unmocked time/randomness.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

# core_gate_bridge lives in orchestrator/ — add to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrator"))

from core_gate_bridge import _STUB_VALUE, run_preflight_guards  # noqa: E402


class TestAllGuardsImplemented:
    """After batch #2, all guards must be real — no stubs remain."""

    def test_no_stubs_in_results(self):
        """No guard should return _STUB_VALUE anymore."""
        result = run_preflight_guards(changed_files=[], trace_id="test-honesty-001")
        for guard, status in result["results"].items():
            assert status != _STUB_VALUE, (
                f"{guard} still returns stub — should be implemented"
            )

    def test_all_guards_return_pass_or_fail(self):
        """Every guard must return 'pass' or 'fail', never stub."""
        result = run_preflight_guards(changed_files=[], trace_id="test-honesty-002")
        for guard, status in result["results"].items():
            assert status in ("pass", "fail"), (
                f"{guard} returned '{status}' — expected 'pass' or 'fail'"
            )

    def test_frozen_files_is_real_guard(self):
        """frozen_files with no frozen touched → pass."""
        result = run_preflight_guards(changed_files=[], trace_id="test-honesty-003")
        assert result["results"]["frozen_files"] == "pass"


class TestPassedLogic:
    """passed flag must be determined by all guards."""

    def test_passed_true_when_no_violations(self):
        """Clean files → passed=True."""
        result = run_preflight_guards(
            changed_files=["catalog/datasheet/schema.py"],
            trace_id="test-honesty-004",
        )
        assert result["passed"] is True

    def test_passed_false_when_frozen_touched(self):
        """Frozen file touched → passed=False."""
        result = run_preflight_guards(
            changed_files=["core/domain/reconciliation_service.py"],
            trace_id="test-honesty-005",
        )
        assert result["passed"] is False
        assert result["blocked_by"] is not None


class TestArtifactStubList:
    """Artifact JSON must include stub_guards field (empty after batch #2)."""

    def test_artifact_has_empty_stub_list(self, tmp_path):
        """All guards implemented → stub_guards should be empty list."""
        with patch("core_gate_bridge.LAST_AUDIT_RESULT_PATH",
                   tmp_path / "last_audit_result.json"):
            run_preflight_guards(
                changed_files=[], trace_id="test-honesty-006",
            )

        artifacts = list(tmp_path.glob("last_preflight_result.json"))
        assert len(artifacts) == 1, f"Expected 1 artifact, found {len(artifacts)}"

        data = json.loads(artifacts[0].read_text(encoding="utf-8"))
        assert "stub_guards" in data
        assert data["stub_guards"] == [], (
            f"Expected no stubs after batch #2, got: {data['stub_guards']}"
        )
