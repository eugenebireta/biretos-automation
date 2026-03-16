from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Optional
from uuid import UUID


@dataclass
class _ConfigStub:
    shopware_url: str = "https://shopware.example.local"
    shopware_client_id: str = "shopware-client-id"
    shopware_client_secret: str = "shopware-client-secret"
    shopware_timeout_seconds: int = 10
    shopware_enable_dry_run: bool = True

    # Values referenced by ru_worker import-time constants.
    dry_run_external_apis: bool = True
    telegram_bot_token: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "biretos_automation"
    postgres_user: str = "biretos_user"
    postgres_password: str = "test"
    ru_worker_poll_interval: int = 1
    llm_enabled_default: bool = False

    def __getattr__(self, _: str) -> Any:
        return None


class _StatefulCursor:
    def __init__(self, conn: "_StatefulConnection") -> None:
        self._conn = conn
        self._rows: list[Any] = []

    def execute(self, query: str, params: Optional[tuple[Any, ...]] = None) -> None:
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("insert into shopware_operations"):
            op_id, product_number, content_hash, created_at, updated_at = params
            key = (product_number, content_hash)
            if key in self._conn.operations_by_key:
                self._rows = []
                return
            row = {
                "id": str(op_id),
                "product_number": product_number,
                "content_hash": content_hash,
                "status": "pending",
                "error": None,
                "attempt": 0,
                "created_at": created_at,
                "updated_at": updated_at,
            }
            self._conn.operations_by_key[key] = row
            self._conn.id_to_key[row["id"]] = key
            self._rows = [(row["id"],)]
            return

        if normalized.startswith("select shopware_media_id from shopware_media_map"):
            product_number, media_url = params
            media_id = self._conn.media_map.get((str(product_number), str(media_url)))
            if not media_id:
                self._rows = []
                return
            self._rows = [(media_id,)]
            return

        if normalized.startswith("insert into shopware_media_map"):
            product_number, media_url, media_id, _position = params
            self._conn.media_map[(str(product_number), str(media_url))] = str(media_id)
            self._rows = []
            return

        if normalized.startswith("select id, status, attempt, updated_at from shopware_operations"):
            product_number, content_hash = params
            key = (product_number, content_hash)
            row = self._conn.operations_by_key.get(key)
            if not row:
                self._rows = []
                return
            self._rows = [(row["id"], row["status"], row["attempt"], row["updated_at"])]
            return

        if "set status = 'pending', attempt = attempt + 1, error = null" in normalized:
            (op_id,) = params
            key = self._conn.id_to_key.get(str(op_id))
            row = self._conn.operations_by_key.get(key) if key else None
            if not row:
                self._rows = []
                return
            row["status"] = "pending"
            row["attempt"] = int(row["attempt"]) + 1
            row["error"] = None
            row["updated_at"] = datetime.now(timezone.utc)
            self._rows = [(row["id"],)]
            return

        if normalized.startswith("update shopware_operations set status = %s, error = %s where id = %s"):
            status, error, op_id = params
            key = self._conn.id_to_key.get(str(op_id))
            row = self._conn.operations_by_key.get(key) if key else None
            if row:
                row["status"] = status
                row["error"] = error
                row["updated_at"] = datetime.now(timezone.utc)
            self._rows = []
            return

        raise AssertionError(f"Unexpected SQL in test cursor: {normalized}")

    def fetchone(self) -> Any:
        if not self._rows:
            return None
        return self._rows.pop(0)

    def close(self) -> None:
        return None


class _StatefulConnection:
    def __init__(self) -> None:
        self.autocommit = False
        self.operations_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        self.id_to_key: dict[str, tuple[str, str]] = {}
        self.media_map: dict[tuple[str, str], str] = {}
        self.commit_calls = 0

    def cursor(self) -> _StatefulCursor:
        return _StatefulCursor(self)

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        return None

    def rows(self) -> list[dict[str, Any]]:
        return list(self.operations_by_key.values())


def _project_root() -> Path:
    # tests/validation/test_*.py -> windmill-core-v1/
    return Path(__file__).resolve().parents[2]


