from __future__ import annotations

import importlib
import sys
from pathlib import Path
from uuid import UUID


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import_document_service():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("domain.document_service")


def _import_availability_service():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("domain.availability_service")


def test_document_generation_key_is_deterministic_for_equivalent_content():
    svc = _import_document_service()
    order_id = UUID("11111111-1111-1111-1111-111111111111")

    snapshot_a = {
        "_schema_version": "2.0",
        "order_id": str(order_id),
        "currency": "RUB",
        "line_items": [
            {
                "line_seq": 1,
                "name_snapshot": "Товар",
                "sku_snapshot": "SKU-1",
                "quantity": 1,
                "price_unit_minor": 10000,
                "tax_rate_bps": 0,
            }
        ],
        "total_minor": 10000,
        "generated_at": "2026-02-14T12:00:00Z",
    }
    snapshot_b = {
        "currency": "RUB",
        "line_items": [
            {
                "tax_rate_bps": 0,
                "price_unit_minor": 10000,
                "quantity": 1,
                "sku_snapshot": "SKU-1",
                "name_snapshot": "Товар",
                "line_seq": 1,
            }
        ],
        "order_id": str(order_id),
        "_schema_version": "2.0",
        "total_minor": 10000,
        "document_id": "ignored-during-hash",
    }

    key_a = svc.build_generation_key(order_id, snapshot_a)
    key_b = svc.build_generation_key(order_id, snapshot_b)
    assert key_a == key_b


def test_document_generation_key_changes_when_business_content_changes():
    svc = _import_document_service()
    order_id = UUID("22222222-2222-2222-2222-222222222222")
    base = {
        "order_id": str(order_id),
        "currency": "RUB",
        "line_items": [{"line_seq": 1, "sku_snapshot": "SKU-1", "name_snapshot": "Товар", "quantity": 1, "price_unit_minor": 10000, "tax_rate_bps": 0}],
        "total_minor": 10000,
    }
    changed = {
        "order_id": str(order_id),
        "currency": "RUB",
        "line_items": [{"line_seq": 1, "sku_snapshot": "SKU-1", "name_snapshot": "Товар", "quantity": 1, "price_unit_minor": 12000, "tax_rate_bps": 0}],
        "total_minor": 12000,
    }
    assert svc.build_generation_key(order_id, base) != svc.build_generation_key(order_id, changed)


def test_reservation_chunk_keys_are_event_scoped_and_replay_safe():
    svc = _import_availability_service()
    order_id = UUID("33333333-3333-3333-3333-333333333333")
    line_item_id = UUID("44444444-4444-4444-4444-444444444444")
    ev1 = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    ev2 = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    r1, s1 = svc.build_reservation_chunk_keys(order_id, line_item_id, ev1)
    r1_dup, s1_dup = svc.build_reservation_chunk_keys(order_id, line_item_id, ev1)
    r2, s2 = svc.build_reservation_chunk_keys(order_id, line_item_id, ev2)

    assert (r1, s1) == (r1_dup, s1_dup)
    assert r1 != r2
    assert s1 != s2

