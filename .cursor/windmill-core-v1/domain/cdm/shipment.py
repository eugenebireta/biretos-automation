"""
ShipmentRecord — Pydantic model for validated shipments row.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel


class ShipmentRecord(BaseModel):
    """Typed view of shipments row."""

    order_id: UUID
    shipment_id: UUID
    carrier_code: str
    carrier_external_id: Optional[str] = None
    current_status: str
    metadata: Dict[str, Any] = {}
