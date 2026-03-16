"""
DocumentKey — Pydantic model for validated documents row.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class DocumentKey(BaseModel):
    """Typed view of documents row key fields."""

    order_id: UUID
    document_type: str
    provider_document_id: Optional[str] = None
    status: str
