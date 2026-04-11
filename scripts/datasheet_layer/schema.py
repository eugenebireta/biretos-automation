"""
SS-1.1 — DatasheetRecord schema (Pydantic).

Versioned, content-hashed, trace_id-aware datasheet record.
Every field follows DNA Tier-3 requirements:
- trace_id: mandatory (DNA §7)
- idempotency_key: "{pn}:{content_hash}" — dedup before I/O
- Structured error logging: error_class/severity/retriable
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator


def _now() -> datetime:
    """Injectable clock for testability."""
    return datetime.now(timezone.utc)


class DatasheetRecord(BaseModel):
    """Versioned datasheet record for a single PN."""

    schema_version: int = 1
    pn: str
    brand: str
    version: int = Field(ge=1)
    trace_id: str
    idempotency_key: str = ""  # auto-computed if empty
    source_id: str  # URL or file path
    source_tier: str  # manufacturer / distributor / aggregator
    content_hash: str  # SHA-256 of PDF bytes
    ingested_at: datetime = Field(default_factory=_now)
    pdf_path: str | None = None
    pdf_url: str | None = None
    pn_confirmed: bool = False
    num_pages: int = 0
    specs: dict[str, str] = Field(default_factory=dict)
    text_excerpt: str = ""
    parse_method: str = ""  # pymupdf / pdfplumber / ocr
    supersedes: int | None = None  # previous version number

    @model_validator(mode="after")
    def _auto_idempotency_key(self) -> DatasheetRecord:
        if not self.pn:
            raise ValueError("pn must not be empty — dedup depends on it")
        if not self.content_hash:
            raise ValueError("content_hash must not be empty — dedup depends on it")
        if not self.idempotency_key:
            self.idempotency_key = f"{self.pn}:{self.content_hash}"
        return self

    def model_dump_json_safe(self) -> dict:
        """Serialize with ISO timestamps for JSON storage."""
        d = self.model_dump()
        d["ingested_at"] = self.ingested_at.isoformat()
        return d


def compute_content_hash(pdf_bytes: bytes) -> str:
    """SHA-256 hash of PDF content for dedup."""
    return hashlib.sha256(pdf_bytes).hexdigest()
