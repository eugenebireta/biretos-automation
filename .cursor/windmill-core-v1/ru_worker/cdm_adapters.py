"""
Tier-3 adapters: CDM Pydantic models → FSM dataclasses.
domain/cdm does NOT import ru_worker. This module does.
"""
from __future__ import annotations

from domain.cdm.event import OrderEventInput
from domain.cdm.order import OrderRecord
from ru_worker.fsm_v2 import Event, LedgerRecord


def order_event_input_to_fsm_event(ev: OrderEventInput) -> Event:
    """Convert OrderEventInput to fsm_v2.Event."""
    occurred_at = ev.occurred_at
    if hasattr(occurred_at, "isoformat"):
        occurred_at_str = occurred_at.isoformat()
    else:
        occurred_at_str = str(occurred_at)
    return Event(
        event_id=ev.event_id,
        source=ev.source,
        event_type=ev.event_type,
        occurred_at=occurred_at_str,
        payload=ev.payload,
    )


def order_record_to_ledger_record(rec: OrderRecord) -> LedgerRecord:
    """Convert OrderRecord to fsm_v2.LedgerRecord."""
    return LedgerRecord(
        order_id=rec.order_id,
        state=rec.state,
        state_history=rec.state_history,
        metadata=rec.metadata,
    )
