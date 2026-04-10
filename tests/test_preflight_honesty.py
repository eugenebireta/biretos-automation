"""Preflight Honesty Patch — verify stubs are marked honestly.

Batch 0: ensures run_preflight_guards() marks unimplemented guards as
"stub_not_checked" instead of false "pass", and that the passed/blocked
logic only considers implemented guards.

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


class TestStubsMarkedHonestly:
    """Stubs must never report 'pass' — they must say 'stub_not_checked'."""

    def test_stubs_marked_not_pass(self):
        """Three unimplemented guards must return _STUB_VALUE, not 'pass'."""
        result = run_preflight_guards(changed_files=[], trace_id="test-honesty-001")
        for guard in ("forbidden_imports", "forbidden_dml", "pinned_api"):
            assert result["results"][guard] == _STUB_VALUE, (
                f"{guard} should be '{_STUB_VALUE}', got '{result['results'][guard]}'"
            )

    def test_frozen_files_is_real_guard(self):
        """frozen_files is the only implemented guard — must return 'pass' or 'fail'."""
        result = run_preflight_guards(changed_files=[], trace_id="test-honesty-002")
        assert result["results"]["frozen_files"] == "pass"


class TestPassedLogic:
    """passed flag must be determined only by implemented guards."""

    def test_passed_true_when_no_frozen_touched(self):
        """No frozen files touched → passed=True (stubs excluded from check)."""
        result = run_preflight_guards(
            changed_files=["catalog/datasheet/schema.py"],
            trace_id="test-honesty-003",
        )
        assert result["passed"] is True

    def test_passed_false_when_frozen_touched(self):
        """Frozen file touched → passed=False despite stubs being present."""
        result = run_preflight_guards(
            changed_files=["core/domain/reconciliation_service.py"],
            trace_id="test-honesty-004",
        )
        assert result["passed"] is False
        assert result["blocked_by"] is not None


class TestArtifactStubList:
    """Artifact JSON must include stub_guards field for transparency."""

    def test_artifact_has_stub_list(self, tmp_path):
        """Written artifact must contain 'stub_guards' listing all stubs."""
        with patch("core_gate_bridge.LAST_AUDIT_RESULT_PATH",
                   tmp_path / "last_audit_result.json"):
            # run_preflight_guards writes to LAST_AUDIT_RESULT_PATH.parent /
            # "last_preflight_result.json", so we need parent to be tmp_path
            run_preflight_guards(
                changed_files=[], trace_id="test-honesty-005",
            )

        # Find the artifact file that was written
        artifacts = list(tmp_path.glob("last_preflight_result.json"))
        assert len(artifacts) == 1, f"Expected 1 artifact, found {len(artifacts)}"

        data = json.loads(artifacts[0].read_text(encoding="utf-8"))
        assert "stub_guards" in data
        assert set(data["stub_guards"]) == {"forbidden_imports", "forbidden_dml", "pinned_api"}
