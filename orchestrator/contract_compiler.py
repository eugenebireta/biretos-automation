"""
contract_compiler.py — Canonical Contract Gate (Layer 0.5).

Deterministic verification layer between preflight guards (Layer 0) and
LLM critique (Layer 2). Checks three things without any LLM calls:

1. Prerequisite Verifier: are all stage prerequisites actually DONE?
2. Claim Verifier: are factual claims in the proposal true?
3. Shape Advisor: does the proposed solution shape match roadmap? (advisory)

Produces a VerifiedContext dict that is passed to LLM auditors so they
focus on residual engineering risk, not on fact-checking claims.

Cost: $0. No API calls. No hallucinations.
"""
from __future__ import annotations

import json
import logging
import re
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
ROADMAP_STATUS_PATH = ROOT / "docs" / "ROADMAP_LIVE_STATUS.json"

# ── Prerequisites per stage (from EXECUTION_ROADMAP_v2_3.md) ────────────────
# Key = stage id (matches ROADMAP_LIVE_STATUS.json), Value = list of prereq stage ids.
# Only stages with explicit "Prerequisite:" lines are listed.
STAGE_PREREQUISITES: dict[str, list[str]] = {
    "SS-1": ["5.5", "R3"],          # Iron Fence stable, R3 MVP done
    "R4":   ["R3"],                  # R3 Lot Analyzer v2 done
    # Part II requires Stability Gate
    "9":    ["8"],
    "10":   ["8"],
    "11":   ["8"],
    "12":   ["8"],
    "13":   ["8"],
    # Part III requires Part II
    "14":   ["9", "10", "11", "12", "13"],
    "15":   ["9", "10", "11", "12", "13"],
    "16":   ["15", "11"],            # Client Intelligence + Price Intelligence
    "17":   ["9", "10", "11", "12", "13"],
}

# ── Stage shape hints (advisory, not blocker) ───────────────────────────────
# Brief description of expected solution shape per stage from roadmap.
# Used for deviation warnings, not blocking.
STAGE_SHAPE_HINTS: dict[str, str] = {
    "SS-1": "versioned DataSheet schema, ingestion pipeline, version tracking, read-only views, tests+CI",
    "R4": (
        "buyer registry, pre-alert list, fast offer pack, price ladder, KPI tracking; "
        "Tier-3 tables: rev_buyer_registry, rev_liquidation_offers"
    ),
    "R1": "import SKU, normalize via Pydantic, publish safe subset, photo pipeline, idempotency, review bucket",
    "R2": "/export command, rate limit, auth, audit trail",
    "R3": "lot scoring, filter engine, capital map, ingestion from Core via append-only exports",
}


class ContractStatus(str, Enum):
    """Deterministic audit statuses — no ambiguity."""
    BLOCKED_PRECONDITION = "blocked_precondition"
    SHAPE_DEVIATION = "shape_deviation"
    CLEAN = "clean"


def _load_roadmap_status() -> dict[str, dict]:
    """Load ROADMAP_LIVE_STATUS.json → {stage_id: stage_dict}."""
    if not ROADMAP_STATUS_PATH.exists():
        logger.warning("contract_compiler: ROADMAP_LIVE_STATUS.json not found at %s",
                       ROADMAP_STATUS_PATH)
        return {}
    data = json.loads(ROADMAP_STATUS_PATH.read_text(encoding="utf-8"))
    return {s["id"]: s for s in data.get("stages", [])}


def verify_prerequisites(stage_id: str) -> dict[str, Any]:
    """
    Check that all prerequisites for a stage are satisfied.

    Reads actual_status (auto-generated from code artifacts), NOT roadmap_claimed
    (which can be stale). A prereq is satisfied if actual_status == "DONE".

    Returns:
        {
            "passed": bool,
            "status": "blocked_precondition" | "clean",
            "prereqs": [{"stage_id": str, "name": str, "actual_status": str, "satisfied": bool}],
            "blocked_by": [str] | None,
        }
    """
    prereq_ids = STAGE_PREREQUISITES.get(stage_id, [])
    if not prereq_ids:
        return {
            "passed": True,
            "status": ContractStatus.CLEAN.value,
            "prereqs": [],
            "blocked_by": None,
        }

    stages = _load_roadmap_status()
    results = []
    blocked_by = []

    for pid in prereq_ids:
        stage = stages.get(pid)
        if stage:
            actual = stage.get("actual_status", "UNKNOWN")
            name = stage.get("name", pid)
            satisfied = actual == "DONE"
        else:
            actual = "NOT_FOUND"
            name = pid
            satisfied = False

        results.append({
            "stage_id": pid,
            "name": name,
            "actual_status": actual,
            "satisfied": satisfied,
        })
        if not satisfied:
            blocked_by.append(f"{pid} ({name}): actual_status={actual}")

    passed = len(blocked_by) == 0
    return {
        "passed": passed,
        "status": ContractStatus.CLEAN.value if passed
        else ContractStatus.BLOCKED_PRECONDITION.value,
        "prereqs": results,
        "blocked_by": blocked_by if blocked_by else None,
    }


