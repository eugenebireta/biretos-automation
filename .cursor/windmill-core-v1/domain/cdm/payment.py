"""
PaymentTransaction — Pydantic model for validated payment_transactions row.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel


class PaymentTransaction(BaseModel):
    """Typed view of payment_transactions row."""

    order_id: UUID
    transaction_id: UUID
    status: str
    amount_minor: int
    transaction_type: str
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = {}
