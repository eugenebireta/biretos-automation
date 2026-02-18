from __future__ import annotations

from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_availability_service_enforces_row_lock_and_atomic_snapshot_mutation():
    source = (_project_root() / "domain" / "availability_service.py").read_text(encoding="utf-8")
    assert "FOR UPDATE" in source
    assert "INSERT INTO stock_ledger_entries" in source
    assert "UPDATE availability_snapshot" in source
    # Guard against split async cache updates inside service.
    reserve_fn = source.split("def reserve_inventory_chunk_atomic", 1)[1]
    assert ".commit(" not in reserve_fn


def test_payment_service_keeps_insert_and_cache_recompute_in_single_service_path():
    source = (_project_root() / "domain" / "payment_service.py").read_text(encoding="utf-8")
    assert "INSERT INTO payment_transactions" in source
    assert "UPDATE order_ledger" in source
    assert "payment_status_changed_at" in source
    # Service must not commit, worker controls single transaction boundary.
    assert ".commit(" not in source


def test_shipment_cache_semantics_latest_non_cancelled():
    source = (_project_root() / "domain" / "shipment_service.py").read_text(encoding="utf-8")
    assert "current_status <> 'cancelled'" in source
    assert "ORDER BY shipment_seq DESC" in source
    assert "SET cdek_uuid = %s" in source


def test_unwrap_flow_exists_in_cancel_transition():
    source = (_project_root() / "domain" / "shipment_service.py").read_text(encoding="utf-8")
    assert "def _unpack_line_items_for_cancel" in source
    assert "to_status == \"cancelled\"" in source
    assert "line_items_deallocated" in source
    assert "line_items_already_released" in source


def test_invoice_worker_uses_content_hash_document_contract_not_total_amount_key():
    source = (_project_root() / "side_effects" / "invoice_worker.py").read_text(encoding="utf-8")
    assert "upsert_document_by_content_hash_atomic" in source
    assert "invoice_request_key = f\"{insales_order_id}_{total_key}_{currency}\"" not in source


def test_fsm_contains_phase2_partial_states():
    source = (_project_root() / "ru_worker" / "fsm_v2.py").read_text(encoding="utf-8")
    assert "\"partially_paid\"" in source
    assert "\"partially_shipped\"" in source
    assert "\"cancelled\"" in source

