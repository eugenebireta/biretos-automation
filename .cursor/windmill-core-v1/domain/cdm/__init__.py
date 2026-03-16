"""
CDM v2 — Pydantic boundary models for validation.
No ru_worker imports. Conversion to FSM types is done in Tier-3 adapters.
"""
from __future__ import annotations

from domain.cdm.document import DocumentKey
from domain.cdm.event import OrderEventInput
from domain.cdm.order import OrderRecord
from domain.cdm.payment import PaymentTransaction
from domain.cdm.shipment import ShipmentRecord
from domain.cdm.task_intent import TaskIntent
from domain.cdm.validators import validate_order_state

__all__ = [
    "DocumentKey",
    "OrderEventInput",
    "OrderRecord",
    "PaymentTransaction",
    "ShipmentRecord",
    "TaskIntent",
    "validate_order_state",
]
