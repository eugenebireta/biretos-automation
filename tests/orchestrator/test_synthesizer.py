"""
test_synthesizer.py — deterministic unit tests for orchestrator/synthesizer.py

All tests are pure — no file I/O, no LLM, no subprocess.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "orchestrator"))

import pytest
from synthesizer import (
    decide,
    SynthesizerDecision,
    ACTION_PROCEED,
    ACTION_CORE_GATE,
    ACTION_ESCALATE,
    ACTION_BLOCKED,
    ACTION_NO_OP,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clf(risk="LOW", route="none"):
    c = MagicMock()
    c.risk_class = risk
    c.governance_route = route
    c.rationale = f"test rationale risk={risk}"
    return c


def _verdict(risk="LOW", route="none", scope=None, next_step="proceed"):
    v = MagicMock()
    v.risk_assessment = risk
    v.governance_route = route
    v.scope = scope if scope is not None else ["scripts/foo.py"]
    v.next_step = next_step
    v.rationale = "advisor rationale"
    # Explicitly None so synthesizer falls back to keyword search (not structured field)
    v.addresses_blocker = None
    return v


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
class TestInputValidation:
    def test_none_classification_raises(self):
        with pytest.raises(ValueError):
            decide(None, _verdict())

    def test_returns_synthesizer_decision(self):
        result = decide(_clf(), _verdict())
        assert isinstance(result, SynthesizerDecision)

    def test_rule_trace_is_list(self):
        result = decide(_clf(), _verdict())
        assert isinstance(result.rule_trace, list)
        assert len(result.rule_trace) > 0


# ---------------------------------------------------------------------------
# R1: CORE_GATE
# ---------------------------------------------------------------------------
class TestR1CoreGate:
    def test_classifier_core_triggers_gate(self):
        result = decide(_clf("CORE"), _verdict("LOW"))
        assert result.action == ACTION_CORE_GATE

    def test_advisor_core_triggers_gate(self):
        result = decide(_clf("LOW"), _verdict("CORE"))
        assert result.action == ACTION_CORE_GATE

    def test_both_core_triggers_gate(self):
        result = decide(_clf("CORE"), _verdict("CORE"))
        assert result.action == ACTION_CORE_GATE

    def test_core_gate_final_risk_is_core(self):
        result = decide(_clf("CORE"), _verdict("LOW"))
        assert result.final_risk == "CORE"

    def test_core_gate_route_spec_full(self):
        result = decide(_clf("CORE"), _verdict("LOW"))
        assert result.final_route == "spec_full"

    def test_core_gate_approved_scope_empty(self):
        result = decide(_clf("CORE"), _verdict(scope=["scripts/foo.py"]))
        assert result.approved_scope == []

    def test_core_gate_rule_trace_contains_r1(self):
        result = decide(_clf("CORE"), _verdict())
        assert any("R1" in r for r in result.rule_trace)

    def test_low_both_not_core(self):
        result = decide(_clf("LOW"), _verdict("LOW"))
        assert result.action != ACTION_CORE_GATE

    def test_semi_both_not_core(self):
        result = decide(_clf("SEMI"), _verdict("SEMI"))
        assert result.action != ACTION_CORE_GATE


# ---------------------------------------------------------------------------
# R4: ATTEMPT_CAP
# ---------------------------------------------------------------------------
class TestR4AttemptCap:
    def test_at_cap_escalates(self):
        result = decide(_clf(), _verdict(), attempt_count=3, max_attempts=3)
        assert result.action == ACTION_ESCALATE

    def test_over_cap_escalates(self):
        result = decide(_clf(), _verdict(), attempt_count=5, max_attempts=3)
        assert result.action == ACTION_ESCALATE

    def test_under_cap_proceeds(self):
        result = decide(_clf(), _verdict(scope=["scripts/foo.py"]), attempt_count=2, max_attempts=3)
        assert result.action != ACTION_ESCALATE

    def test_attempt_cap_rule_trace(self):
        result = decide(_clf(), _verdict(), attempt_count=3, max_attempts=3)
        assert any("R4" in r for r in result.rule_trace)

    def test_r1_beats_r4(self):
        # R1 fires before R4
        result = decide(_clf("CORE"), _verdict(), attempt_count=10, max_attempts=3)
        assert result.action == ACTION_CORE_GATE
        assert any("R1" in r for r in result.rule_trace)
        assert not any("R4" in r for r in result.rule_trace)


# ---------------------------------------------------------------------------
# R5: BLOCKED_PACKET
# ---------------------------------------------------------------------------
class TestR5BlockedPacket:
    def test_blocked_status_no_unblock_keyword(self):
        result = decide(_clf(), _verdict(next_step="fix the tests"),
                        last_packet_status="blocked")
        assert result.action == ACTION_BLOCKED

    def test_blocked_status_with_unblock_keyword(self):
        result = decide(_clf(), _verdict(next_step="unblock by adding retry logic",
                                         scope=["scripts/foo.py"]),
                        last_packet_status="blocked")
        assert result.action != ACTION_BLOCKED

    def test_addresses_blocker_true_structured_field(self):
        # Opus mandatory fix 1: structured field takes priority over keyword
        v = _verdict(scope=["scripts/foo.py"])
        v.addresses_blocker = True
        result = decide(_clf(), v, last_packet_status="blocked")
        assert result.action != ACTION_BLOCKED

    def test_addresses_blocker_false_structured_field(self):
        v = _verdict(next_step="unblock this immediately", scope=["scripts/foo.py"])
        v.addresses_blocker = False
        result = decide(_clf(), v, last_packet_status="blocked")
        assert result.action == ACTION_BLOCKED

    def test_non_blocked_status_not_blocked(self):
        result = decide(_clf(), _verdict(scope=["scripts/foo.py"]),
                        last_packet_status="completed")
        assert result.action != ACTION_BLOCKED

    def test_none_status_not_blocked(self):
        result = decide(_clf(), _verdict(scope=["scripts/foo.py"]),
                        last_packet_status=None)
        assert result.action != ACTION_BLOCKED

    def test_blocked_rule_trace(self):
        result = decide(_clf(), _verdict(next_step="retry"),
                        last_packet_status="blocked")
        assert any("R5" in r for r in result.rule_trace)

    def test_r1_beats_r5(self):
        result = decide(_clf("CORE"), _verdict(), last_packet_status="blocked")
        assert result.action == ACTION_CORE_GATE

    def test_r4_beats_r5(self):
        result = decide(_clf(), _verdict(), attempt_count=5, max_attempts=3,
                        last_packet_status="blocked")
        assert result.action == ACTION_ESCALATE


# ---------------------------------------------------------------------------
# R2: SEMI escalation
# ---------------------------------------------------------------------------
class TestR2Semi:
    def test_classifier_semi_elevates_risk(self):
        result = decide(_clf("SEMI"), _verdict(scope=["scripts/foo.py"]))
        assert result.final_risk == "SEMI"

    def test_advisor_semi_elevates_risk(self):
        result = decide(_clf("LOW"), _verdict("SEMI", scope=["scripts/foo.py"]))
        assert result.final_risk == "SEMI"

    def test_semi_route_is_audit(self):
        result = decide(_clf("SEMI"), _verdict(scope=["scripts/foo.py"]))
        assert result.final_route == "audit"

    def test_both_low_final_risk_low(self):
        result = decide(_clf("LOW"), _verdict("LOW", scope=["scripts/foo.py"]))
        assert result.final_risk == "LOW"

    def test_both_low_route_none(self):
        result = decide(_clf("LOW"), _verdict("LOW", scope=["scripts/foo.py"]))
        assert result.final_route == "none"

    def test_semi_warning_added(self):
        result = decide(_clf("SEMI"), _verdict(scope=["scripts/foo.py"]))
        assert len(result.warnings) > 0

    def test_semi_rule_trace(self):
        result = decide(_clf("SEMI"), _verdict(scope=["scripts/foo.py"]))
        assert any("R2" in r for r in result.rule_trace)


# ---------------------------------------------------------------------------
# R3: Scope sanitization
# ---------------------------------------------------------------------------
class TestR3ScopeSanitization:
    def test_tier3_file_passes(self):
        result = decide(_clf(), _verdict(scope=["scripts/export_pipeline.py"]))
        assert "scripts/export_pipeline.py" in result.approved_scope

    def test_tier1_file_blocked(self):
        result = decide(_clf(), _verdict(
            scope=[".cursor/windmill-core-v1/domain/reconciliation_service.py"]
        ))
        assert result.action == ACTION_BLOCKED

    def test_tier2_file_blocked(self):
        result = decide(_clf(), _verdict(
            scope=[".cursor/windmill-core-v1/domain/cdm_models.py"]
        ))
        assert result.action == ACTION_BLOCKED

    def test_blocked_scope_in_stripped_files(self):
        tier1 = ".cursor/windmill-core-v1/domain/reconciliation_service.py"
        result = decide(_clf(), _verdict(scope=[tier1]))
        assert tier1 in result.stripped_files

    def test_mixed_scope_blocks_on_protected(self):
        # Tier-3 + Tier-1 mix → BLOCKED (not partial proceed)
        result = decide(_clf(), _verdict(scope=[
            "scripts/foo.py",
            ".cursor/windmill-core-v1/domain/reconciliation_service.py",
        ]))
        assert result.action == ACTION_BLOCKED

    def test_mixed_scope_approved_empty_on_block(self):
        result = decide(_clf(), _verdict(scope=[
            "scripts/foo.py",
            ".cursor/windmill-core-v1/domain/reconciliation_service.py",
        ]))
        assert result.approved_scope == []

    def test_scope_block_final_risk_core(self):
        result = decide(_clf(), _verdict(
            scope=[".cursor/windmill-core-v1/maintenance_sweeper.py"]
        ))
        assert result.final_risk == "CORE"
        assert result.final_route == "spec_full"

    def test_clean_scope_passes(self):
        result = decide(_clf(), _verdict(scope=["scripts/a.py", "scripts/b.py"]))
        assert result.action == ACTION_PROCEED
        assert "scripts/a.py" in result.approved_scope
        assert "scripts/b.py" in result.approved_scope

    def test_r3_rule_trace_scope_gate(self):
        result = decide(_clf(), _verdict(
            scope=[".cursor/windmill-core-v1/domain/reconciliation_service.py"]
        ))
        assert any("R3" in r for r in result.rule_trace)

    def test_r3_rule_trace_scope_clean(self):
        result = decide(_clf(), _verdict(scope=["scripts/foo.py"]))
        assert any("R3" in r and "CLEAN" in r for r in result.rule_trace)


# ---------------------------------------------------------------------------
# R6: NO_OP (empty scope)
# ---------------------------------------------------------------------------
class TestR6NoOp:
    def test_empty_scope_low_risk_is_no_op(self):
        result = decide(_clf("LOW"), _verdict("LOW", scope=[]))
        assert result.action == ACTION_NO_OP

    def test_none_verdict_empty_scope_is_no_op(self):
        result = decide(_clf("LOW"), None)
        assert result.action == ACTION_NO_OP

    def test_empty_scope_semi_risk_is_escalate(self):
        # Opus mandatory fix 2: SEMI + empty scope → ESCALATE, not NO_OP
        result = decide(_clf("SEMI"), _verdict("SEMI", scope=[]))
        assert result.action == ACTION_ESCALATE

    def test_empty_scope_classifier_semi_is_escalate(self):
        result = decide(_clf("SEMI"), _verdict("LOW", scope=[]))
        assert result.action == ACTION_ESCALATE

    def test_no_op_rule_trace(self):
        result = decide(_clf("LOW"), _verdict("LOW", scope=[]))
        assert any("R6" in r for r in result.rule_trace)

    def test_no_op_approved_scope_empty(self):
        result = decide(_clf("LOW"), _verdict("LOW", scope=[]))
        assert result.approved_scope == []

    def test_semi_empty_scope_escalate_rule_trace(self):
        result = decide(_clf("SEMI"), _verdict(scope=[]))
        assert any("R6" in r for r in result.rule_trace)


# ---------------------------------------------------------------------------
# R7: PROCEED
# ---------------------------------------------------------------------------
class TestR7Proceed:
    def test_all_green_proceeds(self):
        result = decide(_clf("LOW"), _verdict("LOW", scope=["scripts/foo.py"]))
        assert result.action == ACTION_PROCEED

    def test_proceed_approved_scope_populated(self):
        result = decide(_clf("LOW"), _verdict("LOW", scope=["scripts/foo.py", "scripts/bar.py"]))
        assert len(result.approved_scope) == 2

    def test_proceed_stripped_empty(self):
        result = decide(_clf("LOW"), _verdict("LOW", scope=["scripts/foo.py"]))
        assert result.stripped_files == []

    def test_proceed_rule_trace_contains_r7(self):
        result = decide(_clf("LOW"), _verdict("LOW", scope=["scripts/foo.py"]))
        assert any("R7" in r for r in result.rule_trace)

    def test_proceed_rationale_non_empty(self):
        result = decide(_clf("LOW"), _verdict("LOW", scope=["scripts/foo.py"]))
        assert len(result.rationale) > 0


# ---------------------------------------------------------------------------
# Rule priority ordering
# ---------------------------------------------------------------------------
class TestRulePriority:
    def test_r1_beats_r2(self):
        result = decide(_clf("CORE"), _verdict("SEMI"))
        assert result.action == ACTION_CORE_GATE

    def test_r1_beats_r6(self):
        result = decide(_clf("CORE"), _verdict(scope=[]))
        assert result.action == ACTION_CORE_GATE

    def test_r4_beats_r2(self):
        result = decide(_clf("SEMI"), _verdict(), attempt_count=5, max_attempts=3)
        assert result.action == ACTION_ESCALATE

    def test_r4_beats_r5(self):
        result = decide(_clf(), _verdict(), attempt_count=5, max_attempts=3,
                        last_packet_status="blocked")
        assert result.action == ACTION_ESCALATE

    def test_r5_beats_r6(self):
        result = decide(_clf(), _verdict(scope=[], next_step="retry"),
                        last_packet_status="blocked")
        assert result.action == ACTION_BLOCKED

    def test_r3_fires_after_r2(self):
        result = decide(_clf("SEMI"), _verdict(
            scope=[".cursor/windmill-core-v1/domain/reconciliation_service.py"]
        ))
        # R2 fires (SEMI), then R3 fires (BLOCKED)
        assert result.action == ACTION_BLOCKED
        assert any("R2" in r for r in result.rule_trace)
        assert any("R3" in r for r in result.rule_trace)
