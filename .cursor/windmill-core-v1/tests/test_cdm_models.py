"""
Tests for domain/cdm_models.py — Task 5.1.

Pure unit tests: no DB, no external API, no live dependencies.
All tests are deterministic.
"""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError


def _ensure_import_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_import_paths()

from domain.cdm_models import ActionSnapshot, TaskIntent


# ---------------------------------------------------------------------------
# TaskIntent tests
# ---------------------------------------------------------------------------


def test_task_intent_valid():
    intent = TaskIntent(
        trace_id="550e8400-e29b-41d4-a716-446655440000",
        action_type="cdek_shipment",
        payload={"invoice_id": "INV-001"},
        source="telegram",
    )
    assert intent.trace_id == "550e8400-e29b-41d4-a716-446655440000"
    assert intent.action_type == "cdek_shipment"
    assert intent.payload == {"invoice_id": "INV-001"}
    assert intent.source == "telegram"
    assert intent.metadata == {}
    assert intent.idempotency_key is None


def test_task_intent_missing_required():
    """Omitting a required field must raise ValidationError (Fail Loud)."""
    with pytest.raises(ValidationError):
        TaskIntent(
            action_type="cdek_shipment",
            payload={"invoice_id": "INV-001"},
            source="telegram",
            # trace_id intentionally omitted
        )


def test_task_intent_empty_trace_id():
    """Empty trace_id must be rejected (min_length=1, Fail Loud)."""
    with pytest.raises(ValidationError):
        TaskIntent(
            trace_id="",
            action_type="cdek_shipment",
            payload={"invoice_id": "INV-001"},
            source="telegram",
        )


# ---------------------------------------------------------------------------
# ActionSnapshot tests
# ---------------------------------------------------------------------------


def test_action_snapshot_valid():
    snapshot = ActionSnapshot(
        schema_version=1,
        leaf_worker_type="cdek_shipment",
        leaf_payload={"order_id": "ORD-001"},
        external_idempotency_key="gov_exec:abc-123",
    )
    assert snapshot.schema_version == 1
    assert snapshot.leaf_worker_type == "cdek_shipment"
    assert snapshot.leaf_payload == {"order_id": "ORD-001"}
    assert snapshot.external_idempotency_key == "gov_exec:abc-123"


def test_action_snapshot_wrong_schema_version():
    """schema_version != 1 must be rejected (Literal[1], Fail Loud)."""
    with pytest.raises(ValidationError):
        ActionSnapshot(
            schema_version=99,
            leaf_worker_type="cdek_shipment",
            leaf_payload={"order_id": "ORD-001"},
            external_idempotency_key="gov_exec:abc-123",
        )


def test_action_snapshot_missing_leaf_payload():
    """Absent leaf_payload must raise ValidationError (Fail Loud)."""
    with pytest.raises(ValidationError):
        ActionSnapshot(
            schema_version=1,
            leaf_worker_type="cdek_shipment",
            # leaf_payload intentionally omitted
            external_idempotency_key="gov_exec:abc-123",
        )
