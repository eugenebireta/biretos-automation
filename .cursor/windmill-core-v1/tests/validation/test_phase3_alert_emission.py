from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import_alerts():
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("domain.reconciliation_alerts")


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows = []
        self.rowcount = 0

    def execute(self, query: str, params=None):
        params = params or ()
        normalized = " ".join(query.strip().lower().split())

        if normalized.startswith("insert into reconciliation_alerts"):
            # params: sweep_trace_id, check_code, entity_type, entity_id, severity, verdict_snapshot, notification_key
            notification_key = str(params[6])
            if notification_key in self._conn.alerts_by_key:
                self._rows = []
                return
            alert_id = f"alert-{len(self._conn.alerts_by_key) + 1}"
            self._conn.alerts_by_key[notification_key] = {
                "id": alert_id,
                "notification_state": "pending",
                "notification_key": notification_key,
            }
            self._rows = [(alert_id,)]
            return

        if normalized.startswith("update reconciliation_alerts set notification_state = 'acked'"):
            alert_id = str(params[0])
            updated = False
            for row in self._conn.alerts_by_key.values():
                if row["id"] == alert_id and row["notification_state"] != "acked":
                    row["notification_state"] = "acked"
                    updated = True
            self.rowcount = 1 if updated else 0
            self._rows = []
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        return None


class _Conn:
    def __init__(self):
        self.alerts_by_key = {}

    def cursor(self):
        return _Cursor(self)


def test_emit_alert_created_then_duplicate():
    alerts = _import_alerts()
    conn = _Conn()

    first = alerts.emit_alert(
        conn,
        sweep_trace_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        check_code="L3-A",
        entity_type="stock",
        entity_id="p1:wh1",
        severity="CRITICAL",
        verdict_snapshot={"x": 1},
    )
    assert first["action"] == "created"

    second = alerts.emit_alert(
        conn,
        sweep_trace_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        check_code="L3-A",
        entity_type="stock",
        entity_id="p1:wh1",
        severity="CRITICAL",
        verdict_snapshot={"x": 2},
    )
    assert second["action"] == "duplicate"


def test_emit_batch_alert_uses_unique_key():
    alerts = _import_alerts()
    conn = _Conn()

    r1 = alerts.emit_batch_alert(
        conn,
        sweep_trace_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        check_code="L3-D",
        severity="MEDIUM",
        sample=[{"entity_id": "r1"}],
        total_count=11,
    )
    assert r1["action"] == "created"

    r2 = alerts.emit_batch_alert(
        conn,
        sweep_trace_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        check_code="L3-D",
        severity="MEDIUM",
        sample=[{"entity_id": "r2"}],
        total_count=12,
    )
    assert r2["action"] == "duplicate"


def test_ack_alert_updates_state():
    alerts = _import_alerts()
    conn = _Conn()

    created = alerts.emit_alert(
        conn,
        sweep_trace_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        check_code="L3-A",
        entity_type="stock",
        entity_id="p2:wh2",
        severity="CRITICAL",
        verdict_snapshot={"x": 1},
    )
    assert created["action"] == "created"
    alert_id = created["alert_id"]

    res = alerts.ack_alert(conn, alert_id=alert_id)
    assert res["updated"] is True