# ── Claim patterns ──────────────────────────────────────────────────────────
# Match phrases like "R3 done", "Iron Fence ✅", "R3 MVP завершён", "CI stable"
_CLAIM_PATTERNS = [
    # "X done/complete/stable/✅"
    re.compile(
        r"(?:Stage\s*|Этап\s*)?(\S+(?:\s+\S+)?)\s+"
        r"(?:done|DONE|complete|completed|stable|завершён|закрыт|✅|✔)",
        re.IGNORECASE,
    ),
    # "X is done/complete"
    re.compile(
        r"(?:Stage\s*|Этап\s*)?(\S+(?:\s+\S+)?)\s+(?:is\s+)?(?:done|complete|stable)",
        re.IGNORECASE,
    ),
]

# Map claim text fragments → stage IDs in ROADMAP_LIVE_STATUS
_CLAIM_STAGE_MAP: dict[str, str] = {
    "iron fence": "5.5",
    "iron_fence": "5.5",
    "r3": "R3",
    "r1": "R1",
    "r2": "R2",
    "r4": "R4",
    "stability gate": "8",
    "ci": "2",
    "branch protection": "2",
    "reconciliation": "3",
    "alerting": "4",
    "observability": "4.5",
    "pydantic": "5",
    "cdm": "5",
    "backoffice": "6",
    "nlu": "7",
    "assistant": "7",
    "meta orchestrator": "META",
    "auditor": "AUDITOR",
    "governance executor": "1",
    "lot analyzer": "R3",
    "catalog pipeline": "R1",
    "ss-1": "SS-1",
}


def _resolve_claim_to_stage(claim_text: str) -> str | None:
    """Try to map a claim text fragment to a stage ID."""
    lower = claim_text.lower().strip()
    for fragment, stage_id in _CLAIM_STAGE_MAP.items():
        if fragment in lower:
            return stage_id
    return None


def verify_claims(proposal_text: str) -> dict[str, Any]:
    """
    Parse factual claims from proposal text and verify against actual status.

    Extracts phrases like "R3 done", "Iron Fence stable" and checks them
    against ROADMAP_LIVE_STATUS.json actual_status field.

    Returns:
        {
            "claims": [{"text": str, "stage_id": str|None, "verified": bool, "actual_status": str}],
            "unverified_claims": [str],
            "false_claims": [str],
        }
    """
    stages = _load_roadmap_status()
    claims = []
    seen = set()

    for pattern in _CLAIM_PATTERNS:
        for match in pattern.finditer(proposal_text):
            claim_text = match.group(0).strip()
            subject = match.group(1).strip()

            # Deduplicate
            key = subject.lower()
            if key in seen:
                continue
            seen.add(key)

            stage_id = _resolve_claim_to_stage(subject)
            if stage_id and stage_id in stages:
                actual = stages[stage_id]["actual_status"]
                verified = actual == "DONE"
                claims.append({
                    "text": claim_text,
                    "stage_id": stage_id,
                    "verified": verified,
                    "actual_status": actual,
                })
            elif stage_id:
                # Stage ID resolved but not in ROADMAP_LIVE_STATUS
                claims.append({
                    "text": claim_text,
                    "stage_id": stage_id,
                    "verified": False,
                    "actual_status": "NOT_IN_STATUS_FILE",
                })
            else:
                claims.append({
                    "text": claim_text,
                    "stage_id": None,
                    "verified": False,
                    "actual_status": "UNRESOLVABLE",
                })

    return {
        "claims": claims,
        "unverified_claims": [c["text"] for c in claims if not c["verified"] and c["stage_id"]],
        "false_claims": [
            c["text"] for c in claims
            if not c["verified"] and c["stage_id"] and c["actual_status"] not in (
                "NOT_IN_STATUS_FILE", "UNRESOLVABLE",
            )
        ],
    }


