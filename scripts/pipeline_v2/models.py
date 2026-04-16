"""Pipeline v2 Pydantic contracts — all data models.

Source of truth: docs/PIPELINE_ARCHITECTURE_v2.md section 7.
Generated mechanically from frozen spec. Do not hand-edit fields
without updating the spec first.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    BindingStatus,
    BrandMatch,
    EvidenceField,
    FieldAdmissibility,
    IdentityClass,
    IdentityVerdict,
    OriginGroup,
    PackagingType,
    PageType,
    Platform,
    PNMatch,
    ProductTypeMatch,
    ReadinessStatus,
    ReviewBucketType,
    ReviewPriority,
    ReviewQueueType,
    SourceTier,
)


# ── 7.1 Candidate Identity Records ─────────────────────────────────────────


class CandidateIdentityRecord(BaseModel):
    """Raw observation from Layer 1 scouting. NOT confirmed. NOT truth."""

    record_id: str
    search_batch_id: str | None = None
    requested_pn: str
    requested_brand_hint: str | None = None

    # Source
    source_url: str
    source_domain: str
    source_tier: SourceTier
    page_type: PageType
    origin_group: OriginGroup

    # Extracted data
    extracted_pn: str | None = None
    extracted_brand: str | None = None
    extracted_mpn: str | None = None
    extracted_ean: str | None = None
    extracted_title: str | None = None
    extracted_product_type: str | None = None
    extracted_category_path: str | None = None

    # Match assessment
    pn_match: PNMatch = PNMatch.ABSENT
    brand_match: BrandMatch = BrandMatch.ABSENT
    product_type_match: ProductTypeMatch = ProductTypeMatch.UNKNOWN
    negative_evidence: list[str] = Field(default_factory=list)

    # Score (for ranking within same verdict only)
    identity_score: float = 0.0

    collected_at: datetime
    collected_by: str


# ── 7.2 Identity Capsule ───────────────────────────────────────────────────


class ConfirmedSource(BaseModel):
    """Source that contributed to identity confirmation."""

    url: str
    domain: str
    tier: SourceTier
    page_type: PageType
    origin_group: OriginGroup
    candidate_record_id: str


class CapsuleConstraints(BaseModel):
    """Rules that guide enrichment for this specific capsule."""

    required_anchor_for_numeric: bool = False
    forbidden_page_types: list[PageType] = Field(default_factory=list)
    min_source_tier_for_price: SourceTier = SourceTier.INDUSTRIAL_DISTRIBUTOR
    accept_marketplace_photos: bool = False


class IdentityCapsule(BaseModel):
    """Frozen passport of confirmed product. Immutable after frozen_at.

    Invariant: identity_hash = sha256(confirmed_brand|normalized_pn|manufacturer_namespace).
    Does NOT include product_type, series, EAN, or version in hash.
    Changes create new version (superseded_by), never mutate in place.
    """

    model_config = ConfigDict(frozen=True)

    identity_hash: str
    identity_key: str  # "BRAND|PN|NAMESPACE"
    version: int = 1
    superseded_by: int | None = None
    frozen_at: datetime

    confirmed_brand: str
    confirmed_pn: str
    normalized_pn: str
    manufacturer_namespace: str

    product_type: str | None = None
    series: str | None = None
    identity_class: IdentityClass = IdentityClass.NORMAL

    allowed_brand_aliases: list[str] = Field(default_factory=list)
    allowed_pn_aliases: list[str] = Field(default_factory=list)
    allowed_series_aliases: list[str] = Field(default_factory=list)
    ean: str | None = None

    verdict: IdentityVerdict = IdentityVerdict.CONFIRMED
    decision_path: list[str] = Field(default_factory=list)

    confirmed_sources: list[ConfirmedSource] = Field(default_factory=list)
    capsule_constraints: CapsuleConstraints = Field(default_factory=CapsuleConstraints)

    packaging: PackagingType = PackagingType.SINGLE
    known_pack_sizes: list[int] = Field(default_factory=list)
    variant_key: str | None = None


# ── 7.3 Identity Resolution Events ─────────────────────────────────────────


class ReviewerOverride(BaseModel):
    """Manual override by human reviewer."""

    reviewer: str
    override_at: datetime
    original_verdict: IdentityVerdict
    new_verdict: IdentityVerdict
    reason: str


class IdentityResolutionEvent(BaseModel):
    """Append-only log entry. Documents HOW resolver reached verdict."""

    event_id: str
    identity_key: str
    timestamp: datetime

    candidate_set: list[str]  # record_ids considered
    hard_vetoes: list[dict[str, str]] = Field(default_factory=list)
    independence_groups: dict[str, list[str]] = Field(default_factory=dict)
    cross_validation_result: str | None = None
    final_verdict: IdentityVerdict
    verdict_reason: str
    capsule_version_created: int | None = None
    reviewer_override: ReviewerOverride | None = None


# ── 7.4 Bound Evidence ─────────────────────────────────────────────────────


class BindingChecks(BaseModel):
    """Record of what re-bind check evaluated."""

    pn_match: str
    brand_match: str
    negative_evidence: str = "none"
    page_type_allowed: bool = True


class FieldAdmissibilityRecord(BaseModel):
    """Per-field admission decision for this evidence."""

    price: FieldAdmissibility = FieldAdmissibility.NOT_AVAILABLE
    photo: FieldAdmissibility = FieldAdmissibility.NOT_AVAILABLE
    description: FieldAdmissibility = FieldAdmissibility.NOT_AVAILABLE
    specs: FieldAdmissibility = FieldAdmissibility.NOT_AVAILABLE


class BoundEvidence(BaseModel):
    """Data that passed re-bind check. Linked to capsule via identity_hash.

    Invariant: No evidence without identity_hash enters canonical product.
    """

    evidence_id: str
    identity_hash: str
    capsule_version: int
    field: EvidenceField

    value: dict[str, Any]  # field-specific structure
    value_normalized: dict[str, Any] | None = None

    source_url: str
    source_domain: str
    source_tier: SourceTier
    page_type: PageType
    origin_group: OriginGroup

    binding_status: BindingStatus = BindingStatus.BOUND
    binding_reason: str
    binding_checks: BindingChecks

    field_admissibility: FieldAdmissibilityRecord = Field(
        default_factory=FieldAdmissibilityRecord
    )

    collected_at: datetime
    collected_by: str
    expires_at: datetime | None = None  # TTL for prices


# ── 7.5 Candidate Enrichment ───────────────────────────────────────────────


class RejectionDetails(BaseModel):
    """Why re-bind check rejected this evidence."""

    pn_match: str | None = None
    brand_match: str | None = None
    source_tier: str | None = None
    page_type: str | None = None
    negative_evidence: list[str] = Field(default_factory=list)


class CandidateEnrichment(BaseModel):
    """Evidence that FAILED re-bind check. Stored for review and learning.

    Invariant: Candidate enrichment is NEVER lost. Always stored with reason.
    """

    candidate_id: str
    identity_hash: str
    field: str
    value: dict[str, Any]

    source_url: str
    source_domain: str
    source_tier: SourceTier

    rejection_reason: str
    rejection_details: RejectionDetails = Field(default_factory=RejectionDetails)

    collected_at: datetime


# ── 7.6 Canonical Product ──────────────────────────────────────────────────


class CanonicalIdentity(BaseModel):
    """Identity subset copied from capsule for convenience."""

    brand: str
    pn: str
    manufacturer: str
    product_type: str | None = None
    series: str | None = None
    ean: str | None = None


class PhotoSetEntry(BaseModel):
    url: str
    source: str
    role: str  # main / gallery


class TrustedSourceEntry(BaseModel):
    domain: str
    tier: SourceTier
    has: list[str]  # ["price", "photo", "specs"]


class CategorySignalEntry(BaseModel):
    path: str
    source: str


class DocumentEntry(BaseModel):
    type: str  # datasheet / brochure / certificate
    url: str
    source: str


class CanonicalSpecs(BaseModel):
    """Merged specs from all bound evidence. Normalized units."""

    weight_g: int | None = None
    length_mm: int | None = None
    width_mm: int | None = None
    height_mm: int | None = None
    color_canonical: str | None = None
    material: str | None = None
    ip_rating: str | None = None
    raw_merged: dict[str, Any] = Field(default_factory=dict)


class PlatformReadiness(BaseModel):
    insales: ReadinessStatus = ReadinessStatus.DRAFT
    ozon: ReadinessStatus = ReadinessStatus.DRAFT
    wb: ReadinessStatus = ReadinessStatus.DRAFT


class EvidenceStats(BaseModel):
    bound_count: int = 0
    candidate_count: int = 0
    rejected_count: int = 0


class CanonicalProduct(BaseModel):
    """Materialized projection from capsule + bound_evidence.

    Invariant: Always rebuilt from evidence. Never hand-edited.
    Truth is in capsule + bound_evidence, not here.
    """

    identity_hash: str
    capsule_version: int
    built_at: datetime
    build_trigger: str = "manual"

    identity: CanonicalIdentity

    # Best selections (by trust_tier > confidence > freshness)
    title_ru: str | None = None
    title_en: str | None = None

    best_price: float | None = None
    best_price_currency: str | None = None
    best_price_source: str | None = None
    best_price_tier: SourceTier | None = None
    best_price_evidence_id: str | None = None

    best_photo_url: str | None = None
    best_photo_tier: SourceTier | None = None
    best_photo_evidence_id: str | None = None
    photo_set: list[PhotoSetEntry] = Field(default_factory=list)

    best_description_ru: str | None = None
    best_description_tier: SourceTier | None = None

    specs: CanonicalSpecs = Field(default_factory=CanonicalSpecs)
    canonical_category: str | None = None
    category_signals: list[CategorySignalEntry] = Field(default_factory=list)
    documents: list[DocumentEntry] = Field(default_factory=list)
    trusted_sources: list[TrustedSourceEntry] = Field(default_factory=list)

    readiness: PlatformReadiness = Field(default_factory=PlatformReadiness)
    evidence_stats: EvidenceStats = Field(default_factory=EvidenceStats)


# ── 7.7 Platform Listing Drafts ────────────────────────────────────────────


class RequirementsSnapshot(BaseModel):
    """Version of platform rules used to validate this draft."""

    snapshot_version: str
    required_fields: list[str] = Field(default_factory=list)
    category_mapping_version: str | None = None


class PlatformListingDraft(BaseModel):
    """Platform-specific card. Generated from canonical + platform rules.

    Invariant: Listing cannot publish if canonical product not stabilised.
    """

    platform: Platform
    identity_hash: str
    status: ReadinessStatus = ReadinessStatus.DRAFT
    generated_at: datetime

    requirements_snapshot: RequirementsSnapshot
    listing: dict[str, Any]  # platform-specific fields

    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)


# ── 7.8 Review Buckets ─────────────────────────────────────────────────────


class ReviewBucket(BaseModel):
    """Queue item for human decision. Typed by owner_queue_type."""

    bucket_id: str
    identity_key: str  # "brand|pn|namespace", NOT bare pn
    identity_hash: str | None = None  # null for pre-capsule reviews
    owner_queue_type: ReviewQueueType
    bucket_type: ReviewBucketType
    reason: str
    priority: ReviewPriority = ReviewPriority.MEDIUM
    candidates: list[str] = Field(default_factory=list)
    created_at: datetime
    resolved: bool = False
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution: str | None = None
