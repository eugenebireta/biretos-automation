from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_ROOT = Path(__file__).resolve().parents[2]  # windmill-core-v1/
_WORKERS = _ROOT / "workers"
for _p in (_ROOT, _WORKERS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

rc8_worker = importlib.import_module("shopware_reconciliation_worker")
run_rc8_shopware_reconciliation = rc8_worker.run_rc8_shopware_reconciliation


class _MockCursor:
    def __init__(self, conn: "_MockConn") -> None:
        self._conn = conn
        self._rows: List[Any] = []

    def execute(self, query: str, params: Optional[tuple[Any, ...]] = None) -> None:
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("insert into shopware_reconciliation_audit_log"):
            (
                trace_id,
                instance,
                check_code,
                entity_type,
                entity_id,
                core_value_json,
                external_value_json,
                drift_value,
                severity,
            ) = params
            self._conn.audit_rows.append(
                {
                    "trace_id": trace_id,
                    "instance": instance,
                    "check_code": check_code,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "core_value": core_value_json,
                    "external_value": external_value_json,
                    "drift_value": drift_value,
                    "severity": severity,
                }
            )
            self._rows = []
            return

        if normalized.startswith("insert into shopware_reconciliation_alerts"):
            trace_id, instance, check_code, severity, message_text, cooldown_key = params
            if cooldown_key in self._conn.alert_rows:
                self._rows = []
                return
            self._conn.alert_rows[cooldown_key] = {
                "trace_id": trace_id,
                "instance": instance,
                "check_code": check_code,
                "severity": severity,
                "message_text": message_text,
                "cooldown_key": cooldown_key,
            }
            self._rows = [("alert-id",)]
            return

        raise AssertionError(f"Unexpected SQL in RC-8 test cursor: {normalized}")

    def fetchone(self) -> Any:
        if not self._rows:
            return None
        return self._rows.pop(0)

    def close(self) -> None:
        return None


class _MockConn:
    def __init__(self) -> None:
        self.audit_rows: List[Dict[str, Any]] = []
        self.alert_rows: Dict[str, Dict[str, Any]] = {}
        self.commit_calls = 0

    def cursor(self) -> _MockCursor:
        return _MockCursor(self)

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        return None


def test_rc8_detects_stock_and_price_drift() -> None:
    conn = _MockConn()
    payload = {
        "trace_id": "00000000-0000-0000-0000-000000000111",
        "instance": "ru",
        "stock_warn_threshold": 5,
        "stock_critical_threshold": 20,
    }

    def _core_catalog(_db, _instance):
        return [{"sku": "SKU-1", "stock_quota": 10, "price_minor": 1000}]

    def _sw_catalog(_db, _instance):
        return [{"sku": "SKU-1", "stock": 1, "price_minor": 900}]

    result = run_rc8_shopware_reconciliation(
        conn,
        payload,
        core_catalog_fetcher=_core_catalog,
        shopware_catalog_fetcher=_sw_catalog,
    )

    assert result["audit_count"] == 2
    assert result["alert_count"] == 2
    assert result["critical_count"] == 0
    assert result["kill_switch"] is False
    assert conn.commit_calls == 1


def test_rc8_orphan_order_triggers_kill_switch() -> None:
    conn = _MockConn()
    payload = {
        "trace_id": "00000000-0000-0000-0000-000000000222",
        "instance": "ru",
        "kill_switch_critical_limit": 1,
    }

    now = datetime.now(timezone.utc)

    def _core_orders(_db, _instance):
        return []

    def _sw_orders(_db, _instance):
        return [{"order_number": "SO-100", "state": "open", "updated_at": now.isoformat()}]

    result = run_rc8_shopware_reconciliation(
        conn,
        payload,
        core_order_fetcher=_core_orders,
        shopware_order_fetcher=_sw_orders,
    )

    assert result["audit_count"] == 1
    assert result["critical_count"] == 1
    assert result["kill_switch"] is True
    assert any("RC8-KILL-SWITCH" in row["check_code"] for row in conn.alert_rows.values())


def test_rc8_order_state_mismatch_escalates_by_age() -> None:
    conn = _MockConn()
    payload = {
        "trace_id": "00000000-0000-0000-0000-000000000333",
        "instance": "int",
        "order_state_max_age_minutes": 30,
    }

    now = datetime.now(timezone.utc)

    def _core_orders(_db, _instance):
        return [
            {
                "order_number": "SO-200",
                "state": "shipped",
                "updated_at": (now - timedelta(minutes=45)).isoformat(),
            }
        ]

    def _sw_orders(_db, _instance):
        return [
            {
                "order_number": "SO-200",
                "state": "in_progress",
                "updated_at": (now - timedelta(minutes=35)).isoformat(),
            }
        ]

    result = run_rc8_shopware_reconciliation(
        conn,
        payload,
        core_order_fetcher=_core_orders,
        shopware_order_fetcher=_sw_orders,
    )

    assert result["audit_count"] == 1
    assert result["critical_count"] == 1
    assert result["kill_switch"] is False
    assert result["alert_count"] == 1
