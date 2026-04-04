from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4


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

        if normalized.startswith("insert into review_cases"):
            (
                trace_id,
                order_id,
                gate_name,
                original_verdict,
                original_decision_seq,
                policy_hash,
                action_snapshot_json,
                resume_context_json,
                _sla_deadline_at,
                idempotency_key,
            ) = params
            key = str(idempotency_key)
            if key in self._conn.review_cases_by_key:
                self._rows = []
                return
            case_id = str(uuid4())
            row = {
                "id": case_id,
                "trace_id": str(trace_id),
                "order_id": str(order_id) if order_id is not None else None,
                "gate_name": str(gate_name),
                "original_verdict": str(original_verdict),
                "original_decision_seq": int(original_decision_seq),
                "policy_hash": str(policy_hash),
                "action_snapshot": str(action_snapshot_json),
                "resume_context": str(resume_context_json) if resume_context_json is not None else None,
                "status": "open",
                "idempotency_key": key,
            }
            self._conn.review_cases_by_key[key] = row
            self._conn.review_cases_by_id[case_id] = row
            self._rows = [(case_id, "open")]
            return

        if normalized.startswith("select id, status from review_cases where idempotency_key = %s"):
            row = self._conn.review_cases_by_key.get(str(params[0]))
            self._rows = [(row["id"], row["status"])] if row else []
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
        self.rolled_back = 0
        self.review_cases_by_key = {}
        self.review_cases_by_id = {}

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1


def _payload() -> dict:
    return {
        "trace_id": "11111111-1111-1111-1111-111111111111",
        "intent_type": "send_invoice",
        "employee_id": "emp-1",
        "employee_role": "operator",
        "payload": {"insales_order_id": "ORDER-123"},
        "metadata": {
            "nlu": {
                "confirmation_id": "confirm-1",
                "model_version": "regex-v1",
                "prompt_version": "v1.0",
                "confidence": 0.91,
            }
        },
    }


def test_send_invoice_insufficient_context_creates_review_case_and_records_metrics(monkeypatch):
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
    assert result["review_case_created"] is True
    assert result["review_case_gate_name"] == backoffice_router.SEND_INVOICE_MANUAL_REVIEW_GATE
    gates = [row["gate_name"] for row in conn.control_decisions]
    assert "manual_intervention" in gates
    assert "escalation_tracking" in gates
    assert len(conn.review_cases_by_key) == 1
    stored = next(iter(conn.review_cases_by_key.values()))
    assert stored["gate_name"] == backoffice_router.SEND_INVOICE_MANUAL_REVIEW_GATE
    assert stored["original_verdict"] == "NEEDS_HUMAN"
    assert stored["original_decision_seq"] == 1
    action_snapshot = json.loads(stored["action_snapshot"])
    assert action_snapshot["manual_outcome"] == "insufficient_context"
    assert action_snapshot["intent_type"] == "send_invoice"
    resume_context = json.loads(stored["resume_context"])
    assert resume_context["required_fields"] == ["insales_order_id"]
    assert resume_context["source"]["entrypoint"] == "assistant_nlu_confirm"
    assert conn.committed == 1


def test_send_invoice_review_required_creates_review_case(monkeypatch):
    conn = _Conn()

    monkeypatch.setattr(
        backoffice_router,
        "execute_send_invoice",
        lambda db_conn, trace_id, payload: {
            "status": "review_required",
            "intent_type": "send_invoice",
            "trace_id": trace_id,
            "error": "send_invoice_missing_customer_inn",
            "message": "manual review needed",
            "insales_order_id": "ORDER-123",
        },
        raising=True,
    )

    result = backoffice_router.route_backoffice_intent(_payload(), conn)
    assert result["status"] == "review_required"
    assert result["review_case_created"] is True
    stored = next(iter(conn.review_cases_by_key.values()))
    assert stored["original_decision_seq"] == 2
    resume_context = json.loads(stored["resume_context"])
    assert resume_context["required_fields"] == ["customer_data.inn"]
    assert resume_context["order_reference"]["insales_order_id"] == "ORDER-123"


def test_send_invoice_same_trace_and_outcome_is_idempotent_for_review_case(monkeypatch):
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

    result1 = backoffice_router.route_backoffice_intent(_payload(), conn)
    result2 = backoffice_router.route_backoffice_intent(_payload(), conn)
    assert result1["review_case_id"] == result2["review_case_id"]
    assert result1["review_case_created"] is True
    assert result2["review_case_created"] is False
    assert len(conn.review_cases_by_key) == 1


def test_send_invoice_review_case_creation_failure_rolls_back_and_raises(monkeypatch):
    conn = _Conn()

    monkeypatch.setattr(
        backoffice_router,
        "execute_send_invoice",
        lambda db_conn, trace_id, payload: {
            "status": "review_required",
            "intent_type": "send_invoice",
            "trace_id": trace_id,
            "error": "send_invoice_missing_customer_inn",
            "message": "manual review needed",
            "insales_order_id": "ORDER-123",
        },
        raising=True,
    )
    monkeypatch.setattr(
        backoffice_router,
        "_create_send_invoice_manual_review_case",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("review_case_insert_failed")),
        raising=True,
    )

    try:
        backoffice_router.route_backoffice_intent(_payload(), conn)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "review_case_insert_failed" in str(exc)
    assert conn.rolled_back == 1
    assert conn.committed == 0
    assert conn.control_decisions == []
    assert conn.review_cases_by_key == {}


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
