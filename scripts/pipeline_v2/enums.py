"""Pipeline v2 enums — all status/type enumerations.

Source of truth: docs/PIPELINE_ARCHITECTURE_v2.md sections 4, 5, 6, 7.
"""
from __future__ import annotations

from enum import Enum


# --- Trust & Source ---

class SourceTier(str, Enum):
    MANUFACTURER_PROOF = "manufacturer_proof"
    AUTHORIZED_DISTRIBUTOR = "authorized_distributor"
    INDUSTRIAL_DISTRIBUTOR = "industrial_distributor"
    MARKETPLACE_FALLBACK = "marketplace_fallback"
    ORGANIC_DISCOVERY = "organic_discovery"
    DENYLIST = "denylist"


class PageType(str, Enum):
    PRODUCT_PAGE = "product_page"
    DATASHEET = "datasheet"
    CATALOG_PAGE = "catalog_page"
    CATEGORY_PAGE = "category_page"
    SEARCH_RESULTS = "search_results"
    MARKETPLACE_OFFER = "marketplace_offer"
    PDF_BROCHURE = "pdf_brochure"
    IMAGE_ASSET = "image_asset"


class OriginGroup(str, Enum):
    MANUFACTURER = "manufacturer"
    DISTRIBUTOR = "distributor"
    MARKETPLACE = "marketplace"
    CACHED_COPY = "cached_copy"
    RESELLER_CLONE = "reseller_clone"
    AI_EXTRACTION = "ai_extraction"


# --- Identity ---

class PNMatch(str, Enum):
    EXACT = "exact"
    NORMALIZED = "normalized"
    ALIAS = "alias"
    PARTIAL = "partial"
    MISMATCH = "mismatch"
    ABSENT = "absent"


class BrandMatch(str, Enum):
    EXACT = "exact"
    ALIAS = "alias"
    AMBIGUOUS = "ambiguous"
    MISMATCH = "mismatch"
    ABSENT = "absent"


class ProductTypeMatch(str, Enum):
    EXACT = "exact"
    COMPATIBLE = "compatible"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


class IdentityVerdict(str, Enum):
    CONFIRMED = "CONFIRMED"
    WEAK = "WEAK"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"


class IdentityClass(str, Enum):
    NORMAL = "normal"
    NUMERIC_STRICT = "numeric_strict"


# --- Evidence ---

class EvidenceField(str, Enum):
    PRICE = "price"
    PHOTO = "photo"
    DESCRIPTION = "description"
    SPECS = "specs"
    CATEGORY_SIGNAL = "category_signal"
    DOCUMENT = "document"


class FieldAdmissibility(str, Enum):
    ADMITTED = "admitted"
    NOT_ADMITTED = "not_admitted"
    NOT_AVAILABLE = "not_available"


class BindingStatus(str, Enum):
    BOUND = "bound"


# --- Packaging ---

class PackagingType(str, Enum):
    SINGLE = "single"
    PACK = "pack"


# --- Pipeline ---

class PipelineStatus(str, Enum):
    PENDING = "pending"
    SCOUTING = "scouting"
    RESOLVING_IDENTITY = "resolving_identity"
    ENRICHING = "enriching"
    BUILDING_CANONICAL = "building_canonical"
    LISTING_READY = "listing_ready"
    ARCHIVED = "archived"


# --- Review ---

class ReviewQueueType(str, Enum):
    IDENTITY_REVIEW = "identity_review"
    EVIDENCE_REVIEW = "evidence_review"
    MARKETPLACE_MAPPING_REVIEW = "marketplace_mapping_review"
    PRICING_REVIEW = "pricing_review"


class ReviewBucketType(str, Enum):
    IDENTITY_CONFLICT = "identity_conflict"
    IDENTITY_WEAK = "identity_weak"
    ENRICHMENT_STARVATION = "enrichment_starvation"
    PRICE_PACK_AMBIGUITY = "price_pack_ambiguity"
    PHOTO_WRONG_PRODUCT = "photo_wrong_product"
    CATEGORY_MAPPING_MISSING = "category_mapping_missing"
    MISSING_REQUIRED_ATTRS = "missing_required_attrs"


class ReviewPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# --- Platform ---

class Platform(str, Enum):
    INSALES = "insales"
    OZON = "ozon"
    WB = "wb"


class ReadinessStatus(str, Enum):
    READY = "READY"
    DRAFT = "DRAFT"
    BLOCKED_NO_PRICE = "BLOCKED_NO_PRICE"
    BLOCKED_NO_EAN = "BLOCKED_NO_EAN"
    BLOCKED_NO_WEIGHT = "BLOCKED_NO_WEIGHT"
    BLOCKED_NO_CATEGORY_MAPPING = "BLOCKED_NO_CATEGORY_MAPPING"
    BLOCKED_NO_PHOTO = "BLOCKED_NO_PHOTO"
    BLOCKED_IDENTITY_WEAK = "BLOCKED_IDENTITY_WEAK"
