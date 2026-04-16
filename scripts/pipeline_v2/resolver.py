"""Pipeline v2 Identity Resolver (Layer 2).

Evaluates candidate_identity_records and produces verdict:
CONFIRMED / WEAK / CONFLICT / REJECTED.

Creates IdentityCapsule when CONFIRMED.
Logs IdentityResolutionEvent for every resolution attempt.

Source of truth: docs/PIPELINE_ARCHITECTURE_v2.md section 4.

Hard rules first, score second. Verdict rules:
- CONFIRMED: exact PN + exact/alias brand + no veto + strong source + extra anchor for numeric
- WEAK: partial conditions met but insufficient proof
- CONFLICT: two strong candidates with incompatible verdict roots
- REJECTED: hard mismatch / wrong page / explicit other product
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .enums import (
    BrandMatch,
    IdentityClass,
    IdentityVerdict,
    OriginGroup,
    PageType,
    PNMatch,
    ProductTypeMatch,
    SourceTier,
)
from .identity import (
    compute_identity_hash,
    compute_identity_key,
    normalize_brand,
    normalize_pn,
)
from .models import (
    CandidateIdentityRecord,
    CapsuleConstraints,
    ConfirmedSource,
    IdentityCapsule,
    IdentityResolutionEvent,
)


# Page types that can confirm identity
_CONFIRMABLE_PAGE_TYPES = {
    PageType.PRODUCT_PAGE,
    PageType.DATASHEET,
    PageType.CATALOG_PAGE,
}

# Tier strength ranking (lower index = stronger)
_TIER_STRENGTH = [
    SourceTier.MANUFACTURER_PROOF,
    SourceTier.AUTHORIZED_DISTRIBUTOR,
    SourceTier.INDUSTRIAL_DISTRIBUTOR,
    SourceTier.MARKETPLACE_FALLBACK,
    SourceTier.ORGANIC_DISCOVERY,
    SourceTier.DENYLIST,
]


def _tier_rank(tier: SourceTier) -> int:
    try:
        return _TIER_STRENGTH.index(tier)
    except ValueError:
        return 99


def _is_strong_source(rec: CandidateIdentityRecord) -> bool:
    """A record is 'strong' if it has exact PN + brand match from a confirmable page.

    Marketplace (TIER4) and organic sources are NOT strong — they can provide
    data but cannot confirm identity on their own.
    """
    return (
        rec.pn_match in (PNMatch.EXACT, PNMatch.NORMALIZED)
        and rec.brand_match in (BrandMatch.EXACT, BrandMatch.ALIAS)
        and rec.page_type in _CONFIRMABLE_PAGE_TYPES
        and not rec.negative_evidence
        and rec.source_tier in (
            SourceTier.MANUFACTURER_PROOF,
            SourceTier.AUTHORIZED_DISTRIBUTOR,
            SourceTier.INDUSTRIAL_DISTRIBUTOR,
        )
    )


def _compute_independence_groups(
    records: list[CandidateIdentityRecord],
) -> dict[str, list[str]]:
    """Group records by origin to count independent confirmations.

    Two sources from same origin_group count as ONE confirmation.
    Each distributor domain is its own group.
    """
    groups: dict[str, list[str]] = {}
    for rec in records:
        if rec.origin_group == OriginGroup.DISTRIBUTOR:
            key = f"distributor:{rec.source_domain}"
        else:
            key = rec.origin_group.value
        groups.setdefault(key, []).append(rec.record_id)
    return groups


def _has_extra_anchor(records: list[CandidateIdentityRecord]) -> bool:
    """Check if numeric PN has required extra anchor.

    Extra anchor = EAN found, or manufacturer page, or datasheet.
    """
    for rec in records:
        if not _is_strong_source(rec):
            continue
        if rec.source_tier == SourceTier.MANUFACTURER_PROOF:
            return True
        if rec.page_type == PageType.DATASHEET:
            return True
        if rec.extracted_ean:
            return True
    return False


def _detect_conflicts(
    strong_records: list[CandidateIdentityRecord],
) -> list[tuple[CandidateIdentityRecord, CandidateIdentityRecord]]:
    """Find pairs of strong records with incompatible brands or product types."""
    conflicts = []
    for i, a in enumerate(strong_records):
        for b in strong_records[i + 1:]:
            # Brand conflict
            if (a.extracted_brand and b.extracted_brand
                    and normalize_brand(a.extracted_brand) != normalize_brand(b.extracted_brand)):
                conflicts.append((a, b))
                continue
            # Product type conflict
            if (a.extracted_product_type and b.extracted_product_type
                    and a.product_type_match == ProductTypeMatch.EXACT
                    and b.product_type_match == ProductTypeMatch.EXACT
                    and a.extracted_product_type.lower() != b.extracted_product_type.lower()):
                conflicts.append((a, b))
    return conflicts


def resolve_identity(
    requested_pn: str,
    requested_brand_hint: str,
    candidates: list[CandidateIdentityRecord],
) -> tuple[IdentityVerdict, IdentityCapsule | None, IdentityResolutionEvent]:
    """Execute identity resolution per spec section 4.

    Returns:
        verdict: CONFIRMED / WEAK / CONFLICT / REJECTED
        capsule: IdentityCapsule if CONFIRMED, else None
        event: IdentityResolutionEvent (always, for audit log)
    """
    event_id = f"ire_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    # Filter out denylist and rejected records
    valid = [c for c in candidates
             if c.source_tier != SourceTier.DENYLIST and not c.negative_evidence]
    [c for c in candidates if c not in valid]

    hard_vetoes = [
        {"record_id": r.record_id, "reason": f"denylist:{r.source_domain}"}
        for r in candidates if r.source_tier == SourceTier.DENYLIST
    ] + [
        {"record_id": r.record_id, "reason": f"negative_evidence:{r.negative_evidence[0]}"}
        for r in candidates if r.negative_evidence
    ]

    # Find strong records (exact PN + brand + confirmable page)
    strong = [r for r in valid if _is_strong_source(r)]

    # Check for conflicts among strong records
    conflicts = _detect_conflicts(strong)

    # Independence groups
    strong_groups = _compute_independence_groups(strong)

    # Determine identity class
    norm_pn = normalize_pn(requested_pn)
    is_numeric = requested_pn.replace("-", "").replace(".", "").replace("/", "").isdigit()
    short_pn = len(requested_pn.replace("-", "").replace(".", "")) <= 8
    identity_class = IdentityClass.NUMERIC_STRICT if (is_numeric and short_pn) else IdentityClass.NORMAL

    # --- CONFLICT ---
    if conflicts:
        a, b = conflicts[0]
        identity_key = compute_identity_key(requested_brand_hint, norm_pn, requested_brand_hint)
        event = IdentityResolutionEvent(
            event_id=event_id,
            identity_key=identity_key,
            timestamp=now,
            candidate_set=[c.record_id for c in candidates],
            hard_vetoes=hard_vetoes,
            independence_groups=strong_groups,
            cross_validation_result=f"CONFLICT:{a.extracted_brand}_vs_{b.extracted_brand}",
            final_verdict=IdentityVerdict.CONFLICT,
            verdict_reason=f"Two strong candidates disagree: {a.source_domain} vs {b.source_domain}",
        )
        return IdentityVerdict.CONFLICT, None, event

    # --- No strong records at all ---
    if not strong:
        identity_key = compute_identity_key(requested_brand_hint, norm_pn, requested_brand_hint)

        # REJECTED if nothing useful at all
        if not valid:
            event = IdentityResolutionEvent(
                event_id=event_id,
                identity_key=identity_key,
                timestamp=now,
                candidate_set=[c.record_id for c in candidates],
                hard_vetoes=hard_vetoes,
                independence_groups={},
                final_verdict=IdentityVerdict.REJECTED,
                verdict_reason="No valid candidates after filtering",
            )
            return IdentityVerdict.REJECTED, None, event

        # WEAK if some valid but none strong
        event = IdentityResolutionEvent(
            event_id=event_id,
            identity_key=identity_key,
            timestamp=now,
            candidate_set=[c.record_id for c in candidates],
            hard_vetoes=hard_vetoes,
            independence_groups=_compute_independence_groups(valid),
            final_verdict=IdentityVerdict.WEAK,
            verdict_reason="Valid candidates exist but none meet strong confirmation criteria",
        )
        return IdentityVerdict.WEAK, None, event

    # --- Check confirmation rules ---
    # Pick the best strong record as primary
    primary = sorted(strong, key=lambda r: _tier_rank(r.source_tier))[0]

    # Determine confirmed brand and manufacturer
    confirmed_brand = primary.extracted_brand or requested_brand_hint
    manufacturer_ns = confirmed_brand  # default: brand = manufacturer

    # Cross-validation: count independent strong groups
    n_independent = len(strong_groups)
    has_tier1 = any(r.source_tier == SourceTier.MANUFACTURER_PROOF for r in strong)
    has_tier2 = sum(1 for r in strong if r.source_tier == SourceTier.AUTHORIZED_DISTRIBUTOR)
    has_tier3 = sum(1 for r in strong if r.source_tier == SourceTier.INDUSTRIAL_DISTRIBUTOR)

    # Count independent tier2+ groups
    independent_tier2_groups = sum(
        1 for k, v in strong_groups.items()
        if any(candidates_by_id(candidates, rid).source_tier
               in (SourceTier.MANUFACTURER_PROOF, SourceTier.AUTHORIZED_DISTRIBUTOR)
               for rid in v)
    )

    decision_path = []
    confirmed = False

    # Rule: 1x TIER 1 alone is enough
    if has_tier1:
        decision_path.append("source_manufacturer_page")
        confirmed = True

    # Rule: 2x TIER 2 independent
    elif independent_tier2_groups >= 2:
        decision_path.append("cross_validated_2_independent_tier2")
        confirmed = True

    # Rule: 1x TIER 2 + 1x TIER 3
    elif has_tier2 >= 1 and has_tier3 >= 1 and n_independent >= 2:
        decision_path.append("cross_validated_tier2_plus_tier3")
        confirmed = True

    # Rule: 3x TIER 3 independent
    elif n_independent >= 3:
        decision_path.append("cross_validated_3_independent")
        confirmed = True

    # Numeric PN extra anchor check
    if confirmed and identity_class == IdentityClass.NUMERIC_STRICT:
        if not _has_extra_anchor(strong):
            confirmed = False
            decision_path.append("BLOCKED:numeric_no_extra_anchor")

    # Build decision path
    decision_path.insert(0, f"pn_{primary.pn_match.value}")
    decision_path.insert(1, f"brand_{primary.brand_match.value}")
    if primary.product_type_match != ProductTypeMatch.UNKNOWN:
        decision_path.append(f"product_type_{primary.product_type_match.value}")
    decision_path.append("no_negative_evidence")

    identity_key = compute_identity_key(confirmed_brand, norm_pn, manufacturer_ns)

    if not confirmed:
        event = IdentityResolutionEvent(
            event_id=event_id,
            identity_key=identity_key,
            timestamp=now,
            candidate_set=[c.record_id for c in candidates],
            hard_vetoes=hard_vetoes,
            independence_groups=strong_groups,
            cross_validation_result=f"insufficient:{n_independent}_independent_groups",
            final_verdict=IdentityVerdict.WEAK,
            verdict_reason=f"Strong records exist but cross-validation insufficient: {n_independent} independent groups",
        )
        return IdentityVerdict.WEAK, None, event

    # --- CONFIRMED: create capsule ---
    identity_hash = compute_identity_hash(confirmed_brand, norm_pn, manufacturer_ns)

    # Collect aliases from all strong records
    brand_aliases = set()
    pn_aliases = set()
    ean = None
    product_type = None
    series = None

    for rec in strong:
        if rec.extracted_brand and normalize_brand(rec.extracted_brand) != normalize_brand(confirmed_brand):
            brand_aliases.add(rec.extracted_brand)
        if rec.extracted_pn and normalize_pn(rec.extracted_pn) != norm_pn:
            pn_aliases.add(rec.extracted_pn)
        if rec.extracted_ean and not ean:
            ean = rec.extracted_ean
        if rec.extracted_product_type and not product_type:
            product_type = rec.extracted_product_type
    # Also add brand hint as alias if different
    if normalize_brand(requested_brand_hint) != normalize_brand(confirmed_brand):
        brand_aliases.add(requested_brand_hint)

    confirmed_sources = [
        ConfirmedSource(
            url=rec.source_url,
            domain=rec.source_domain,
            tier=rec.source_tier,
            page_type=rec.page_type,
            origin_group=rec.origin_group,
            candidate_record_id=rec.record_id,
        )
        for rec in strong
    ]

    # Capsule constraints based on identity class
    constraints = CapsuleConstraints(
        required_anchor_for_numeric=(identity_class == IdentityClass.NUMERIC_STRICT),
        forbidden_page_types=[PageType.CATEGORY_PAGE, PageType.SEARCH_RESULTS],
        min_source_tier_for_price=SourceTier.ORGANIC_DISCOVERY,  # accept all tiers for price (validated by re-bind PN+brand check)
        accept_marketplace_photos=False,
    )

    capsule = IdentityCapsule(
        identity_hash=identity_hash,
        identity_key=identity_key,
        version=1,
        frozen_at=now,
        confirmed_brand=confirmed_brand,
        confirmed_pn=requested_pn,
        normalized_pn=norm_pn,
        manufacturer_namespace=manufacturer_ns,
        product_type=product_type,
        series=series,
        identity_class=identity_class,
        allowed_brand_aliases=sorted(brand_aliases),
        allowed_pn_aliases=sorted(pn_aliases),
        ean=ean,
        verdict=IdentityVerdict.CONFIRMED,
        decision_path=decision_path,
        confirmed_sources=confirmed_sources,
        capsule_constraints=constraints,
    )

    event = IdentityResolutionEvent(
        event_id=event_id,
        identity_key=identity_key,
        timestamp=now,
        candidate_set=[c.record_id for c in candidates],
        hard_vetoes=hard_vetoes,
        independence_groups=strong_groups,
        cross_validation_result=f"CONFIRMED:{n_independent}_independent",
        final_verdict=IdentityVerdict.CONFIRMED,
        verdict_reason=f"Identity confirmed via {decision_path}",
        capsule_version_created=1,
    )

    return IdentityVerdict.CONFIRMED, capsule, event


def candidates_by_id(
    candidates: list[CandidateIdentityRecord], record_id: str,
) -> CandidateIdentityRecord:
    """Lookup candidate by record_id."""
    for c in candidates:
        if c.record_id == record_id:
            return c
    raise KeyError(f"No candidate with record_id={record_id}")