def _import_ru_worker_isolated(config_stub: _ConfigStub, monkeypatch) -> ModuleType:
    root = _project_root()
    ru_worker_dir = root / "ru_worker"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(ru_worker_dir) not in sys.path:
        sys.path.insert(0, str(ru_worker_dir))

    import config as config_pkg

    monkeypatch.setattr(config_pkg, "get_config", lambda: config_stub, raising=True)

    module_path = ru_worker_dir / "ru_worker.py"
    spec = importlib.util.spec_from_file_location("_validation_isolated_ru_worker", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to create import spec for ru_worker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _import_shopware_worker(config_stub: _ConfigStub, monkeypatch):
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    import config as config_pkg

    monkeypatch.setattr(config_pkg, "get_config", lambda: config_stub, raising=True)

    for module_name in [
        "side_effects.shopware_product_worker",
        "ru_worker.shopware_api_client",
        "ru_worker.shopware_idempotency",
        "ru_worker.shopware_payload_builder",
    ]:
        sys.modules.pop(module_name, None)

    worker_module = importlib.import_module("side_effects.shopware_product_worker")
    return worker_module


def _build_payload() -> dict[str, Any]:
    return {
        "product_number": "TEST-123",
        "cdm_product": {
            "name": "Test Product",
            "description": "Smoke",
            "price_gross": 100.0,
            "currency_id": "RUB_ID",
            "tax_id": "TAX_ID",
            "stock": 5,
            "active": True,
        },
        "_trace_id": "00000000-0000-0000-0000-000000000123",
    }


def test_shopware_product_sync_dry_run_creates_operation_and_confirms(monkeypatch):
    config_stub = _ConfigStub(shopware_enable_dry_run=True)
    isolated_ru_worker = _import_ru_worker_isolated(config_stub, monkeypatch)
    assert hasattr(isolated_ru_worker, "process_job")

    worker_module = _import_shopware_worker(config_stub, monkeypatch)

    # Deterministic operation id/time behavior where needed.
    idempotency_module = importlib.import_module("ru_worker.shopware_idempotency")
    monkeypatch.setattr(
        idempotency_module,
        "uuid4",
        lambda: UUID("00000000-0000-0000-0000-00000000a001"),
        raising=True,
    )

    # DRY_RUN must not invoke network request path.
    monkeypatch.setattr(worker_module.ShopwareApiClient, "_ensure_token", lambda self: None, raising=True)

    def _forbid_network(*_args, **_kwargs):
        raise AssertionError("Network call is forbidden in DRY_RUN validation")

    monkeypatch.setattr("requests.Session.request", _forbid_network, raising=True)

    conn = _StatefulConnection()
    result = worker_module.execute_shopware_product_sync(_build_payload(), conn)

    assert result["status"] == "confirmed"
    assert "operation_id" in result

    rows = conn.rows()
    assert len(rows) == 1
    assert rows[0]["status"] == "confirmed"
    assert rows[0]["attempt"] == 0
    assert conn.commit_calls == 0


def test_shopware_product_sync_second_run_is_skip_and_no_upsert(monkeypatch):
    config_stub = _ConfigStub(shopware_enable_dry_run=True)
    isolated_ru_worker = _import_ru_worker_isolated(config_stub, monkeypatch)
    assert hasattr(isolated_ru_worker, "process_job")

    worker_module = _import_shopware_worker(config_stub, monkeypatch)

    idempotency_module = importlib.import_module("ru_worker.shopware_idempotency")
    monkeypatch.setattr(
        idempotency_module,
        "uuid4",
        lambda: UUID("00000000-0000-0000-0000-00000000a001"),
        raising=True,
    )

    monkeypatch.setattr(worker_module.ShopwareApiClient, "_ensure_token", lambda self: None, raising=True)

    def _forbid_network(*_args, **_kwargs):
        raise AssertionError("Network call is forbidden in DRY_RUN validation")

    monkeypatch.setattr("requests.Session.request", _forbid_network, raising=True)

    conn = _StatefulConnection()
    payload = _build_payload()

    first_result = worker_module.execute_shopware_product_sync(payload, conn)
    assert first_result["status"] == "confirmed"
    count_before = len(conn.rows())

    second_result = worker_module.execute_shopware_product_sync(payload, conn)
    assert second_result["status"] == "skipped"
    assert len(conn.rows()) == count_before
    assert count_before == 1
    assert conn.commit_calls == 0


def test_shopware_product_sync_stale_pending_takeover(monkeypatch):
    config_stub = _ConfigStub(shopware_enable_dry_run=True)
    worker_module = _import_shopware_worker(config_stub, monkeypatch)

    idempotency_module = importlib.import_module("ru_worker.shopware_idempotency")
    monkeypatch.setattr(
        idempotency_module,
        "uuid4",
        lambda: UUID("00000000-0000-0000-0000-00000000a001"),
        raising=True,
    )

    monkeypatch.setattr(worker_module.ShopwareApiClient, "_ensure_token", lambda self: None, raising=True)

    def _forbid_network(*_args, **_kwargs):
        raise AssertionError("Network call is forbidden in DRY_RUN validation")

    monkeypatch.setattr("requests.Session.request", _forbid_network, raising=True)

    conn = _StatefulConnection()
    payload = _build_payload()

    first_result = worker_module.execute_shopware_product_sync(payload, conn)
    assert first_result["status"] == "confirmed"
    assert len(conn.rows()) == 1
    assert conn.rows()[0]["attempt"] == 0

    row = conn.rows()[0]
    row["status"] = "pending"
    row["updated_at"] = datetime.now(timezone.utc) - timedelta(minutes=20)

    second_result = worker_module.execute_shopware_product_sync(payload, conn)
    assert second_result["status"] == "confirmed"
    assert len(conn.rows()) == 1
    assert conn.rows()[0]["attempt"] == 1
    assert conn.rows()[0]["status"] == "confirmed"
    assert conn.commit_calls == 0


def test_shopware_product_sync_marks_failed_on_api_error(monkeypatch):
    config_stub = _ConfigStub(shopware_enable_dry_run=True)
    worker_module = _import_shopware_worker(config_stub, monkeypatch)

    idempotency_module = importlib.import_module("ru_worker.shopware_idempotency")
    monkeypatch.setattr(
        idempotency_module,
        "uuid4",
        lambda: UUID("00000000-0000-0000-0000-00000000a001"),
        raising=True,
    )

    def _forbid_network(*_args, **_kwargs):
        raise AssertionError("Network call is forbidden in DRY_RUN validation")

    monkeypatch.setattr("requests.Session.request", _forbid_network, raising=True)

    conn = _StatefulConnection()
    payload = _build_payload()

    first_result = worker_module.execute_shopware_product_sync(payload, conn)
    assert first_result["status"] == "confirmed"
    assert len(conn.rows()) == 1

    row = conn.rows()[0]
    row["status"] = "pending"
    row["updated_at"] = datetime.now(timezone.utc)
    attempt_before = row["attempt"]

    monkeypatch.setattr(
        worker_module,
        "insert_shopware_operation_idempotent",
        lambda db_conn, product_number, payload: {"mode": "takeover", "operation_id": row["id"]},
        raising=True,
    )

    def _raise_api_error(self, _payload):
        raise worker_module.ShopwareApiError("boom")

    monkeypatch.setattr(worker_module.ShopwareApiClient, "upsert_product", _raise_api_error, raising=True)

    try:
        worker_module.execute_shopware_product_sync(payload, conn)
        raise AssertionError("Expected ShopwareApiError to propagate")
    except worker_module.ShopwareApiError as exc:
        assert str(exc) == "boom"

    assert len(conn.rows()) == 1
    assert row["status"] == "failed"
    assert row["attempt"] == attempt_before
    assert conn.commit_calls == 0


def test_shopware_product_sync_dry_run_persists_media_mapping(monkeypatch):
    config_stub = _ConfigStub(shopware_enable_dry_run=True)
    worker_module = _import_shopware_worker(config_stub, monkeypatch)

    monkeypatch.setattr(worker_module.ShopwareApiClient, "_ensure_token", lambda self: None, raising=True)

    def _forbid_network(*_args, **_kwargs):
        raise AssertionError("Network call is forbidden in DRY_RUN validation")

    monkeypatch.setattr("requests.Session.request", _forbid_network, raising=True)

    conn = _StatefulConnection()
    payload = _build_payload()
    payload["cdm_product"]["media_urls"] = [
        "https://cdn.example.local/images/sku-1.jpg",
        "https://cdn.example.local/images/sku-2.jpg",
    ]
    payload["cdm_product"]["attributes"] = {"brand_origin": "EU"}

    result = worker_module.execute_shopware_product_sync(payload, conn)

    assert result["status"] == "confirmed"
    assert len(conn.rows()) == 1
    assert conn.rows()[0]["status"] == "confirmed"
    assert len(conn.media_map) == 2
