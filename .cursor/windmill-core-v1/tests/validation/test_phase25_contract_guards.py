from __future__ import annotations

from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_observability_service_is_read_only():
    source = (_project_root() / "domain" / "observability_service.py").read_text(encoding="utf-8")
    upper = source.upper()
    assert "INSERT INTO" not in upper
    assert "UPDATE " not in upper
    assert "DELETE FROM" not in upper


def test_rc3_lock_order_for_update_before_ledger_sum():
    source = (_project_root() / "domain" / "reconciliation_service.py").read_text(encoding="utf-8")
    section = source.split("def rebuild_stock_snapshot", 1)[1].split("def reconcile_document_key", 1)[0]
    assert "FOR UPDATE" in section
    assert "SUM(quantity_delta)" in section
    assert section.index("FOR UPDATE") < section.index("SUM(quantity_delta)")


def test_maintenance_sweeper_does_not_import_ru_worker_runtime_module():
    source = (_project_root() / "maintenance_sweeper.py").read_text(encoding="utf-8")
    assert "ru_worker.ru_worker" not in source

