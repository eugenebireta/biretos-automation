"""identity_gate.py — Deterministic identity gate for enrichment pipeline.

Provides a single reusable gate that answers:
  - Is the brand/subbrand consistent with expected identity?
  - Is the PN match strong enough?
  - Is the category consistent?
  - Overall: pass / review / block?

Design:
  - Pure functions, no I/O, no API calls.
  - Uses brand_knowledge for canonical ecosystem logic.
  - Uses category_resolver for category conflict detection.
  - Reason codes are machine-readable for downstream consumers.

Integration points:
  - merge_research_to_evidence.py — before price/specs acceptance
  - deterministic_false_positive_controls.py — brand guard
  - export_pipeline.py — identity_level enrichment (future)
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Optional

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from brand_knowledge import load_brand_config


# ── Brand ecosystem definitions ─────────────────────────────────────────────
# A "canonical ecosystem" groups parent brand + sub-brands.
# Same PN under Honeywell vs PEHA is NOT a mismatch — PEHA is Honeywell sub-brand.

_KNOWN_ECOSYSTEMS: dict[str, set[str]] = {
    "honeywell": {"honeywell", "peha", "esser", "notifier", "saia", "elster",
                  "honeywell analytics", "honeywell home", "honeywell process solutions"},
}


def _normalize_brand(brand: str) -> str:
    return (brand or "").strip().lower()


def _brands_in_same_ecosystem(brand_a: str, brand_b: str) -> bool:
    """Check if two brands belong to the same canonical ecosystem."""
    a = _normalize_brand(brand_a)
    b = _normalize_brand(brand_b)
    if not a or not b:
        return False
    if a == b:
        return True

    # Check known ecosystems
    for _parent, members in _KNOWN_ECOSYSTEMS.items():
        if a in members and b in members:
            return True

    # Check brand_knowledge YAML sub_brands
    config_a = load_brand_config(brand_a)
    if config_a:
        subs_a = {s.lower() for s in config_a.get("sub_brands", [])}
        parent_a = _normalize_brand(config_a.get("brand", ""))
        family_a = {parent_a} | subs_a | {_normalize_brand(al) for al in config_a.get("aliases", [])}
        if b in family_a:
            return True

    config_b = load_brand_config(brand_b)
    if config_b:
        subs_b = {s.lower() for s in config_b.get("sub_brands", [])}
        parent_b = _normalize_brand(config_b.get("brand", ""))
        family_b = {parent_b} | subs_b | {_normalize_brand(al) for al in config_b.get("aliases", [])}
        if a in family_b:
            return True

    return False


# ── Gate result ─────────────────────────────────────────────────────────────

@dataclass
class IdentityGateResult:
    """Deterministic outcome of identity evaluation."""
    gate_result: str = "block"          # "pass" | "review" | "block"
    brand_match_status: str = "unknown"  # "confirmed" | "ecosystem_match" | "mismatch" | "unknown"
    pn_match_status: str = "unknown"     # "exact" | "ambiguous" | "unknown"
    category_match_status: str = "unknown"  # "consistent" | "inconsistent" | "unknown"
    identity_resolved: bool = False
    reason_codes: list[str] = field(default_factory=list)

    @property
    def allows_price(self) -> bool:
        """Price acceptance allowed only on pass."""
        return self.gate_result == "pass"

    @property
    def allows_specs(self) -> bool:
        """Specs acceptance allowed on pass or review (but flagged)."""
        return self.gate_result in ("pass", "review")

    @property
    def is_blocked(self) -> bool:
        return self.gate_result == "block"


# ── Brand guard ─────────────────────────────────────────────────────────────

def evaluate_brand_match(
    expected_brand: str,
    found_brand: str,
    expected_subbrand: str = "",
) -> tuple[str, list[str]]:
    """Evaluate brand match status.

    Returns:
        (status, reason_codes) where status is one of:
        - "confirmed": exact string match
        - "ecosystem_match": different names but same canonical ecosystem
        - "mismatch": brands are from different ecosystems
        - "unknown": insufficient data to determine
    """
    reasons: list[str] = []
    eb = _normalize_brand(expected_brand)
    fb = _normalize_brand(found_brand)
    esb = _normalize_brand(expected_subbrand)

    if not fb:
        reasons.append("brand_unknown_no_found_brand")
        return "unknown", reasons

    if not eb:
        reasons.append("brand_unknown_no_expected_brand")
        return "unknown", reasons

    # Exact match
    if fb == eb or fb == esb:
        return "confirmed", reasons

    # Ecosystem match (e.g., PEHA found for Honeywell expected)
    if _brands_in_same_ecosystem(eb, fb):
        reasons.append(f"brand_ecosystem_match:{eb}+{fb}")
        return "ecosystem_match", reasons

    if esb and _brands_in_same_ecosystem(esb, fb):
        reasons.append(f"brand_ecosystem_match:{esb}+{fb}")
        return "ecosystem_match", reasons

    # True mismatch
    reasons.append(f"brand_mismatch:{eb}!={fb}")
    return "mismatch", reasons


# ── PN match evaluation ─────────────────────────────────────────────────────

def evaluate_pn_match(
    identity_confirmed: Optional[bool],
    pn_match_location: str = "",
    pn_confidence: float = 0.0,
) -> tuple[str, list[str]]:
    """Evaluate PN match status from DR result signals.

    Returns:
        (status, reason_codes) where status is one of:
        - "exact": strong structured match (jsonld/title/h1) or identity_confirmed=True
        - "ambiguous": body match only, or low confidence
        - "unknown": no match data
    """
    reasons: list[str] = []

    if identity_confirmed is True:
        return "exact", reasons

    if identity_confirmed is False:
        reasons.append("pn_identity_not_confirmed")
        return "ambiguous", reasons

    # Fall back to location-based assessment
    structured = {"jsonld", "title", "h1", "product_context"}
    if pn_match_location in structured:
        return "exact", reasons

    if pn_match_location == "body":
        reasons.append("pn_body_match_only")
        return "ambiguous", reasons

    if pn_confidence >= 0.85:
        return "exact", reasons

    if pn_confidence >= 0.50:
        reasons.append("pn_moderate_confidence")
        return "ambiguous", reasons

    reasons.append("pn_no_match_data")
    return "unknown", reasons


# ── Category match evaluation ───────────────────────────────────────────────

def evaluate_category_match(
    expected_category: str,
    found_category: str,
    product_category: str = "",
) -> tuple[str, list[str]]:
    """Evaluate category consistency.

    expected_category = advisory hint from xlsx (92% wrong — NOT truth)
    found_category = DR category_suggestion
    product_category = normalized canonical category from evidence

    Returns:
        (status, reason_codes)
    """
    reasons: list[str] = []

    # Use product_category (normalized) as primary if available
    resolved = product_category or found_category
    if not resolved:
        if not expected_category:
            reasons.append("category_no_data")
            return "unknown", reasons
        # Only expected_category available — it's unreliable (92% wrong)
        reasons.append("category_only_expected_unreliable")
        return "unknown", reasons

    if not expected_category:
        # No expected to compare against — trust resolved
        return "consistent", reasons

    # Compare resolved vs expected
    ec = expected_category.strip().lower()
    rc = resolved.strip().lower()

    if ec == rc:
        return "consistent", reasons

    # Fuzzy match: one contains the other
    if ec in rc or rc in ec:
        return "consistent", reasons

    # Known mismatch between expected_category (unreliable) and resolved (from DR)
    # Since expected_category is 92% wrong, conflict is informational, not blocking
    reasons.append(f"category_expected_vs_resolved_conflict:{ec}!={rc}")
    return "inconsistent", reasons


# ── Main gate ───────────────────────────────────────────────────────────────

def evaluate_identity_gate(
    *,
    expected_brand: str,
    expected_subbrand: str = "",
    found_brand: str = "",
    expected_category: str = "",
    found_category: str = "",
    product_category: str = "",
    identity_confirmed: Optional[bool] = None,
    pn_match_location: str = "",
    pn_confidence: float = 0.0,
) -> IdentityGateResult:
    """Evaluate full identity gate.

    Gate logic:
      - brand_mismatch → BLOCK (hard gate)
      - brand_unknown + pn_unknown → BLOCK
      - brand_unknown + pn_exact → REVIEW (degraded but usable)
      - brand_confirmed/ecosystem + pn_exact → PASS
      - brand_confirmed/ecosystem + pn_ambiguous → REVIEW
      - category inconsistency → does NOT block alone (expected_category unreliable)
        but adds reason code
    """
    result = IdentityGateResult()

    # 1. Brand evaluation
    brand_status, brand_reasons = evaluate_brand_match(
        expected_brand=expected_brand,
        found_brand=found_brand,
        expected_subbrand=expected_subbrand,
    )
    result.brand_match_status = brand_status
    result.reason_codes.extend(brand_reasons)

    # 2. PN evaluation
    pn_status, pn_reasons = evaluate_pn_match(
        identity_confirmed=identity_confirmed,
        pn_match_location=pn_match_location,
        pn_confidence=pn_confidence,
    )
    result.pn_match_status = pn_status
    result.reason_codes.extend(pn_reasons)

    # 3. Category evaluation (advisory — does not block on its own)
    cat_status, cat_reasons = evaluate_category_match(
        expected_category=expected_category,
        found_category=found_category,
        product_category=product_category,
    )
    result.category_match_status = cat_status
    result.reason_codes.extend(cat_reasons)

    # 4. Gate decision
    if brand_status == "mismatch":
        result.gate_result = "block"
        result.reason_codes.append("brand_guard_block")
        result.identity_resolved = False
        return result

    if brand_status in ("confirmed", "ecosystem_match") and pn_status == "exact":
        result.gate_result = "pass"
        result.identity_resolved = True
        if cat_status == "inconsistent":
            result.reason_codes.append("category_advisory_conflict")
        return result

    if brand_status in ("confirmed", "ecosystem_match") and pn_status == "ambiguous":
        result.gate_result = "review"
        result.reason_codes.append("brand_ok_pn_ambiguous")
        result.identity_resolved = False
        return result

    if brand_status == "unknown" and pn_status == "exact":
        result.gate_result = "review"
        result.reason_codes.append("brand_unknown_pn_exact")
        result.identity_resolved = False
        return result

    # Default: block
    result.gate_result = "block"
    result.reason_codes.append("insufficient_identity_signals")
    result.identity_resolved = False
    return result
