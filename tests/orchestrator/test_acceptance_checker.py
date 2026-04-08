"""Tests for orchestrator/acceptance_checker.py — deterministic acceptance checks."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "orchestrator"))

import acceptance_checker as ac


SAMPLE_DIRECTIVE = """\
# Orchestrator Directive
trace_id: orch_test_001
task_id: TEST-TASK

## Sprint Goal
Fix the thing.

## Scope (Tier-3 verified)
- catalog/peha_reclassify_8sku.py
- catalog/evidence_bundles/peha_sku_evidence.json
- tests/catalog/test_peha_reclassify_8sku.py

## Constraints
- Tier-1 files are FROZEN

## Acceptance Criteria
- All tests pass
"""


class TestParseDirectiveScope:
    def test_parses_scope_files(self):
        files = ac._parse_directive_scope(SAMPLE_DIRECTIVE)
        assert files == [
            "catalog/peha_reclassify_8sku.py",
            "catalog/evidence_bundles/peha_sku_evidence.json",
            "tests/catalog/test_peha_reclassify_8sku.py",
        ]

    def test_empty_directive(self):
        assert ac._parse_directive_scope("") == []

    def test_no_scope_section(self):
        assert ac._parse_directive_scope("## Sprint Goal\nDo stuff\n") == []

    def test_no_scope_specified(self):
        text = "## Scope\n- (no scope specified)\n## Constraints\n"
        assert ac._parse_directive_scope(text) == []

    def test_scope_with_parenthetical(self):
        text = "## Scope (Tier-3 verified)\n- foo.py\n- bar.json\n## Next\n"
        assert ac._parse_directive_scope(text) == ["foo.py", "bar.json"]


class TestAcceptanceChecker:
    def test_all_pass_in_scope(self):
        packet = {
            "changed_files": ["catalog/peha_reclassify_8sku.py"],
            "affected_tiers": ["Tier-3"],
            "test_results": {"passed": 10, "failed": 0},
        }
        result = ac.check(packet, SAMPLE_DIRECTIVE, "trace_001")
        assert result.passed is True
        assert result.drift_detected is False
        assert result.trace_id == "trace_001"

    def test_empty_execution_fails(self):
        packet = {"changed_files": [], "affected_tiers": [], "test_results": None}
        result = ac.check(packet, SAMPLE_DIRECTIVE, "trace_002")
        assert result.passed is False
        a1 = [c for c in result.checks if c.check_id == "A1:NON_EMPTY"][0]
        assert a1.passed is False

    def test_tier1_violation_fails(self):
        packet = {
            "changed_files": ["catalog/peha_reclassify_8sku.py"],
            "affected_tiers": ["Tier-1", "Tier-3"],
            "test_results": None,
        }
        result = ac.check(packet, SAMPLE_DIRECTIVE, "trace_003")
        assert result.passed is False
        a2 = [c for c in result.checks if c.check_id == "A2:TIER1_SAFE"][0]
        assert a2.passed is False

    def test_test_failure_fails(self):
        packet = {
            "changed_files": ["catalog/peha_reclassify_8sku.py"],
            "affected_tiers": ["Tier-3"],
            "test_results": {"passed": 9, "failed": 1},
        }
        result = ac.check(packet, SAMPLE_DIRECTIVE, "trace_004")
        assert result.passed is False
        a3 = [c for c in result.checks if c.check_id == "A3:TESTS_PASS"][0]
        assert a3.passed is False

    def test_out_of_scope_drift(self):
        packet = {
            "changed_files": [
                "catalog/peha_reclassify_8sku.py",
                "some/random/file.py",
            ],
            "affected_tiers": ["Tier-3"],
            "test_results": None,
        }
        result = ac.check(packet, SAMPLE_DIRECTIVE, "trace_005")
        assert result.passed is False
        assert result.drift_detected is True
        assert "some/random/file.py" in result.out_of_scope_files

    def test_no_scope_in_directive_passes(self):
        """If directive has no scope section, skip scope check."""
        packet = {
            "changed_files": ["anything.py"],
            "affected_tiers": ["Tier-3"],
            "test_results": None,
        }
        result = ac.check(packet, "## Sprint Goal\nDo stuff", "trace_006")
        assert result.passed is True

    def test_multiple_scope_files_all_in_scope(self):
        packet = {
            "changed_files": [
                "catalog/peha_reclassify_8sku.py",
                "catalog/evidence_bundles/peha_sku_evidence.json",
                "tests/catalog/test_peha_reclassify_8sku.py",
            ],
            "affected_tiers": ["Tier-3"],
            "test_results": {"passed": 100, "failed": 0},
        }
        result = ac.check(packet, SAMPLE_DIRECTIVE, "trace_007")
        assert result.passed is True
        assert len(result.checks) == 4  # A1, A2, A3, A4

    def test_no_test_results_passes(self):
        """If tests weren't run, A3 passes by default."""
        packet = {
            "changed_files": ["catalog/peha_reclassify_8sku.py"],
            "affected_tiers": ["Tier-3"],
            "test_results": None,
        }
        result = ac.check(packet, SAMPLE_DIRECTIVE, "trace_008")
        a3 = [c for c in result.checks if c.check_id == "A3:TESTS_PASS"][0]
        assert a3.passed is True
        assert "skipped" in a3.detail

    def test_scope_from_directive_recorded(self):
        packet = {
            "changed_files": ["catalog/peha_reclassify_8sku.py"],
            "affected_tiers": ["Tier-3"],
            "test_results": None,
        }
        result = ac.check(packet, SAMPLE_DIRECTIVE, "trace_009")
        assert len(result.scope_from_directive) == 3
