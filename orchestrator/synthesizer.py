"""
synthesizer.py — M3 Decision Synthesizer.

Deterministic rule engine between LLM Advisor verdict and directive writer.
Guarantees CORE-risk work cannot proceed without governance regardless of advisor output.

Input:  ClassifierResult + AdvisorVerdict + attempt_count + last_packet_status
Output: SynthesizerDecision

Rules (priority order):
  R1 CORE_GATE  — classifier or advisor == CORE → block, never write directive
  R2 SEMI       — either == SEMI → final_risk=SEMI, route=audit
  R3 SCOPE_GATE — Tier-1/2 files in advisor.scope → BLOCKED (partial exec is worse than none)
  R4 ATTEMPT_CAP — attempt_count >= max_attempts → ESCALATE
  R5 BLOCKED     — last packet status==blocked, no unblock keyword → BLOCKED
  R6 NO_OP       — scope empty after R3 → NO_OP (do not invoke executor)
  R7 PROCEED     — all gates passed

No LLM calls. No FSM mutations. No file I/O. Pure function.
Tier classification delegates to classifier._check_tier() — single source of truth.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Actions
ACTION_PROCEED    = "PROCEED"
ACTION_CORE_GATE  = "CORE_GATE"
ACTION_SEMI_AUDIT = "SEMI_AUDIT"   # P0.5: SEMI risk routes to pre-execution auditor
ACTION_ESCALATE   = "ESCALATE"
ACTION_BLOCKED    = "BLOCKED"
ACTION_NO_OP      = "NO_OP"

# Default attempt cap (overridden by config)
DEFAULT_MAX_ATTEMPTS = 3


@dataclass
class SynthesizerDecision:
    action: str                      # PROCEED | CORE_GATE | ESCALATE | BLOCKED | NO_OP
    final_risk: str                  # LOW | SEMI | CORE
    final_route: str                 # none | critique | audit | spec_full
    approved_scope: list[str]        # Tier-3-only filtered file list
    rationale: str                   # combined human-readable explanation
    rule_trace: list[str]            # rule IDs that fired, in order (no raw payloads)
    stripped_files: list[str] = field(default_factory=list)  # removed from scope
    warnings: list[str] = field(default_factory=list)


def decide(
    classification,                  # ClassifierResult from classifier.py
    verdict,                         # AdvisorVerdict from advisor.py (may be None)
    attempt_count: int = 0,
    last_packet_status: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> SynthesizerDecision:
    """
    Apply 7 rules in priority order and return a SynthesizerDecision.

    Args:
        classification: ClassifierResult (deterministic ground truth)
        verdict: AdvisorVerdict or None (LLM advisory — never overrides classifier)
        attempt_count: current attempt number from manifest
        last_packet_status: status field from last execution packet
        max_attempts: ceiling from config.yaml (default 3)

    Returns:
        SynthesizerDecision with action, final_risk, approved_scope, rule_trace
    """
    # Validate inputs — Fail Loud
    if classification is None:
        raise ValueError(
            "synthesizer.decide: classification is required",
        )

    rule_trace: list[str] = []
    warnings: list[str] = []

    classifier_risk = getattr(classification, "risk_class", "LOW")
    advisor_risk = getattr(verdict, "risk_assessment", "LOW") if verdict else "LOW"
    advisor_scope = list(getattr(verdict, "scope", []) if verdict else [])
    # R5: prefer structured field addresses_blocker if present, fall back to keyword
    advisor_addresses_blocker = getattr(verdict, "addresses_blocker", None) if verdict else None
    if advisor_addresses_blocker is None:
        # Legacy fallback: keyword search (less reliable)
        advisor_next_step = (getattr(verdict, "next_step", "") or "").lower() if verdict else ""
        _r5_unblocked = "unblock" in advisor_next_step
    else:
        _r5_unblocked = bool(advisor_addresses_blocker)

    logger.info(
        "synthesizer.decide: trace start "
        "classifier_risk=%s advisor_risk=%s attempt=%d last_status=%s",
        classifier_risk, advisor_risk, attempt_count, last_packet_status,
        extra={"error_class": None, "severity": "INFO", "retriable": False},
    )

    # -------------------------------------------------------------------------
    # R1: CORE_GATE — absolute, deterministic beats LLM
    # -------------------------------------------------------------------------
    if classifier_risk == "CORE" or advisor_risk == "CORE":
        rule_trace.append("R1:CORE_GATE")
        rationale = (
            f"CORE risk detected: classifier={classifier_risk}, advisor={advisor_risk}. "
            "Directive blocked pending governance review."
        )
        logger.warning(
            "synthesizer.decide: R1 CORE_GATE fired "
            "classifier_risk=%s advisor_risk=%s",
            classifier_risk, advisor_risk,
            extra={"error_class": "POLICY_VIOLATION", "severity": "WARNING", "retriable": False},
        )
        return SynthesizerDecision(
            action=ACTION_CORE_GATE,
            final_risk="CORE",
            final_route="spec_full",
            approved_scope=[],
            rationale=rationale,
            rule_trace=rule_trace,
            warnings=warnings,
        )

    # -------------------------------------------------------------------------
    # R4: ATTEMPT_CAP — check before further processing
    # -------------------------------------------------------------------------
    if attempt_count >= max_attempts:
        rule_trace.append("R4:ATTEMPT_CAP")
        rationale = (
            f"Attempt count {attempt_count} >= max_attempts {max_attempts}. "
            "Owner must reset attempt_count in manifest.json."
        )
        logger.warning(
            "synthesizer.decide: R4 ATTEMPT_CAP fired attempt=%d max=%d",
            attempt_count, max_attempts,
            extra={"error_class": "POLICY_VIOLATION", "severity": "WARNING", "retriable": False},
        )
        return SynthesizerDecision(
            action=ACTION_ESCALATE,
            final_risk=classifier_risk,
            final_route="none",
            approved_scope=[],
            rationale=rationale,
            rule_trace=rule_trace,
            warnings=warnings,
        )

    # -------------------------------------------------------------------------
    # R5: BLOCKED packet — don't continue blindly past a blocked execution
    # -------------------------------------------------------------------------
    if last_packet_status == "blocked" and not _r5_unblocked:
        rule_trace.append("R5:BLOCKED_PACKET")
        rationale = (
            "Last execution packet status is 'blocked' and advisor next_step "
            "does not contain an unblock strategy. Owner must resolve the block."
        )
        logger.warning(
            "synthesizer.decide: R5 BLOCKED_PACKET fired last_status=%s",
            last_packet_status,
            extra={"error_class": "POLICY_VIOLATION", "severity": "WARNING", "retriable": False},
        )
        return SynthesizerDecision(
            action=ACTION_BLOCKED,
            final_risk=classifier_risk,
            final_route="none",
            approved_scope=[],
            rationale=rationale,
            rule_trace=rule_trace,
            warnings=warnings,
        )

    # -------------------------------------------------------------------------
    # R2: SEMI escalation — risk elevation from either source
    # -------------------------------------------------------------------------
    final_risk = "LOW"
    final_route = "none"
    if classifier_risk == "SEMI" or advisor_risk == "SEMI":
        rule_trace.append("R2:SEMI_ESCALATION")
        final_risk = "SEMI"
        final_route = "audit"
        warnings.append(
            f"SEMI risk: classifier={classifier_risk}, advisor={advisor_risk}. "
            "Critique pass recommended before merge."
        )
        logger.info(
            "synthesizer.decide: R2 SEMI_ESCALATION "
            "classifier=%s advisor=%s",
            classifier_risk, advisor_risk,
            extra={"error_class": None, "severity": "INFO", "retriable": False},
        )
    else:
        rule_trace.append("R2:LOW_PASS")

    # -------------------------------------------------------------------------
    # R3: Scope sanitization — strip Tier-1/2, BLOCK if any stripped
    # Uses classifier._check_tier() — single authoritative source
    # -------------------------------------------------------------------------
    stripped_files: list[str] = []
    approved_scope: list[str] = []

    if advisor_scope:
        try:
            from classifier import _check_tier
        except ImportError:
            # P0-2: fail-closed — if tier check is unavailable, BLOCK (not pass-through)
            rule_trace.append("R3:TIER_CHECK_UNAVAILABLE")
            rationale = (
                "Cannot import classifier._check_tier — tier protection unavailable. "
                "Fail-closed: blocking execution to prevent unguarded Tier-1/2 access."
            )
            logger.error(
                "synthesizer.decide: R3 TIER_CHECK_UNAVAILABLE — fail-closed BLOCK",
                extra={"error_class": "PERMANENT", "severity": "ERROR", "retriable": False},
            )
            return SynthesizerDecision(
                action=ACTION_BLOCKED,
                final_risk="CORE",
                final_route="spec_full",
                approved_scope=[],
                rationale=rationale,
                rule_trace=rule_trace,
                stripped_files=[],
                warnings=warnings + [
                    "CRITICAL: classifier._check_tier import failed — "
                    "all scope blocked as fail-closed safety measure"
                ],
            )
        else:
            for f in advisor_scope:
                try:
                    tier = _check_tier(f)
                except Exception as _tier_exc:
                    # P0-2: individual file tier check crash => assume Tier-1 (fail-closed)
                    logger.error(
                        "synthesizer.decide: _check_tier crashed for %s: %s — assuming Tier-1",
                        f, _tier_exc,
                        extra={"error_class": "PERMANENT", "severity": "ERROR", "retriable": False},
                    )
                    tier = "Tier-1"
                if tier in ("Tier-1", "Tier-2"):
                    stripped_files.append(f)
                else:
                    approved_scope.append(f)

            if stripped_files:
                rule_trace.append(f"R3:SCOPE_GATE(stripped={len(stripped_files)})")
                rationale = (
                    f"Advisor scope contains protected files ({stripped_files}). "
                    "Partial execution of a multi-tier change is unsafe. "
                    "Owner must approve scope modification or submit CORE governance package."
                )
                logger.warning(
                    "synthesizer.decide: R3 SCOPE_GATE fired stripped=%s",
                    stripped_files,
                    extra={
                        "error_class": "POLICY_VIOLATION",
                        "severity": "WARNING",
                        "retriable": False,
                    },
                )
                return SynthesizerDecision(
                    action=ACTION_BLOCKED,
                    final_risk="CORE",
                    final_route="spec_full",
                    approved_scope=[],
                    rationale=rationale,
                    rule_trace=rule_trace,
                    stripped_files=stripped_files,
                    warnings=warnings,
                )
            else:
                rule_trace.append("R3:SCOPE_CLEAN")
    else:
        approved_scope = []

    # -------------------------------------------------------------------------
    # R6: Empty scope
    # LOW → NO_OP (executor can't proceed but low risk, just skip)
    # SEMI/CORE → ESCALATE (scope creep risk too high to allow "own judgement")
    # -------------------------------------------------------------------------
    if not approved_scope:
        if final_risk in ("SEMI", "CORE"):
            rule_trace.append(f"R6:ESCALATE(empty_scope,risk={final_risk})")
            rationale = (
                f"Approved scope is empty and final_risk={final_risk}. "
                "Allowing executor to proceed without scope on a SEMI/CORE task "
                "risks scope creep into Tier-2. Owner must specify target files."
            )
            logger.warning(
                "synthesizer.decide: R6 ESCALATE empty scope at risk=%s",
                final_risk,
                extra={"error_class": "POLICY_VIOLATION", "severity": "WARNING", "retriable": False},
            )
            return SynthesizerDecision(
                action=ACTION_ESCALATE,
                final_risk=final_risk,
                final_route=final_route,
                approved_scope=[],
                rationale=rationale,
                rule_trace=rule_trace,
                stripped_files=stripped_files,
                warnings=warnings,
            )
        else:
            rule_trace.append("R6:NO_OP(empty_scope,risk=LOW)")
            rationale = (
                "Approved scope is empty (LOW risk). "
                "Cannot produce a meaningful directive. "
                "Advisor should specify target files in the next cycle."
            )
            logger.info(
                "synthesizer.decide: R6 NO_OP empty scope LOW risk",
                extra={"error_class": None, "severity": "INFO", "retriable": False},
            )
            return SynthesizerDecision(
                action=ACTION_NO_OP,
                final_risk=final_risk,
                final_route=final_route,
                approved_scope=[],
                rationale=rationale,
                rule_trace=rule_trace,
                stripped_files=stripped_files,
                warnings=warnings,
            )

    # -------------------------------------------------------------------------
    # R7: PROCEED (LOW) or SEMI_AUDIT (SEMI)
    # P0.5: SEMI risk requires pre-execution auditor sign-off before building directive.
    # -------------------------------------------------------------------------
    if final_risk == "SEMI":
        rule_trace.append("R7:SEMI_AUDIT")
        rationale = (
            f"All gates passed. final_risk=SEMI — routing to pre-execution auditor. "
            f"Approved scope: {approved_scope}. "
            f"Audit must pass before directive is built."
        )
        logger.info(
            "synthesizer.decide: R7 SEMI_AUDIT final_risk=%s scope=%s",
            final_risk, approved_scope,
            extra={"error_class": None, "severity": "INFO", "retriable": False},
        )
        return SynthesizerDecision(
            action=ACTION_SEMI_AUDIT,
            final_risk=final_risk,
            final_route=final_route,
            approved_scope=approved_scope,
            rationale=rationale,
            rule_trace=rule_trace,
            stripped_files=[],
            warnings=warnings,
        )

    rule_trace.append("R7:PROCEED")
    rationale = (
        f"All gates passed. final_risk={final_risk}, route={final_route}. "
        f"Approved scope: {approved_scope}."
    )
    logger.info(
        "synthesizer.decide: R7 PROCEED final_risk=%s scope=%s",
        final_risk, approved_scope,
        extra={"error_class": None, "severity": "INFO", "retriable": False},
    )
    return SynthesizerDecision(
        action=ACTION_PROCEED,
        final_risk=final_risk,
        final_route=final_route,
        approved_scope=approved_scope,
        rationale=rationale,
        rule_trace=rule_trace,
        stripped_files=[],
        warnings=warnings,
    )
