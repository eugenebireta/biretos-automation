"""Pipeline v2 Canonical Builder (Layer 5).

Materializes CanonicalProduct from IdentityCapsule + BoundEvidence[].
Selects best_* per field by trust_tier > confidence > freshness.

Source of truth: docs/PIPELINE_ARCHITECTURE_v2.md section 8.

This is a PROJECTION — always rebuilt from evidence, never hand-edited.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .enums import (
    EvidenceField,
    FieldAdmissibility,
    ReadinessStatus,
    SourceTier,
)
from .models import (
    BoundEvidence,
    CanonicalIdentity,
    CanonicalProduct,
    CanonicalSpecs,
    CategorySignalEntry,
    DocumentEntry,
    EvidenceStats,
    IdentityCapsule,
    PhotoSetEntry,
    PlatformReadiness,
    TrustedSourceEntry,
)


# Tier ranking for selection (lower = better)
_TIER_RANK = {
    SourceTier.MANUFACTURER_PROOF: 0,
    SourceTier.AUTHORIZED_DISTRIBUTOR: 1,
    SourceTier.INDUSTRIAL_DISTRIBUTOR: 2,
    SourceTier.ORGANIC_DISCOVERY: 3,
    SourceTier.DENYLIST: 99,
}


def _sort_key(ev: BoundEvidence) -> tuple:
    """Sort key: best tier first, then freshest."""
    return (
        _TIER_RANK.get(ev.source_tier, 50),
        -(ev.collected_at.timestamp() if ev.collected_at else 0),
    )


def build_canonical(
    capsule: IdentityCapsule,
    evidence: list[BoundEvidence],
    candidate_count: int = 0,
    rejected_count: int = 0,
    trigger: str = "manual",
    assembled_title: str = "",
    seed_name: str = "",
    dr_title_ru: str = "",
) -> CanonicalProduct:
    """Build CanonicalProduct from capsule + bound evidence.

    Selection rule per field: best trust_tier > freshest collected_at.
    Pack prices are divided by pack_qty before selection.
    """
    now = datetime.now(timezone.utc)

    # Partition evidence by field, only admitted
    prices = sorted(
        [e for e in evidence
         if e.field == EvidenceField.PRICE
         and e.field_admissibility.price == FieldAdmissibility.ADMITTED],
        key=_sort_key,
    )
    photos = sorted(
        [e for e in evidence
         if e.field == EvidenceField.PHOTO
         and e.field_admissibility.photo == FieldAdmissibility.ADMITTED],
        key=_sort_key,
    )
    descriptions = sorted(
        [e for e in evidence
         if e.field == EvidenceField.DESCRIPTION
         and e.field_admissibility.description == FieldAdmissibility.ADMITTED],
        key=_sort_key,
    )
    specs_list = sorted(
        [e for e in evidence
         if e.field == EvidenceField.SPECS
         and e.field_admissibility.specs == FieldAdmissibility.ADMITTED],
        key=_sort_key,
    )
    cat_signals = [e for e in evidence if e.field == EvidenceField.CATEGORY_SIGNAL]
    docs = [e for e in evidence if e.field == EvidenceField.DOCUMENT]

    # --- Best price ---
    best_price = None
    best_price_currency = None
    best_price_source = None
    best_price_tier = None
    best_price_evidence_id = None

    for ev in prices:
        val = ev.value
        amount = val.get("amount")
        if amount is None:
            continue
        pack_qty = val.get("pack_qty")
        if pack_qty and pack_qty > 1:
            amount = amount / pack_qty  # divide pack price to unit
        if best_price is None or _TIER_RANK.get(ev.source_tier, 50) < _TIER_RANK.get(best_price_tier, 50):
            best_price = round(amount, 2)
            best_price_currency = val.get("currency")
            best_price_source = ev.source_domain
            best_price_tier = ev.source_tier
            best_price_evidence_id = ev.evidence_id

    # --- Best photo ---
    best_photo_url = None
    best_photo_tier = None
    best_photo_evidence_id = None
    photo_set: list[PhotoSetEntry] = []

    for i, ev in enumerate(photos):
        url = ev.value.get("url", "")
        if not url:
            continue
        if i == 0:
            best_photo_url = url
            best_photo_tier = ev.source_tier
            best_photo_evidence_id = ev.evidence_id
            photo_set.append(PhotoSetEntry(url=url, source=ev.source_domain, role="main"))
        else:
            photo_set.append(PhotoSetEntry(url=url, source=ev.source_domain, role="gallery"))

    # --- Best description ---
    best_description_ru = None
    best_description_tier = None

    for ev in descriptions:
        text = ev.value.get("text", "")
        lang = ev.value.get("lang", "")
        if text and len(text) >= 30:
            if lang in ("ru", ""):
                best_description_ru = text
                best_description_tier = ev.source_tier
                break

    # If no Russian, take any
    if not best_description_ru and descriptions:
        ev = descriptions[0]
        best_description_ru = ev.value.get("text", "")
        best_description_tier = ev.source_tier

    # --- Specs (merge all) ---
    merged_specs: dict = {}
    weight_g = None
    length_mm = None
    width_mm = None
    height_mm = None
    color_canonical = None
    material = None
    ip_rating = None

    for ev in specs_list:
        parsed = ev.value.get("parsed") or {}
        for k, v in parsed.items():
            if v and k not in merged_specs:
                merged_specs[k] = v
        # Extract normalized values
        nv = ev.value_normalized or {}
        if nv.get("weight_g") and not weight_g:
            weight_g = nv["weight_g"]
        if nv.get("length_mm") and not length_mm:
            length_mm = nv["length_mm"]
        if nv.get("width_mm") and not width_mm:
            width_mm = nv["width_mm"]
        if nv.get("height_mm") and not height_mm:
            height_mm = nv["height_mm"]
        if nv.get("color_canonical") and not color_canonical:
            color_canonical = nv["color_canonical"]
        if nv.get("material") and not material:
            material = nv["material"]
        if nv.get("ip_rating") and not ip_rating:
            ip_rating = nv["ip_rating"]

    specs = CanonicalSpecs(
        weight_g=weight_g,
        length_mm=length_mm,
        width_mm=width_mm,
        height_mm=height_mm,
        color_canonical=color_canonical,
        material=material,
        ip_rating=ip_rating,
        raw_merged=merged_specs,
    )

    # --- Category ---
    category_signals_out = [
        CategorySignalEntry(path=ev.value.get("source_category_path", ""), source=ev.source_domain)
        for ev in cat_signals if ev.value.get("source_category_path")
    ]

    # --- Documents ---
    documents_out = [
        DocumentEntry(type=ev.value.get("type", ""), url=ev.value.get("url", ""), source=ev.source_domain)
        for ev in docs if ev.value.get("url")
    ]

    # --- Trusted sources (aggregate) ---
    source_capabilities: dict[str, dict] = {}
    for ev in evidence:
        dom = ev.source_domain
        if dom not in source_capabilities:
            source_capabilities[dom] = {"domain": dom, "tier": ev.source_tier, "has": set()}
        source_capabilities[dom]["has"].add(ev.field.value)

    trusted_sources = [
        TrustedSourceEntry(domain=v["domain"], tier=v["tier"], has=sorted(v["has"]))
        for v in sorted(source_capabilities.values(), key=lambda x: _TIER_RANK.get(x["tier"], 50))
    ]

    # --- Readiness ---
    readiness = _compute_readiness(
        best_price=best_price,
        best_photo_url=best_photo_url,
        best_description_ru=best_description_ru,
        ean=capsule.ean,
        weight_g=weight_g,
        specs=specs,
    )

    # --- Title ---
    # Priority: dr_title_ru > assembled_title > seed_name > description first sentence > fallback
    title_ru = None

    if dr_title_ru and len(dr_title_ru) > 5 and dr_title_ru.lower() != "unknown":
        title_ru = dr_title_ru[:150]
    elif assembled_title and len(assembled_title) > 5:
        title_ru = assembled_title[:150]
    elif seed_name and len(seed_name) > 5:
        title_ru = seed_name[:150]
    else:
        # Last resort: first sentence of best description
        for ev in descriptions:
            text = ev.value.get("text", "")
            if text and len(text) > 10:
                first_sentence = text.split(".")[0].strip()
                if len(first_sentence) > 10:
                    title_ru = first_sentence[:150]
                break

    # Absolute fallback
    if not title_ru:
        brand_str = capsule.confirmed_brand
        pn_str = capsule.confirmed_pn
        pt = capsule.product_type or ""
        title_ru = f"{pt} {brand_str} {pn_str}".strip() if pt else f"{brand_str} {pn_str}"

    return CanonicalProduct(
        identity_hash=capsule.identity_hash,
        capsule_version=capsule.version,
        built_at=now,
        build_trigger=trigger,
        identity=CanonicalIdentity(
            brand=capsule.confirmed_brand,
            pn=capsule.confirmed_pn,
            manufacturer=capsule.manufacturer_namespace,
            product_type=capsule.product_type,
            series=capsule.series,
            ean=capsule.ean,
        ),
        title_ru=title_ru,
        best_price=best_price,
        best_price_currency=best_price_currency,
        best_price_source=best_price_source,
        best_price_tier=best_price_tier,
        best_price_evidence_id=best_price_evidence_id,
        best_photo_url=best_photo_url,
        best_photo_tier=best_photo_tier,
        best_photo_evidence_id=best_photo_evidence_id,
        photo_set=photo_set,
        best_description_ru=best_description_ru,
        best_description_tier=best_description_tier,
        specs=specs,
        canonical_category=None,  # set by category mapper later
        category_signals=category_signals_out,
        documents=documents_out,
        trusted_sources=trusted_sources,
        readiness=readiness,
        evidence_stats=EvidenceStats(
            bound_count=len(evidence),
            candidate_count=candidate_count,
            rejected_count=rejected_count,
        ),
    )


def _compute_readiness(
    best_price: float | None,
    best_photo_url: str | None,
    best_description_ru: str | None,
    ean: str | None,
    weight_g: int | None,
    specs: CanonicalSpecs,
) -> PlatformReadiness:
    """Compute per-platform readiness status."""

    # InSales: title + price + description -> READY (photo/weight optional)
    if best_price and best_description_ru:
        insales = ReadinessStatus.READY
    elif best_price:
        insales = ReadinessStatus.DRAFT
    else:
        insales = ReadinessStatus.BLOCKED_NO_PRICE

    # Ozon: title + price + description + EAN + weight + dimensions + category
    if not best_price:
        ozon = ReadinessStatus.BLOCKED_NO_PRICE
    elif not ean:
        ozon = ReadinessStatus.BLOCKED_NO_EAN
    elif not weight_g:
        ozon = ReadinessStatus.BLOCKED_NO_WEIGHT
    elif not best_photo_url:
        ozon = ReadinessStatus.BLOCKED_NO_PHOTO
    else:
        ozon = ReadinessStatus.READY

    # WB: similar to Ozon
    if not best_price:
        wb = ReadinessStatus.BLOCKED_NO_PRICE
    elif not ean:
        wb = ReadinessStatus.BLOCKED_NO_EAN
    elif not weight_g:
        wb = ReadinessStatus.BLOCKED_NO_WEIGHT
    else:
        wb = ReadinessStatus.READY

    return PlatformReadiness(insales=insales, ozon=ozon, wb=wb)
