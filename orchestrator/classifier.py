"""
classifier.py — deterministic task risk classifier.

Input:  list of changed files + affected tiers from execution packet.
Output: ClassifierResult(risk_class, governance_route, rationale, tier_violations)

Rules are hardcoded from PROJECT_DNA.md §2-5 and CLAUDE.md.
No LLM involved — this is a pure rule engine step.

Risk classes:
  LOW   — Tier-3 only, no Core touch
  SEMI  — Tier-2 body changes, new Tier-3 with financial side effects
  CORE  — Tier-1 adjacent, schema, FSM, Guardian, invariants

Governance routes:
  none      — LOW, no review needed
  critique  — SEMI, bounded critique pass
  audit     — SEMI with financial/API side effects
  spec_full — CORE, full INV-GOV pipeline
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Tier-1 frozen file prefixes (from PROJECT_DNA.md §3)
# ---------------------------------------------------------------------------
TIER1_PREFIXES: tuple[str, ...] = (
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

# Tier-2: business domain (pinned API surface)
TIER2_PREFIXES: tuple[str, ...] = (
    ".cursor/windmill-core-v1/domain/",
    ".cursor/windmill-core-v1/migrations/",
)

# Prohibited imports (PROJECT_DNA.md §5)
PROHIBITED_IMPORTS: tuple[str, ...] = (
    "domain.reconciliation_service",
    "domain.reconciliation_alerts",
    "domain.reconciliation_verify",
    "domain.structural_checks",
    "domain.observability_service",
)

# Pinned API signatures (PROJECT_DNA.md §4) — changing these = CORE
PINNED_SIGNATURES: tuple[str, ...] = (
    "_derive_payment_status",
    "_extract_order_total_minor",
    "recompute_order_cdek_cache_atomic",
    "update_shipment_status_atomic",
    "_ensure_snapshot_row",
    "InvoiceStatusRequest",
    "ShipmentTrackingStatusRequest",
)

# Revenue Tier-3 table prefixes (PROJECT_DNA.md §5b)
REVENUE_TABLE_PREFIXES: tuple[str, ...] = ("rev_", "stg_", "lot_")

# Core business tables — direct DML from Tier-3 is forbidden
CORE_BUSINESS_TABLES: tuple[str, ...] = (
    "order_ledger", "shipments", "payment_transactions",
    "reservations", "stock_ledger_entries", "availability_snapshot", "documents",
    "reconciliation_audit_log", "reconciliation_alerts", "reconciliation_suppressions",
)


@dataclass
class ClassifierResult:
    risk_class: str        # LOW | SEMI | CORE
    governance_route: str  # none | critique | audit | spec_full
    rationale: str
    tier_violations: list[str] = field(default_factory=list)
    blocking_rules: list[str] = field(default_factory=list)


def _check_tier(path: str) -> str:
    """Return 'Tier-1', 'Tier-2', or 'Tier-3' for a file path."""
    for prefix in TIER1_PREFIXES:
        if path.startswith(prefix):
            return "Tier-1"
    for prefix in TIER2_PREFIXES:
        if path.startswith(prefix):
            return "Tier-2"
    return "Tier-3"


def classify(
    changed_files: Sequence[str],
    affected_tiers: Sequence[str] | None = None,
    task_id: str = "",
    intent: str = "",
) -> ClassifierResult:
    """
    Deterministic risk classification.

    Args:
        changed_files: list of file paths from execution packet
        affected_tiers: pre-computed tiers from collect_packet (optional, recomputed if None)
        task_id: current task identifier (for rationale)
        intent: task intent string (scanned for prohibited patterns)

    Returns:
        ClassifierResult with risk_class, governance_route, rationale, violations
    """
    violations: list[str] = []
    blocking: list[str] = []

    # Recompute tiers if not provided
    computed_tiers: set[str] = set()
    for f in changed_files:
        computed_tiers.add(_check_tier(f))

    tiers = set(affected_tiers) if affected_tiers else computed_tiers

    # --- CORE triggers ---

    # Rule C1: Any Tier-1 file touched
    tier1_files = [f for f in changed_files if _check_tier(f) == "Tier-1"]
    if tier1_files:
        violations.append(f"Tier-1 files touched: {tier1_files}")
        blocking.append("C1: Tier-1 file modification → CORE")
        return ClassifierResult(
            risk_class="CORE",
            governance_route="spec_full",
            rationale=f"Tier-1 frozen files touched: {tier1_files}. Full INV-GOV required.",
            tier_violations=violations,
            blocking_rules=blocking,
        )

    # Rule C2: Prohibited imports in intent/task_id string
    for imp in PROHIBITED_IMPORTS:
        if imp in intent or imp in task_id:
            violations.append(f"Prohibited import referenced: {imp}")
            blocking.append(f"C2: Prohibited import {imp} → CORE")
            return ClassifierResult(
                risk_class="CORE",
                governance_route="spec_full",
                rationale=f"Prohibited import detected in task scope: {imp}",
                tier_violations=violations,
                blocking_rules=blocking,
            )

    # Rule C3: Pinned API signatures referenced in intent
    for sig in PINNED_SIGNATURES:
        if sig in intent:
            violations.append(f"Pinned API signature referenced: {sig}")
            blocking.append(f"C3: Pinned API {sig} → CORE")
            return ClassifierResult(
                risk_class="CORE",
                governance_route="spec_full",
                rationale=f"Pinned API signature in scope: {sig}. Signature changes are forbidden.",
                tier_violations=violations,
                blocking_rules=blocking,
            )

    # Rule C4: Core business table DML in intent
    for table in CORE_BUSINESS_TABLES:
        # Look for INSERT/UPDATE/DELETE patterns near core table names
        intent_lower = intent.lower()
        table_lower = table.lower()
        if table_lower in intent_lower:
            for dml in ("insert", "update", "delete", "alter", "drop"):
                if dml in intent_lower:
                    violations.append(f"Possible DML on core table {table}")
                    blocking.append(f"C4: Core table DML → CORE")
                    return ClassifierResult(
                        risk_class="CORE",
                        governance_route="spec_full",
                        rationale=f"Intent references Core table {table!r} with DML operation.",
                        tier_violations=violations,
                        blocking_rules=blocking,
                    )

    # --- SEMI triggers ---

    # Rule S1: Tier-2 files touched (body changes allowed, signatures not)
    tier2_files = [f for f in changed_files if _check_tier(f) == "Tier-2"]
    if tier2_files:
        violations.append(f"Tier-2 files touched: {tier2_files}")
        return ClassifierResult(
            risk_class="SEMI",
            governance_route="audit",
            rationale=f"Tier-2 domain files touched: {tier2_files}. Verify pinned API signatures unchanged.",
            tier_violations=violations,
            blocking_rules=[],
        )

    # Rule S2: migrations/020+ touched (Revenue schema)
    migration_files = [f for f in changed_files
                       if "migrations/" in f and _migration_seq(f) >= 20]
    if migration_files:
        violations.append(f"Revenue migrations touched: {migration_files}")
        return ClassifierResult(
            risk_class="SEMI",
            governance_route="critique",
            rationale=f"Revenue migration files: {migration_files}. Schema changes need critique.",
            tier_violations=violations,
            blocking_rules=[],
        )

    # Rule S3: orchestrator/ synthesizer or advisor touched (policy-level code)
    policy_files = [f for f in changed_files
                    if any(kw in f for kw in ("synthesizer", "advisor", "classifier"))]
    if policy_files:
        return ClassifierResult(
            risk_class="SEMI",
            governance_route="critique",
            rationale=f"Orchestrator policy files touched: {policy_files}. Critique before M3 gate.",
            tier_violations=[],
            blocking_rules=[],
        )

    # --- LOW ---
    tier_summary = sorted(tiers) if tiers else ["Tier-3"]
    return ClassifierResult(
        risk_class="LOW",
        governance_route="none",
        rationale=f"Tier-3 only changes ({tier_summary}). No Core touch. Batch execution allowed.",
        tier_violations=[],
        blocking_rules=[],
    )


def _migration_seq(path: str) -> int:
    """Extract migration sequence number from path like 'migrations/025_create_foo.sql'."""
    import re
    m = re.search(r"migrations/(\d+)_", path)
    return int(m.group(1)) if m else 0
