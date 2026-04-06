"""
tests/orchestrator/test_collect_packet.py

Deterministic tests for collect_packet.py.
All subprocess calls are mocked — no live git, no live pytest.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_orch = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "orchestrator"))
if _orch not in sys.path:
    sys.path.insert(0, _orch)

from collect_packet import (
    _parse_pytest_output,
    classify_tiers,
    collect,
)


# ---------------------------------------------------------------------------
# classify_tiers
# ---------------------------------------------------------------------------

class TestClassifyTiers:
    def test_tier3_scripts(self):
        assert classify_tiers(["scripts/providers.py"]) == ["Tier-3"]

    def test_tier3_orchestrator(self):
        assert classify_tiers(["orchestrator/main.py"]) == ["Tier-3"]

    def test_tier1_reconciliation(self):
        result = classify_tiers([
            ".cursor/windmill-core-v1/domain/reconciliation_service.py"
        ])
        assert "Tier-1" in result

    def test_tier1_frozen_migration(self):
        result = classify_tiers([
            ".cursor/windmill-core-v1/migrations/016_create_reconciliation_audit_log.sql"
        ])
        assert "Tier-1" in result

    def test_tier1_validation_test(self):
        result = classify_tiers([
            ".cursor/windmill-core-v1/tests/validation/test_phase3_alert_emission.py"
        ])
        assert "Tier-1" in result

    def test_tier2_domain(self):
        result = classify_tiers([
            ".cursor/windmill-core-v1/domain/payment_service.py"
        ])
        assert "Tier-2" in result

    def test_mixed_tiers(self):
        result = classify_tiers([
            "scripts/providers.py",
            ".cursor/windmill-core-v1/domain/reconciliation_service.py",
        ])
        assert "Tier-1" in result
        assert "Tier-3" in result

    def test_unknown_path_defaults_to_tier3(self):
        result = classify_tiers(["some_random_file.py"])
        assert result == ["Tier-3"]

    def test_empty_list(self):
        assert classify_tiers([]) == []

    def test_sorted_output(self):
        result = classify_tiers([
            ".cursor/windmill-core-v1/domain/reconciliation_service.py",
            "scripts/foo.py",
        ])
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# _parse_pytest_output
# ---------------------------------------------------------------------------

class TestParsePytestOutput:
    def test_all_passed(self):
        r = _parse_pytest_output("509 passed in 4.20s")
        assert r["passed"] == 509
        assert r["failed"] == 0
        assert r["skipped"] == 0

    def test_mixed_results(self):
        r = _parse_pytest_output("3 failed, 12 passed, 1 skipped in 2.00s")
        assert r["passed"] == 12
        assert r["failed"] == 3
        assert r["skipped"] == 1

    def test_errors(self):
        r = _parse_pytest_output("2 error, 5 passed in 1.00s")
        assert r["error"] == 2
        assert r["passed"] == 5

    def test_empty_output(self):
        r = _parse_pytest_output("")
        assert r == {"passed": 0, "failed": 0, "skipped": 0, "error": 0}

    def test_no_numbers(self):
        assert _parse_pytest_output("no tests ran")["passed"] == 0

    def test_large_suite(self):
        r = _parse_pytest_output("1234 passed, 0 failed, 5 skipped in 60.00s")
        assert r["passed"] == 1234
        assert r["skipped"] == 5


# ---------------------------------------------------------------------------
# collect() — full integration with all subprocesses mocked
# ---------------------------------------------------------------------------

FAKE_DIFF_STAT = "scripts/providers.py | 20 ++++\n1 file changed, 20 insertions(+)"
FAKE_DIFF = "diff --git a/scripts/providers.py b/scripts/providers.py\n" + "+" * 100
FAKE_MERGE_BASE = "abc1234567890abcdef"


def _make_subprocess_mock(stat_out="", diff_out="", merge_base=FAKE_MERGE_BASE,
                           name_only="scripts/providers.py"):
    def side_effect(cmd, **kwargs):
        mock = MagicMock()
        mock.returncode = 0
        joined = " ".join(cmd)
        if "merge-base" in joined:
            mock.stdout = merge_base + "\n"
        elif "name-only" in joined:
            mock.stdout = name_only + "\n"
        elif "--stat" in joined:
            mock.stdout = stat_out
        else:
            mock.stdout = diff_out
        mock.stderr = ""
        return mock
    return side_effect


class TestCollect:
    def _run(self, run_pytest_flag=False, executor_notes=None,
             name_only="scripts/providers.py", diff_out=FAKE_DIFF, stat_out=FAKE_DIFF_STAT):
        with patch("collect_packet.subprocess.run",
                   side_effect=_make_subprocess_mock(
                       stat_out=stat_out, diff_out=diff_out, name_only=name_only
                   )):
            return collect(
                trace_id="orch_test_001",
                base_commit=None,
                run_pytest_flag=run_pytest_flag,
                executor_notes=executor_notes,
            )

    def test_basic_structure(self):
        p = self._run()
        assert p["schema_version"] == "v1"
        assert p["trace_id"] == "orch_test_001"
        assert p["collected_by"] == "collect_packet.py"
        assert "collected_at" in p

    def test_changed_files_parsed(self):
        p = self._run(name_only="scripts/providers.py\nscripts/export_pipeline.py")
        assert "scripts/providers.py" in p["changed_files"]
        assert "scripts/export_pipeline.py" in p["changed_files"]

    def test_tiers_classified(self):
        assert self._run(name_only="scripts/providers.py")["affected_tiers"] == ["Tier-3"]

    def test_tier1_detection(self):
        p = self._run(
            name_only=".cursor/windmill-core-v1/domain/reconciliation_service.py"
        )
        assert "Tier-1" in p["affected_tiers"]

    def test_diff_truncation(self):
        p = self._run(diff_out="x" * 20_000)
        assert p["diff_truncated"] is True
        assert "[DIFF TRUNCATED]" in p["diff_summary"]
        assert len(p["diff_summary"]) <= 15_000 + len("\n[DIFF TRUNCATED]")

    def test_no_truncation_short_diff(self):
        assert self._run(diff_out="small diff")["diff_truncated"] is False

    def test_executor_notes_preserved(self):
        assert self._run(executor_notes="All good")["executor_notes"] == "All good"

    def test_no_pytest_when_flag_false(self):
        assert self._run(run_pytest_flag=False)["test_results"] is None

    def test_pytest_results_included(self):
        with patch("collect_packet.subprocess.run",
                   side_effect=_make_subprocess_mock()):
            with patch("collect_packet.run_pytest",
                       return_value={"passed": 50, "failed": 0, "skipped": 2, "error": 0}):
                p = collect(trace_id="orch_test_002", run_pytest_flag=True)
        assert p["test_results"]["passed"] == 50
        assert p["test_results"]["skipped"] == 2

    def test_status_completed_with_changes(self):
        assert self._run(name_only="scripts/foo.py")["status"] == "completed"

    def test_status_partial_no_changes(self):
        assert self._run(name_only="")["status"] == "partial"

    def test_base_commit_recorded(self):
        with patch("collect_packet.subprocess.run",
                   side_effect=_make_subprocess_mock()):
            p = collect(trace_id="orch_test_003", base_commit="deadbeef")
        assert p["base_commit"] == "deadbeef"

    def test_empty_questions_and_blockers(self):
        p = self._run()
        assert p["questions"] == []
        assert p["blockers"] == []

    def test_valid_json_serializable(self):
        p = self._run()
        assert json.loads(json.dumps(p))["trace_id"] == "orch_test_001"
