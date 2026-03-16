"""
OrderRecord — Pydantic model for validated order_ledger row.
No ru_worker imports. Conversion to LedgerRecord is done in Tier-3 adapters.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator

from domain.cdm.validators import validate_order_state


class OrderRecord(BaseModel):
    """Typed view of order_ledger row."""

    order_id: UUID
    state: str
    state_history: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    order_total_minor: int = 0
    trace_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        return validate_order_state(v)

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> OrderRecord:
        order_id = row.get("order_id")
        if order_id is None:
            raise ValueError("order_id is required in row")
        state = row.get("state")
        if state is None:
            raise ValueError("state is required in row")

        state_history = row.get("state_history")
        if isinstance(state_history, str):
            state_history = json.loads(state_history) if state_history else []
        state_history = state_history or []

        metadata = row.get("metadata")
        if isinstance(metadata, str):
            metadata = json.loads(metadata) if metadata else {}
        metadata = metadata or {}

        order_total_minor = row.get("order_total_minor")
        if order_total_minor is None:
            order_total_minor = 0
        else:
            order_total_minor = int(order_total_minor)

        trace_id = row.get("trace_id")
        if trace_id is not None:
            trace_id = str(trace_id)

        return cls(
            order_id=UUID(str(order_id)),
            state=state,
            state_history=state_history,
            metadata=metadata,
            order_total_minor=order_total_minor,
            trace_id=trace_id,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
