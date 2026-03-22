"""domain/catalog_models.py — R1 Mass Catalog Pipeline: Pydantic v2 models.

Tier-2 domain models. Validates and normalises inbound catalog rows.
No DB access here — pure data contracts.

Confidence scoring (catalog_evidence_policy_v1):
    HIGH   — part_number + name + approx_price + qty all present.
    MEDIUM — part_number present; at least one of name/approx_price/qty missing.
    LOW    — part_number present but name and price both absent.
    → no confidence level is assigned if part_number is missing (row is rejected).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ReviewReason(str, Enum):
    MISSING_PN = "missing_pn"
    AMBIGUOUS_PN = "ambiguous_pn"
    DUPLICATE_PN = "duplicate_pn"
    NO_PHOTO = "no_photo"
    TITLE_CONFIDENCE_LOW = "title_confidence_low"
    SOURCE_CONFLICT = "source_conflict"
    VALIDATION_FAILED = "validation_failed"


# ---------------------------------------------------------------------------
# Row model (one SKU from the import file)
# ---------------------------------------------------------------------------

_PN_NOISE = re.compile(r"[\s\-_./\\]+")


def _clean_pn(raw: str) -> str:
    """Normalise part number: uppercase, collapse separators to single space."""
    return _PN_NOISE.sub(" ", raw.strip()).upper().strip()


class CatalogImportRow(BaseModel):
    """Validated and normalised representation of a single catalog row.

    Mandatory at construction: trace_id, idempotency_key, brand, part_number.
    All other fields are optional and influence confidence scoring.
    """

    trace_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)
    brand: str = Field(..., min_length=1)
    part_number: str = Field(..., min_length=1)

    name: Optional[str] = None
    qty: Optional[int] = Field(default=None, ge=0)
    approx_price: Optional[float] = Field(default=None, ge=0.0)
    photo_url: Optional[str] = None

    # Derived — set by model_validator below.
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    review_reason: Optional[ReviewReason] = None

    @field_validator("part_number", mode="before")
    @classmethod
    def normalise_part_number(cls, v: object) -> str:
        raw = str(v).strip()
        if not raw:
            raise ValueError("part_number must not be empty")
        return _clean_pn(raw)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @model_validator(mode="after")
    def _derive_confidence_and_review(self) -> "CatalogImportRow":
        has_name = bool(self.name)
        has_price = self.approx_price is not None
        has_qty = self.qty is not None

        if has_name and has_price and has_qty:
            self.confidence = ConfidenceLevel.HIGH
        elif has_name or has_price:
            self.confidence = ConfidenceLevel.MEDIUM
        else:
            self.confidence = ConfidenceLevel.LOW
            self.review_reason = ReviewReason.TITLE_CONFIDENCE_LOW

        # Photo placeholder policy (catalog_evidence_policy_v1):
        # absence of photo does NOT block revenue; flag for review only if
        # the row is otherwise HIGH confidence (better to flag proactively).
        if not self.photo_url and self.confidence == ConfidenceLevel.HIGH:
            if self.review_reason is None:
                self.review_reason = ReviewReason.NO_PHOTO

        return self


# ---------------------------------------------------------------------------
# Job payload model (what the worker entry point receives)
# ---------------------------------------------------------------------------

class CatalogJobPayload(BaseModel):
    """Input contract for catalog_worker.run_catalog_job().

    Carries all job-level parameters needed to drive the pipeline.
    """

    trace_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)

    # Path to the import file (Excel .xlsx or .csv).
    source_file_path: str = Field(..., min_length=1)

    brand: str = Field(..., min_length=1)

    # Shopware identifiers required to build the product payload.
    shopware_tax_id: str = Field(..., min_length=1)
    shopware_currency_id: str = Field(..., min_length=1)

    # Optional overrides.
    shopware_default_stock: int = Field(default=0, ge=0)
