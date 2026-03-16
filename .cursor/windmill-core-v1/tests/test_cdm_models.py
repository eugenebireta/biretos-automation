"""
Tests for CDM v2 Pydantic models and adapters.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _setup_path():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


# --- OrderEventInput ---


def test_order_event_input_construction():
    _setup_path()
    from domain.cdm.event import OrderEventInput

    ev = OrderEventInput(
        event_id=uuid4(),
        source="telegram",
        event_type="telegram_callback_order",
        external_id="123",
        occurred_at="2026-03-03T12:00:00Z",
        payload={"order_id": "00000000-0000-0000-0000-000000000001"},
        order_id=uuid4(),
    )
    assert ev.source == "telegram"
    assert ev.event_type == "telegram_callback_order"
    assert isinstance(ev.occurred_at, datetime)


def test_order_event_input_rejects_invalid_source():
    _setup_path()
    from domain.cdm.event import OrderEventInput
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OrderEventInput(
            event_id=uuid4(),
            source="invalid_source",
            event_type="test",
            external_id="x",
            occurred_at="2026-03-03T12:00:00Z",
            payload={},
            order_id=uuid4(),
        )


def test_order_event_input_parse_occurred_at_from_str():
    _setup_path()
    from domain.cdm.event import OrderEventInput

    ev = OrderEventInput(
        event_id=uuid4(),
        source="cdek",
        event_type="cdek_status_update",
        external_id="cdek-123",
        occurred_at="2026-03-03T14:30:00+00:00",
        payload={},
        order_id=uuid4(),
    )
    assert ev.occurred_at.tzinfo is not None or ev.occurred_at.year == 2026


# --- OrderRecord ---


def test_order_record_construction():
    _setup_path()
    from domain.cdm.order import OrderRecord

    rec = OrderRecord(
        order_id=uuid4(),
        state="paid",
        state_history=[],
        metadata={},
    )
    assert rec.state == "paid"
    assert rec.order_total_minor == 0


def test_order_record_rejects_invalid_state():
    _setup_path()
    from domain.cdm.order import OrderRecord
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OrderRecord(
            order_id=uuid4(),
            state="invalid_state_xyz",
            state_history=[],
            metadata={},
        )


def test_order_record_from_db_row():
    _setup_path()
    from domain.cdm.order import OrderRecord

    oid = uuid4()
    row = {
        "order_id": oid,
        "state": "draft",
        "state_history": [],
        "metadata": {},
        "order_total_minor": 1000,
    }
    rec = OrderRecord.from_db_row(row)
    assert rec.order_id == oid
    assert rec.state == "draft"
    assert rec.order_total_minor == 1000


def test_order_record_from_db_row_with_json_strings():
    _setup_path()
    from domain.cdm.order import OrderRecord

    oid = uuid4()
    row = {
        "order_id": str(oid),
        "state": "paid",
        "state_history": "[]",
        "metadata": "{}",
        "order_total_minor": None,
    }
    rec = OrderRecord.from_db_row(row)
    assert rec.state == "paid"
    assert rec.state_history == []
    assert rec.metadata == {}
    assert rec.order_total_minor == 0


# --- Adapters ---


def test_order_event_input_to_fsm_event():
    _setup_path()
    from domain.cdm.event import OrderEventInput
    from ru_worker.cdm_adapters import order_event_input_to_fsm_event

    ev = OrderEventInput(
        event_id=uuid4(),
        source="telegram",
        event_type="telegram_callback_order",
        external_id="123",
        occurred_at=datetime(2026, 3, 3, 12, 0, 0, tzinfo=timezone.utc),
        payload={"key": "value"},
        order_id=uuid4(),
    )
    fsm_event = order_event_input_to_fsm_event(ev)
    assert fsm_event.event_id == ev.event_id
    assert fsm_event.source == "telegram"
    assert fsm_event.event_type == "telegram_callback_order"
    assert "2026-03-03" in fsm_event.occurred_at
    assert fsm_event.payload == {"key": "value"}


def test_order_record_to_ledger_record():
    _setup_path()
    from domain.cdm.order import OrderRecord
    from ru_worker.cdm_adapters import order_record_to_ledger_record

    oid = uuid4()
    rec = OrderRecord(
        order_id=oid,
        state="shipped",
        state_history=[{"from_state": "paid", "to_state": "shipped"}],
        metadata={"key": "value"},
    )
    ledger = order_record_to_ledger_record(rec)
    assert ledger.order_id == oid
    assert ledger.state == "shipped"
    assert len(ledger.state_history) == 1
    assert ledger.metadata == {"key": "value"}


# --- validate_order_state ---


def test_validate_order_state_accepts_valid():
    _setup_path()
    from domain.cdm.validators import validate_order_state

    assert validate_order_state("draft") == "draft"
    assert validate_order_state("paid") == "paid"
    assert validate_order_state("completed") == "completed"


def test_validate_order_state_rejects_invalid():
    _setup_path()
    from domain.cdm.validators import validate_order_state

    with pytest.raises(ValueError, match="state must be in"):
        validate_order_state("invalid")
