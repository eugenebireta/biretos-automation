"""Tests for orchestrator/batch_quality_gate.py — deterministic batch quality gate."""
from batch_quality_gate import check_packet, BatchGateResult


def _base_packet(**overrides) -> dict:
    packet = {
        "schema_version": "v1",
        "trace_id": "test_trace",
        "status": "completed",
        "changed_files": ["scripts/enrichment/runner.py"],
        "affected_tiers": ["Tier-3"],
        "test_results": {"passed": 10, "failed": 0, "skipped": 0},
        "blockers": [],
        "questions": [],
    }
    packet.update(overrides)
    return packet


class TestG1Empty:
    def test_empty_files_fails(self):
        r = check_packet(_base_packet(changed_files=[]))
        assert not r.passed
        assert r.rule == "G1:EMPTY"

    def test_missing_files_key_fails(self):
        p = _base_packet()
        del p["changed_files"]
        r = check_packet(p)
        assert not r.passed
        assert r.rule == "G1:EMPTY"


class TestG2Tier1:
    def test_tier1_file_fails(self):
        r = check_packet(_base_packet(
            changed_files=[".cursor/windmill-core-v1/domain/reconciliation_service.py"],
            affected_tiers=["Tier-1", "Tier-3"],
        ))
        assert not r.passed
        assert r.rule == "G2:TIER1_VIOLATION"

    def test_tier3_only_passes(self):
        r = check_packet(_base_packet())
        assert r.passed


class TestG3ScopeCreep:
    def test_tier2_on_low_fails(self):
        r = check_packet(_base_packet(
            affected_tiers=["Tier-2", "Tier-3"],
        ), expected_risk="LOW")
        assert not r.passed
        assert r.rule == "G3:SCOPE_CREEP"

    def test_tier2_on_semi_passes(self):
        r = check_packet(_base_packet(
            affected_tiers=["Tier-2", "Tier-3"],
        ), expected_risk="SEMI")
        assert r.passed

    def test_tier2_on_core_passes(self):
        r = check_packet(_base_packet(
            affected_tiers=["Tier-2", "Tier-3"],
        ), expected_risk="CORE")
        assert r.passed


class TestG4TestRegression:
    def test_failed_tests_fails(self):
        r = check_packet(_base_packet(
            test_results={"passed": 10, "failed": 2, "skipped": 0},
        ))
        assert not r.passed
        assert r.rule == "G4:TEST_REGRESSION"

    def test_all_pass_passes(self):
        r = check_packet(_base_packet(
            test_results={"passed": 10, "failed": 0, "skipped": 1},
        ))
        assert r.passed

    def test_no_tests_passes(self):
        r = check_packet(_base_packet(test_results=None))
        assert r.passed


class TestG5Blockers:
    def test_blockers_fail(self):
        r = check_packet(_base_packet(blockers=["need owner decision"]))
        assert not r.passed
        assert r.rule == "G5:BLOCKERS"


class TestG6Pass:
    def test_clean_packet_passes(self):
        r = check_packet(_base_packet())
        assert r.passed
        assert r.rule == "G6:PASS"

    def test_auto_merge_on_low(self):
        r = check_packet(_base_packet(), expected_risk="LOW")
        assert r.auto_merge_eligible is True

    def test_no_auto_merge_on_semi(self):
        r = check_packet(_base_packet(), expected_risk="SEMI")
        assert r.auto_merge_eligible is False

    def test_no_auto_merge_on_core(self):
        r = check_packet(_base_packet(), expected_risk="CORE")
        assert r.auto_merge_eligible is False
