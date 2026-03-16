"""
OrderEventInput — Pydantic model for validated external events.
No ru_worker imports. Conversion to fsm_v2.Event is done in Tier-3 adapters.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal
from uuid import UUID

from pydantic import BaseModel, field_validator


class OrderEventInput(BaseModel):
    """Validated external event before FSM processing."""

    event_id: UUID
    source: Literal["telegram", "cdek", "shopware", "system"]
    event_type: str
    external_id: str
    occurred_at: datetime
    payload: Dict[str, Any]
    order_id: UUID

    @field_validator("occurred_at", mode="before")
    @classmethod
    def parse_occurred_at(cls, v: str | datetime) -> datetime:
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                pass
        raise ValueError("occurred_at must be ISO8601 string or datetime")
