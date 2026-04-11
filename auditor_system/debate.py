"""
debate.py — Debate layer for multi-round audit protocol.

NOT in hard_shell/ — keeps debate logic outside Protected Governance Surface.
review_runner calls these as pure functions / black boxes.

Implements:
  - Fast path detection (all approve + no critical → skip debate)
  - Cross-visibility context building for Round 2
  - Disagreement detection after Round 2
  - Compact critique pack for arbiter

Design rationale (from 7 external critiques):
  1. Round 1: isolated verdicts (no cross-visibility)
  2. Round 2: each auditor sees peer's Round 1 verdict (debate)
  3. Round 3: Opus arbiter sees raw object + full critic pack (not "audit of audit")
  4. Fast path: skip debate when all approve (saves API calls)
  5. Context passing is the key problem, not model selection
"""
from __future__ import annotations

import logging
from typing import Any

from .hard_shell.contracts import (
    AuditVerdict,
    AuditVerdictValue,
    QualityGateResult,
    RiskLevel,
)

logger = logging.getLogger(__name__)


def should_debate(verdicts: list[AuditVerdict], risk: RiskLevel) -> bool:
    """
    Determine if debate (Round 2) is needed after Round 1 critiques.

    Fast path (no debate) when:
      - All auditors approve AND no critical issues
      - At least one verdict exists

    All other cases → debate needed.
    """
    if not verdicts:
        return True  # No verdicts → something broke, debate to be safe

    all_approve = all(
        v.verdict == AuditVerdictValue.APPROVE for v in verdicts
    )
    any_critical = any(v.critical_count > 0 for v in verdicts)

    if all_approve and not any_critical:
        logger.info(
            "debate: fast path — all %d auditors approve, no criticals, skipping debate",
            len(verdicts),
        )
        return False

    logger.info(
        "debate: debate triggered — verdicts=%s criticals=%s",
        {v.auditor_id: v.verdict.value for v in verdicts},
        {v.auditor_id: v.critical_count for v in verdicts},
    )
    return True


def needs_arbiter(
    round2_verdicts: list[AuditVerdict],
    gate_result: QualityGateResult,
) -> bool:
    """
    Determine if Round 3 (Opus arbiter) is needed after debate.

    Arbiter needed when:
      - Gate still fails after Round 2
      - Auditors still disagree (approve vs reject)
    """
    if gate_result.passed:
        return False

    if len(round2_verdicts) < 2:
        return False  # Can't have disagreement with <2 auditors

    verdict_set = {v.verdict for v in round2_verdicts}
    has_conflict = (
        AuditVerdictValue.APPROVE in verdict_set
        and AuditVerdictValue.REJECT in verdict_set
    )

    if has_conflict:
        logger.info(
            "debate: arbiter needed — conflict persists after Round 2: %s",
            {v.auditor_id: v.verdict.value for v in round2_verdicts},
        )
        return True

    # Gate failed but no approve/reject conflict — arbiter still useful
    # for heavy_concerns or other gate failures
    logger.info(
        "debate: arbiter needed — gate failed after Round 2: %s",
        gate_result.reason,
    )
    return True


def build_debate_context(
    base_context: dict[str, Any],
    peer_verdict: AuditVerdict,
) -> dict[str, Any]:
    """
    Build context for Round 2 debate with peer verdict included.

    Each auditor sees the OTHER auditor's Round 1 verdict.
    This enables cross-audit without "audit of audit" problem —
    auditors still judge the OBJECT, informed by peer findings.
    """
    debate_ctx = {**base_context}
    debate_ctx["debate_round"] = 2
    debate_ctx["peer_verdict"] = {
        "auditor_id": peer_verdict.auditor_id,
        "verdict": peer_verdict.verdict.value,
        "summary": peer_verdict.summary,
        "issues": [
            {
                "severity": i.severity.value,
                "area": i.area,
                "description": i.description,
            }
            for i in peer_verdict.issues
        ],
        "critical_count": peer_verdict.critical_count,
        "warning_count": peer_verdict.warning_count,
    }
    return debate_ctx


def build_arbiter_pack(
    proposal: str,
    revised_proposal: str,
    round1_verdicts: list[AuditVerdict],
    round2_verdicts: list[AuditVerdict],
) -> dict[str, Any]:
    """
    Build compact critic pack for Opus arbiter (Round 3).

    Arbiter sees:
      - Raw proposals (original + revised)
      - All verdicts from both rounds
      - Task to decide: who is right, what's the final verdict
    """
    def _verdict_summary(v: AuditVerdict) -> dict:
        return {
            "auditor_id": v.auditor_id,
            "verdict": v.verdict.value,
            "summary": v.summary,
            "critical_count": v.critical_count,
            "warning_count": v.warning_count,
            "issues": [
                {
                    "severity": i.severity.value,
                    "area": i.area,
                    "description": i.description,
                }
                for i in v.issues
            ],
        }

    return {
        "original_proposal_excerpt": proposal[:4000] if len(proposal) > 4000 else proposal,
        "revised_proposal_excerpt": (
            revised_proposal[:4000]
            if len(revised_proposal) > 4000
            else revised_proposal
        ),
        "round1_verdicts": [_verdict_summary(v) for v in round1_verdicts],
        "round2_verdicts": [_verdict_summary(v) for v in round2_verdicts],
        "total_rounds": 2,
        "dispute_summary": _summarize_dispute(round1_verdicts, round2_verdicts),
    }


def _summarize_dispute(
    round1: list[AuditVerdict],
    round2: list[AuditVerdict],
) -> str:
    """One-paragraph summary of the dispute for arbiter context."""
    r1_verdicts = ", ".join(f"{v.auditor_id}={v.verdict.value}" for v in round1)
    r2_verdicts = ", ".join(f"{v.auditor_id}={v.verdict.value}" for v in round2)

    r1_issues = []
    r2_issues = []
    for v in round1:
        for i in v.issues:
            if i.severity.value in ("critical", "warning"):
                r1_issues.append(f"[{v.auditor_id}/{i.severity.value}] {i.description}")
    for v in round2:
        for i in v.issues:
            if i.severity.value in ("critical", "warning"):
                r2_issues.append(f"[{v.auditor_id}/{i.severity.value}] {i.description}")

    return (
        f"Round 1 verdicts: {r1_verdicts}. "
        f"Round 2 verdicts (after debate): {r2_verdicts}. "
        f"Key issues raised: {'; '.join(r1_issues[:5])}. "
        f"After debate: {'; '.join(r2_issues[:5]) or 'no new issues'}."
    )