def check_shape_alignment(stage_id: str, proposal_text: str) -> dict[str, Any]:
    """
    Advisory check: does the proposed solution shape match roadmap expectations?

    Returns WARNING (not BLOCK) if there's a deviation. The decision to proceed
    remains with LLM auditor + owner — shape deviations may be justified by
    repo context (e.g., file-based storage in a file-based repo).

    Returns:
        {
            "status": "clean" | "shape_deviation",
            "expected_shape": str | None,
            "deviations": [str],
        }
    """
    hint = STAGE_SHAPE_HINTS.get(stage_id)
    if not hint:
        return {
            "status": ContractStatus.CLEAN.value,
            "expected_shape": None,
            "deviations": [],
        }

    # Extract key nouns from shape hint
    hint_keywords = set(re.findall(r'\b\w{4,}\b', hint.lower()))
    proposal_lower = proposal_text.lower()

    # Check which expected components are mentioned in proposal
    missing = []
    for keyword in hint_keywords:
        # Skip generic words
        if keyword in ("from", "with", "that", "this", "only", "also",
                        "will", "must", "should", "have", "been", "into",
                        "core", "tier", "each", "tests"):
            continue
        if keyword not in proposal_lower:
            missing.append(keyword)

    deviations = []
    if missing and len(missing) > len(hint_keywords) * 0.5:
        deviations.append(
            f"proposal may not cover expected deliverables. "
            f"Roadmap expects: {hint}. "
            f"Keywords not found in proposal: {', '.join(sorted(missing)[:10])}"
        )

    return {
        "status": ContractStatus.SHAPE_DEVIATION.value if deviations
        else ContractStatus.CLEAN.value,
        "expected_shape": hint,
        "deviations": deviations,
    }


def compile_contract(
    stage_id: str,
    proposal_text: str,
    trace_id: str = "",
) -> dict[str, Any]:
    """
    Full contract compilation: prereqs + claims + shape.

    Returns a VerifiedContext dict suitable for passing to LLM auditors.
    LLM auditors receive this so they focus on residual engineering risk,
    not on fact-checking claims that have already been verified deterministically.

    Returns:
        {
            "status": ContractStatus value,
            "prereqs": {...},
            "claims": {...},
            "shape": {...},
            "verified_context": {
                "verified_facts": [...],
                "false_claims": [...],
                "shape_warnings": [...],
                "unverified_residual": str,
            },
            "trace_id": str,
        }
    """
    prereqs = verify_prerequisites(stage_id)
    claims = verify_claims(proposal_text)
    shape = check_shape_alignment(stage_id, proposal_text)

    # Determine overall status (worst wins)
    if not prereqs["passed"]:
        status = ContractStatus.BLOCKED_PRECONDITION
    elif shape["deviations"]:
        status = ContractStatus.SHAPE_DEVIATION
    else:
        status = ContractStatus.CLEAN

    # Build verified context for LLM
    verified_facts = []
    for p in prereqs["prereqs"]:
        if p["satisfied"]:
            verified_facts.append(f"{p['stage_id']} ({p['name']}): DONE ✓")
    for c in claims["claims"]:
        if c["verified"]:
            verified_facts.append(f"claim '{c['text']}': verified ✓")

    verified_context = {
        "verified_facts": verified_facts,
        "false_claims": claims["false_claims"],
        "shape_warnings": shape["deviations"],
        "unverified_residual": (
            "engineering risk: atomic writes, version chain, race conditions; "
            "DNA compliance: trace_id, idempotency_key, structured error logging; "
            "test coverage and mocking strategy"
        ),
    }

    result = {
        "status": status.value,
        "prereqs": prereqs,
        "claims": claims,
        "shape": shape,
        "verified_context": verified_context,
        "trace_id": trace_id,
    }

    logger.info(json.dumps({
        "trace_id": trace_id,
        "stage_id": stage_id,
        "status": status.value,
        "prereqs_passed": prereqs["passed"],
        "claim_count": len(claims["claims"]),
        "false_claim_count": len(claims["false_claims"]),
        "shape_deviations": len(shape["deviations"]),
        "outcome": "contract_compiled",
    }, ensure_ascii=False))

    return result
