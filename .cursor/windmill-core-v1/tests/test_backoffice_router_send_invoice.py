from __future__ import annotations

import sys
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

import ru_worker.backoffice_router as backoffice_router


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows = []
        self.rowcount = 0

    def execute(self, query: str, params=None) -> None:
        normalized = " ".join(query.strip().lower().split())
        params = params or ()
        self._conn.queries.append((normalized, params))
        self._rows = []

        if normalized.startswith("select count(*) from employee_actions_log"):
            self._rows = [(0,)]
            return

        if normalized.startswith("select coalesce(max(decision_seq), 0) + 1 from control_decisions"):
            trace_id = str(params[0])
            seqs = [row["decision_seq"] for row in self._conn.control_decisions if row["trace_id"] == trace_id]
            self._rows = [(max(seqs) + 1 if seqs else 1,)]
            return

        if normalized.startswith("insert into control_decisions"):
            self._conn.control_decisions.append(
                {
                    "trace_id": str(params[0]),
                    "decision_seq": int(params[1]),
                    "gate_name": str(params[2]),
                    "verdict": str(params[3]),
                }
            )
            return

        if "insert into employee_actions_log" in normalized or "insert into shadow_rag_log" in normalized:
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self) -> None:
        return None


class _Conn:
    def __init__(self) -> None:
        self.queries = []
        self.control_decisions = []
        self.committed = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.committed += 1


def _payload() -> dict:
    return {
        "trace_id": "11111111-1111-1111-1111-111111111111",
        "intent_type": "send_invoice",
        "employee_id": "emp-1",
        "employee_role": "operator",
        "payload": {"insales_order_id": "ORDER-123"},
        "metadata": {},
    }


def test_send_invoice_insufficient_context_records_manual_metrics(monkeypatch):
    conn = _Conn()

    monkeypatch.setattr(
        backoffice_router,
        "execute_send_invoice",
        lambda db_conn, trace_id, payload: {
            "status": "insufficient_context",
            "intent_type": "send_invoice",
            "trace_id": trace_id,
            "error": "send_invoice_requires_insales_order_id",
            "message": "need order id",
            "required_fields": ["insales_order_id"],
        },
        raising=True,
    )

    result = backoffice_router.route_backoffice_intent(_payload(), conn)
    assert result["status"] == "insufficient_context"
    gates = [row["gate_name"] for row in conn.control_decisions]
    assert "manual_intervention" in gates
    assert "escalation_tracking" in gates
    assert conn.committed == 1


def test_send_invoice_success_records_closed_cycle(monkeypatch):
    conn = _Conn()

    monkeypatch.setattr(
        backoffice_router,
        "execute_send_invoice",
        lambda db_conn, trace_id, payload: {
            "status": "success",
            "intent_type": "send_invoice",
            "trace_id": trace_id,
            "provider_document_id": "TBANK-42",
            "invoice_number": "INV-42",
        },
        raising=True,
    )

    result = backoffice_router.route_backoffice_intent(_payload(), conn)
    assert result["status"] == "success"
    gates = [row["gate_name"] for row in conn.control_decisions]
    assert "closed_cycle_counter" in gates
