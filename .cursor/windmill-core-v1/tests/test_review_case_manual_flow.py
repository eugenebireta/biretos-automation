from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

import ru_worker.review_case_manual_flow as review_case_manual_flow


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows: List[Any] = []
        self.rowcount = 0

    def execute(self, query: str, params=None) -> None:
        normalized = " ".join(query.strip().lower().split())
        params = params or ()
        self._rows = []
        self.rowcount = 0

        if normalized.startswith(
            "select id, trace_id, gate_name, status, assigned_to, original_decision_seq, policy_hash, action_snapshot, resume_context, resolved_by, resolution_decision_seq from review_cases where id = %s::uuid"
        ):
            row = self._conn.review_cases_by_id.get(str(params[0]))
            if row:
                self._rows = [
                    (
                        row["id"],
                        row["trace_id"],
                        row["gate_name"],
                        row["status"],
                        row["assigned_to"],
                        row["original_decision_seq"],
                        row["policy_hash"],
                        row["action_snapshot"],
                        row["resume_context"],
                        row["resolved_by"],
                        row["resolution_decision_seq"],
                    )
                ]
            return

        if normalized.startswith(
            "select id, status, assigned_to, trace_id, resume_context, created_at from review_cases where gate_name = %s and status in ('open', 'assigned') order by created_at desc limit %s"
        ):
            gate_name, limit = params
            active = [
                row for row in self._conn.review_cases_by_id.values()
                if row["gate_name"] == str(gate_name) and row["status"] in {"open", "assigned"}
            ]
            active.sort(key=lambda row: row["created_at"], reverse=True)
            self._rows = [
                (
                    row["id"],
                    row["status"],
                    row["assigned_to"],
                    row["trace_id"],
                    row["resume_context"],
                    row["created_at"],
                )
                for row in active[: int(limit)]
            ]
            return

        if normalized.startswith("update review_cases set status = 'assigned'"):
            assigned_to, case_id = params
            row = self._conn.review_cases_by_id.get(str(case_id))
            if row and row["status"] == "open":
                row["status"] = "assigned"
                row["assigned_to"] = str(assigned_to)
                row["assigned_at"] = "NOW()"
                self.rowcount = 1
            return

        if normalized.startswith("update review_cases set status = %s"):
            status, resolved_by, resolution_decision_seq, case_id = params
            row = self._conn.review_cases_by_id.get(str(case_id))
            if row and row["status"] in {"open", "assigned", "approved", "executing"}:
                row["status"] = str(status)
                row["resolved_by"] = str(resolved_by)
                row["resolution_decision_seq"] = int(resolution_decision_seq) if resolution_decision_seq is not None else None
                self.rowcount = 1
            return

        if normalized.startswith(
            "select coalesce(max(decision_seq), 0) + 1 from control_decisions where trace_id = %s::uuid"
        ):
            trace_id = str(params[0])
            seqs = [row["decision_seq"] for row in self._conn.control_decisions if row["trace_id"] == trace_id]
            self._rows = [(max(seqs) + 1 if seqs else 1,)]
            return

        if normalized.startswith("insert into control_decisions"):
            (
                trace_id,
                decision_seq,
                gate_name,
                verdict,
                schema_version,
                policy_hash,
                decision_context_json,
                reference_snapshot_json,
                replay_config_status,
            ) = params
            self._conn.control_decisions.append(
                {
                    "trace_id": str(trace_id),
                    "decision_seq": int(decision_seq),
                    "gate_name": str(gate_name),
                    "verdict": str(verdict),
                    "schema_version": str(schema_version),
                    "policy_hash": str(policy_hash),
                    "decision_context": json.loads(decision_context_json),
                    "reference_snapshot": json.loads(reference_snapshot_json),
                    "replay_config_status": replay_config_status,
                }
            )
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self) -> None:
        return None


class _Conn:
    def __init__(self) -> None:
        self.review_cases_by_id: Dict[str, Dict[str, Any]] = {}
        self.control_decisions: List[Dict[str, Any]] = []

    def cursor(self) -> _Cursor:
        return _Cursor(self)


