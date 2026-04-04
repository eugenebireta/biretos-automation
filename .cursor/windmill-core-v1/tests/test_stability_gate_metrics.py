from __future__ import annotations

import json
import sys
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

from ru_worker.stability_gate_metrics import (
    CLOSED_CYCLE_COUNTER,
    ESCALATION_TRACKING,
    MANUAL_INTERVENTION,
    get_metric_counts,
    record_closed_cycle,
    record_escalation,
    record_manual_intervention,
)


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows = []

    def execute(self, query: str, params=None) -> None:
        normalized = " ".join(query.strip().lower().split())
        params = params or ()
        self._rows = []

        if normalized.startswith("select coalesce(max(decision_seq), 0) + 1 from control_decisions where trace_id = %s::uuid"):
            trace_id = str(params[0])
            seqs = [row["decision_seq"] for row in self._conn.rows if row["trace_id"] == trace_id]
            self._rows = [(max(seqs) + 1 if seqs else 1,)]
            return

        if normalized.startswith("insert into control_decisions"):
            self._conn.rows.append(
                {
                    "trace_id": str(params[0]),
                    "decision_seq": int(params[1]),
                    "gate_name": str(params[2]),
                    "verdict": str(params[3]),
                    "decision_context": json.loads(params[6]),
                }
            )
            return

        if normalized.startswith("select gate_name, count(*) from control_decisions"):
            counts = {}
            for row in self._conn.rows:
                gate_name = row["gate_name"]
                counts[gate_name] = counts.get(gate_name, 0) + 1
            self._rows = list(counts.items())
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows = list(self._rows)
        self._rows = []
        return rows

    def close(self) -> None:
        return None


class _Conn:
    def __init__(self) -> None:
        self.rows = []

    def cursor(self) -> _Cursor:
        return _Cursor(self)


def test_records_all_day2_stability_metrics():
    conn = _Conn()
    trace_id = "11111111-1111-1111-1111-111111111111"

    record_manual_intervention(conn, trace_id=trace_id, intent_type="send_invoice", reason="missing_context")
    record_escalation(conn, trace_id=trace_id, intent_type="send_invoice", reason="review_required")
    record_closed_cycle(conn, trace_id=trace_id, intent_type="send_invoice")

    counts = get_metric_counts(conn, hours=24)
    assert counts[MANUAL_INTERVENTION] == 1
    assert counts[ESCALATION_TRACKING] == 1
    assert counts[CLOSED_CYCLE_COUNTER] == 1
