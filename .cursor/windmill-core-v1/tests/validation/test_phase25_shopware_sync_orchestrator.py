from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


_ROOT = Path(__file__).resolve().parents[2]
_WORKERS = _ROOT / "workers"
for _p in (_ROOT, _WORKERS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

orch = importlib.import_module("shopware_sync_orchestrator")


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows: List[Any] = []

    def execute(self, query: str, params: Optional[tuple[Any, ...]] = None) -> None:
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("select id, instance, entity_type, entity_id, payload, attempt_count from shopware_outbound_queue"):
            self._rows = list(self._conn.pending_rows)
            return

        if normalized.startswith("update shopware_outbound_queue set status = 'processing'"):
            self._conn.processing_updates += 1
            self._rows = []
            return

        if normalized.startswith("update shopware_outbound_queue set status = 'confirmed'"):
            self._conn.confirmed_updates += 1
            self._rows = []
            return

        if normalized.startswith("update shopware_outbound_queue set status = 'failed'"):
            self._conn.failed_updates += 1
            self._rows = []
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchall(self):
        return list(self._rows)

    def close(self) -> None:
        return None


class _Conn:
    def __init__(self, pending_rows: List[Any]) -> None:
        self.pending_rows = pending_rows
        self.processing_updates = 0
        self.confirmed_updates = 0
        self.failed_updates = 0
        self.commits = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None


def test_shopware_sync_orchestrator_confirms_product_row(monkeypatch) -> None:
    conn = _Conn(
        pending_rows=[
            ("q1", "ru", "product", "SKU-1", {"productNumber": "SKU-1", "name": "A"}, 0),
        ]
    )

    class _Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def upsert_product(self, _payload):
            return {"ok": True}

        def sync_order_state(self, **_kwargs):
            return {"ok": True}

        def close(self):
            return None

    monkeypatch.setattr(orch, "ShopwareApiClient", _Client, raising=True)
    monkeypatch.setattr(
        orch,
        "get_config",
        lambda: type(
            "Cfg",
            (),
            {
                "shopware_url": "https://shopware.local",
                "shopware_client_id": "id",
                "shopware_client_secret": "secret",
                "shopware_timeout_seconds": 10,
                "shopware_enable_dry_run": True,
            },
        )(),
        raising=True,
    )
    monkeypatch.setenv("SHOPWARE_RU_URL", "https://ru-shopware.local")
    monkeypatch.setenv("SHOPWARE_RU_CLIENT_ID", "ru-id")
    monkeypatch.setenv("SHOPWARE_RU_CLIENT_SECRET", "ru-secret")

    result = orch.run_shopware_sync_orchestrator(conn, batch_size=10)
    assert result["processed"] == 1
    assert result["confirmed"] == 1
    assert result["failed"] == 0
    assert conn.processing_updates == 1
    assert conn.confirmed_updates == 1
    assert conn.commits == 1


def test_shopware_sync_orchestrator_marks_failed_on_error(monkeypatch) -> None:
    conn = _Conn(
        pending_rows=[
            ("q2", "ru", "order_status", "SO-1", {"order_number": "SO-1", "target_core_state": "paid"}, 1),
        ]
    )

    class _Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def upsert_product(self, _payload):
            return {"ok": True}

        def sync_order_state(self, **_kwargs):
            raise RuntimeError("shopware 503")

        def close(self):
            return None

    monkeypatch.setattr(orch, "ShopwareApiClient", _Client, raising=True)
    monkeypatch.setattr(
        orch,
        "get_config",
        lambda: type(
            "Cfg",
            (),
            {
                "shopware_url": "https://shopware.local",
                "shopware_client_id": "id",
                "shopware_client_secret": "secret",
                "shopware_timeout_seconds": 10,
                "shopware_enable_dry_run": True,
            },
        )(),
        raising=True,
    )
    monkeypatch.setenv("SHOPWARE_RU_URL", "https://ru-shopware.local")
    monkeypatch.setenv("SHOPWARE_RU_CLIENT_ID", "ru-id")
    monkeypatch.setenv("SHOPWARE_RU_CLIENT_SECRET", "ru-secret")

    result = orch.run_shopware_sync_orchestrator(conn, batch_size=10)
    assert result["processed"] == 1
    assert result["confirmed"] == 0
    assert result["failed"] == 1
    assert conn.processing_updates == 1
    assert conn.failed_updates == 1