def _seed_case(
    conn: _Conn,
    *,
    case_id: Optional[str] = None,
    status: str = "open",
    assigned_to: Optional[str] = None,
    gate_name: str = review_case_manual_flow.SEND_INVOICE_MANUAL_REVIEW_GATE,
) -> str:
    case_id = case_id or str(uuid4())
    conn.review_cases_by_id[case_id] = {
        "id": case_id,
        "trace_id": str(uuid4()),
        "gate_name": gate_name,
        "status": status,
        "assigned_to": assigned_to,
        "original_decision_seq": 2,
        "policy_hash": "send-invoice-day2-min-safe-v1",
        "action_snapshot": {"intent_type": "send_invoice", "manual_outcome": "insufficient_context"},
        "resume_context": {
            "manual_outcome": "insufficient_context",
            "reason": "send_invoice_requires_insales_order_id",
            "required_fields": ["insales_order_id"],
            "order_reference": {"insales_order_id": "ORDER-42"},
        },
        "resolved_by": None,
        "resolution_decision_seq": None,
        "created_at": f"2026-04-06T00:00:{len(conn.review_cases_by_id):02d}Z",
    }
    return case_id


def test_list_send_invoice_manual_cases_returns_active_only():
    conn = _Conn()
    open_case = _seed_case(conn, status="open")
    assigned_case = _seed_case(conn, status="assigned", assigned_to="42")
    _seed_case(conn, status="executed")

    result = review_case_manual_flow.list_send_invoice_manual_cases(conn, limit=10)

    assert result["status"] == "success"
    case_ids = [case["case_id"] for case in result["cases"]]
    assert open_case in case_ids
    assert assigned_case in case_ids
    assert len(case_ids) == 2


def test_assign_send_invoice_manual_case_updates_open_case():
    conn = _Conn()
    case_id = _seed_case(conn, status="open")

    result = review_case_manual_flow.assign_send_invoice_manual_case(conn, case_id=case_id, actor_id="77")

    assert result["status"] == "assigned"
    assert conn.review_cases_by_id[case_id]["status"] == "assigned"
    assert conn.review_cases_by_id[case_id]["assigned_to"] == "77"


def test_assign_send_invoice_manual_case_is_idempotent_for_same_actor():
    conn = _Conn()
    case_id = _seed_case(conn, status="assigned", assigned_to="77")

    result = review_case_manual_flow.assign_send_invoice_manual_case(conn, case_id=case_id, actor_id="77")

    assert result["status"] == "already_assigned"
    assert conn.review_cases_by_id[case_id]["assigned_to"] == "77"


def test_resolve_send_invoice_manual_case_requires_assignment():
    conn = _Conn()
    case_id = _seed_case(conn, status="open")

    result = review_case_manual_flow.resolve_send_invoice_manual_case(
        conn,
        case_id=case_id,
        actor_id="77",
        resolution_status="executed",
    )

    assert result["status"] == "needs_assignment"
    assert conn.review_cases_by_id[case_id]["status"] == "open"
    assert conn.control_decisions == []


def test_resolve_send_invoice_manual_case_records_human_decision_and_closed_cycle():
    conn = _Conn()
    case_id = _seed_case(conn, status="assigned", assigned_to="77")

    result = review_case_manual_flow.resolve_send_invoice_manual_case(
        conn,
        case_id=case_id,
        actor_id="77",
        resolution_status="executed",
    )

    assert result["status"] == "resolved"
    assert result["resolution_status"] == "executed"
    assert conn.review_cases_by_id[case_id]["status"] == "executed"
    gate_names = [row["gate_name"] for row in conn.control_decisions]
    assert gate_names == ["human_override", "closed_cycle_counter"]
    assert conn.control_decisions[0]["verdict"] == "HUMAN_APPROVE"
    assert conn.control_decisions[1]["verdict"] == "CLOSED"


def test_resolve_send_invoice_manual_case_reject_records_terminal_state():
    conn = _Conn()
    case_id = _seed_case(conn, status="assigned", assigned_to="77")

    result = review_case_manual_flow.resolve_send_invoice_manual_case(
        conn,
        case_id=case_id,
        actor_id="77",
        resolution_status="rejected",
    )

    assert result["status"] == "resolved"
    assert conn.review_cases_by_id[case_id]["status"] == "rejected"
    assert conn.control_decisions[0]["verdict"] == "HUMAN_REJECT"
    assert conn.control_decisions[1]["gate_name"] == "closed_cycle_counter"
