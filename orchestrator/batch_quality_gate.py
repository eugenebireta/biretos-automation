"""
batch_quality_gate.py — deterministic quality gate for execution packets.

Evaluates an execution packet (from collect_packet.py) and returns a
pass/fail verdict with reason. No LLM calls — pure rule engine.

Rules:
  G1: FAIL if no changed_files (empty execution)
  G2: FAIL if Tier-1 in affected_tiers (frozen file violation)
  G3: FAIL if Tier-2 in affected_tiers AND risk was LOW (scope creep)
  G4: FAIL if test_results.failed > 0 (regression)
  G5: FAIL if blockers is non-empty (unresolved blockers)
  G6: PASS otherwise

Usage:
    from orchestrator.batch_quality_gate import check_packet
    result = check_packet(packet, expected_risk="LOW")
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class BatchGateResult:
    """Result of batch quality gate evaluation."""
    passed: bool
    reason: str
    rule: str                      # G1..G6
    auto_merge_eligible: bool      # True only if passed AND LOW risk
    details: Optional[dict] = None


def check_packet(
    packet: dict,
    expected_risk: str = "LOW",
) -> BatchGateResult:
    """Evaluate execution packet against batch quality rules.

    Args:
        packet: Execution packet dict (from collect_packet.collect()).
        expected_risk: Expected risk class from orchestrator (LOW/SEMI/CORE).

    Returns:
        BatchGateResult with pass/fail, reason, and auto-merge eligibility.
    """
    changed_files = packet.get("changed_files", [])
    affected_tiers = packet.get("affected_tiers", [])
    test_results = packet.get("test_results")
    blockers = packet.get("blockers", [])

    # G1: Empty execution — distinguish "already done" from "no output"
    if not changed_files:
        executor_notes = (packet.get("executor_notes") or "").lower()
        _already_signals = ("already", "previously", "no changes needed",
                            "no new changes", "nothing to do", "already exist",
                            "already committed", "already implemented")
        is_already_done = any(sig in executor_notes for sig in _already_signals)
        if is_already_done:
            return BatchGateResult(
                passed=True,
                reason="task already completed — executor confirmed no changes needed",
                rule="G1:ALREADY_DONE",
                auto_merge_eligible=False,  # don't auto-merge empty result
            )
        return BatchGateResult(
            passed=False,
            reason="no changed files — executor produced no output",
            rule="G1:EMPTY",
            auto_merge_eligible=False,
        )

    # G2: Tier-1 violation (frozen files)
    if "Tier-1" in affected_tiers:
        tier1_files = [f for f in changed_files
                       if _is_tier1(f)]
        return BatchGateResult(
            passed=False,
            reason=f"Tier-1 frozen file violation: {len(tier1_files)} files",
            rule="G2:TIER1_VIOLATION",
            auto_merge_eligible=False,
            details={"tier1_files": tier1_files[:10]},
        )

    # G3: Tier-2 scope creep on LOW risk
    if "Tier-2" in affected_tiers and expected_risk == "LOW":
        return BatchGateResult(
            passed=False,
            reason="Tier-2 files changed but expected risk was LOW (scope creep)",
            rule="G3:SCOPE_CREEP",
            auto_merge_eligible=False,
            details={"affected_tiers": affected_tiers},
        )

    # G4: Test regression
    if test_results and test_results.get("failed", 0) > 0:
        return BatchGateResult(
            passed=False,
            reason=f"test regression: {test_results['failed']} failed",
            rule="G4:TEST_REGRESSION",
            auto_merge_eligible=False,
            details={"test_results": test_results},
        )

    # G5: Unresolved blockers
    if blockers:
        return BatchGateResult(
            passed=False,
            reason=f"unresolved blockers: {len(blockers)}",
            rule="G5:BLOCKERS",
            auto_merge_eligible=False,
            details={"blockers": blockers},
        )

    # G6: All clear
    auto_merge = expected_risk == "LOW"
    return BatchGateResult(
        passed=True,
        reason="all checks passed",
        rule="G6:PASS",
        auto_merge_eligible=auto_merge,
        details={
            "changed_files_count": len(changed_files),
            "affected_tiers": affected_tiers,
            "test_results": test_results,
        },
    )


# Tier-1 prefixes (mirror of collect_packet.TIER_MAP)
_TIER1_PREFIXES = (
    ".cursor/windmill-core-v1/domain/reconciliation_",
    ".cursor/windmill-core-v1/maintenance_sweeper",
    ".cursor/windmill-core-v1/retention_policy",
    ".cursor/windmill-core-v1/domain/structural_checks",
    ".cursor/windmill-core-v1/domain/observability_service",
    ".cursor/windmill-core-v1/migrations/016_",
    ".cursor/windmill-core-v1/migrations/017_",
    ".cursor/windmill-core-v1/migrations/018_",
    ".cursor/windmill-core-v1/migrations/019_",
    ".cursor/windmill-core-v1/tests/validation/",
)


def _is_tier1(filepath: str) -> bool:
    return any(filepath.startswith(p) for p in _TIER1_PREFIXES)
