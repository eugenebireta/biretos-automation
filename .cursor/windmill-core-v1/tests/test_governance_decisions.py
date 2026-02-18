from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_paths() -> None:
    root = _project_root()
    ru_worker_dir = root / "ru_worker"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(ru_worker_dir) not in sys.path:
        sys.path.insert(0, str(ru_worker_dir))


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows: List[Any] = []

    def execute(self, query: str, params=None) -> None:
        params = params or ()
        normalized = " ".join(query.strip().lower().split())
        self._rows = []

        if normalized.startswith(
            "select coalesce(max(decision_seq), 0) + 1 from control_decisions where trace_id = %s::uuid"
        ):
            trace_id = str(params[0])
            max_seq = 0
            for row in self._conn.control_decisions:
                if row.get("trace_id") == trace_id:
                    max_seq = max(max_seq, int(row.get("decision_seq") or 0))
            self._rows = [(max_seq + 1,)]
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

    def close(self) -> None:
        return None


class _Conn:
    def __init__(self) -> None:
        self.control_decisions: List[Dict[str, Any]] = []

    def cursor(self) -> _Cursor:
        return _Cursor(self)


def _seed_control_decision(
    conn: _Conn,
    *,
    trace_id: str,
    decision_seq: int,
    gate_name: str,
    verdict: str,
    schema_version: str = "v3-test",
    policy_hash: str = "ph-test",
    decision_context: Optional[Dict[str, Any]] = None,
) -> None:
    conn.control_decisions.append(
        {
            "trace_id": trace_id,
            "decision_seq": int(decision_seq),
            "gate_name": gate_name,
            "verdict": verdict,
            "schema_version": schema_version,
            "policy_hash": policy_hash,
            "decision_context": dict(decision_context or {}),
            "reference_snapshot": {},
            "replay_config_status": None,
        }
    )


def _import_governance_decisions():
    _ensure_import_paths()
    import importlib

    return importlib.import_module("governance_decisions")


def test_record_human_approve_inserts_correctly():
    gd = _import_governance_decisions()
    conn = _Conn()
    trace_id = str(uuid4())

    seq = gd.record_human_approve(
        conn,
        trace_id=trace_id,
        policy_hash="ph1",
        decision_context={"user_id": 123},
        execution_mode="LIVE",
        schema_version="v3-test",
    )

    assert seq == 1
    assert len(conn.control_decisions) == 1
    row = conn.control_decisions[0]
    assert row["trace_id"] == trace_id
    assert row["decision_seq"] == 1
    assert row["gate_name"] == "human_override"
    assert row["verdict"] == gd.HUMAN_APPROVE
    assert row["schema_version"] == "v3-test"
    assert row["policy_hash"] == "ph1"
    assert row["decision_context"]["user_id"] == 123


def test_decision_seq_increments_with_mixed_gates():
    gd = _import_governance_decisions()
    conn = _Conn()
    trace_id = str(uuid4())

    _seed_control_decision(
        conn,
        trace_id=trace_id,
        decision_seq=1,
        gate_name="commercial_sanity",
        verdict="NEEDS_HUMAN",
    )

    seq = gd.record_human_approve(
        conn,
        trace_id=trace_id,
        policy_hash="ph2",
        decision_context={},
        execution_mode="LIVE",
        schema_version="v3-test",
    )

    assert seq == 2
    assert [r["decision_seq"] for r in conn.control_decisions if r["trace_id"] == trace_id] == [1, 2]
    assert conn.control_decisions[-1]["gate_name"] == "human_override"


def test_decision_seq_increments_for_same_gate():
    gd = _import_governance_decisions()
    conn = _Conn()
    trace_id = str(uuid4())

    s1 = gd.record_human_approve(
        conn,
        trace_id=trace_id,
        policy_hash="ph3",
        decision_context={},
        execution_mode="LIVE",
        schema_version="v3-test",
    )
    s2 = gd.record_human_reject(
        conn,
        trace_id=trace_id,
        policy_hash="ph3",
        decision_context={},
        execution_mode="LIVE",
        schema_version="v3-test",
    )

    assert s1 == 1
    assert s2 == 2
    assert [r["decision_seq"] for r in conn.control_decisions if r["trace_id"] == trace_id] == [1, 2]


def test_trace_id_none_raises():
    gd = _import_governance_decisions()
    conn = _Conn()
    with pytest.raises(ValueError):
        gd.record_human_approve(
            conn,
            trace_id=None,
            policy_hash="ph4",
            decision_context={},
            execution_mode="LIVE",
            schema_version="v3-test",
        )


def test_replay_mode_raises():
    gd = _import_governance_decisions()
    conn = _Conn()
    with pytest.raises(RuntimeError):
        gd.record_human_approve(
            conn,
            trace_id=str(uuid4()),
            policy_hash="ph5",
            decision_context={},
            execution_mode="REPLAY",
            schema_version="v3-test",
        )


def test_corrections_content_in_decision_context():
    gd = _import_governance_decisions()
    conn = _Conn()
    trace_id = str(uuid4())

    corrections = [{"field_path": "payload.reference_price", "new_value": 123}]
    seq = gd.record_human_approve_with_correction(
        conn,
        trace_id=trace_id,
        policy_hash="ph6",
        corrections_content=corrections,
        decision_context={"reason": "correct_reference_price"},
        execution_mode="LIVE",
        schema_version="v3-test",
    )

    assert seq == 1
    row = conn.control_decisions[0]
    assert row["verdict"] == gd.HUMAN_APPROVE_WITH_CORRECTION
    assert row["decision_context"]["corrections_content"] == corrections


def test_override_ref_in_decision_context():
    gd = _import_governance_decisions()
    conn = _Conn()
    trace_id = str(uuid4())

    seq = gd.record_human_approve(
        conn,
        trace_id=trace_id,
        policy_hash="ph7",
        decision_context={},
        override_ref=17,
        execution_mode="LIVE",
        schema_version="v3-test",
    )

    assert seq == 1
    row = conn.control_decisions[0]
    assert row["decision_context"]["override_ref"] == 17

