from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass
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
        self.rowcount = 0

    def execute(self, query: str, params=None) -> None:
        params = params or ()
        normalized = " ".join(query.strip().lower().split())
        self._rows = []
        self.rowcount = 0

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
                sla_deadline_at,
                idempotency_key,
            ) = params

            key = str(idempotency_key)
            if key in self._conn.review_cases_by_key:
                # ON CONFLICT DO NOTHING -> RETURNING yields no rows.
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
                "action_snapshot": action_snapshot_json,
                "resume_context": resume_context_json,
                "status": "open",
                "sla_deadline_at": sla_deadline_at,
                "escalation_level": 0,
                "idempotency_key": key,
                "assigned_to": None,
                "assigned_at": None,
                "resolved_at": None,
                "resolved_by": None,
                "resolution_decision_seq": None,
            }
            self._conn.review_cases_by_key[key] = row
            self._conn.review_cases_by_id[case_id] = row
            self._rows = [(case_id, "open")]
            return

        if normalized.startswith("select id, status from review_cases where idempotency_key = %s"):
            key = str(params[0])
            row = self._conn.review_cases_by_key.get(key)
            self._rows = [(row["id"], row["status"])] if row else []
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
            if row and row["status"] in {"open", "assigned", "approved"}:
                row["status"] = str(status)
                row["resolved_by"] = str(resolved_by)
                row["resolution_decision_seq"] = resolution_decision_seq
                row["resolved_at"] = "NOW()"
                self.rowcount = 1
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self) -> None:
        return None


class _Conn:
    def __init__(self) -> None:
        self.review_cases_by_key: Dict[str, Dict[str, Any]] = {}
        self.review_cases_by_id: Dict[str, Dict[str, Any]] = {}

    def cursor(self) -> _Cursor:
        return _Cursor(self)


def _import_governance_workflow():
    _ensure_import_paths()
    return importlib.import_module("governance_workflow")


def _import_governance_case_creator():
    _ensure_import_paths()
    return importlib.import_module("governance_case_creator")


@dataclass
class _ConfigStub:
    execution_mode: str = "LIVE"

    def __getattr__(self, _: str) -> Any:
        return None


def _import_ru_worker_isolated(monkeypatch, cfg: _ConfigStub):
    _ensure_import_paths()
    import config as config_pkg

    monkeypatch.setattr(config_pkg, "get_config", lambda: cfg, raising=True)

    module_name = "_phase2_ru_worker_isolated"
    sys.modules.pop(module_name, None)
    module_path = _project_root() / "ru_worker" / "ru_worker.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to import ru_worker/ru_worker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_create_review_case_inserts_correctly():
    gw = _import_governance_workflow()
    conn = _Conn()
    trace_id = str(uuid4())
    order_id = str(uuid4())

    res = gw.create_review_case(
        conn,
        trace_id=trace_id,
        order_id=order_id,
        gate_name="commercial_sanity",
        original_verdict="NEEDS_HUMAN",
        original_decision_seq=7,
        policy_hash="ph",
        action_snapshot={"a": 1},
        resume_context={"r": 1},
        sla_deadline_at=None,
    )

    assert res["created"] is True
    assert res["status"] == "open"
    assert isinstance(res["case_id"], str) and res["case_id"]
    key = f"review:{trace_id}:commercial_sanity:7"
    assert key in conn.review_cases_by_key


def test_create_review_case_idempotent():
    gw = _import_governance_workflow()
    conn = _Conn()
    trace_id = str(uuid4())

    r1 = gw.create_review_case(
        conn,
        trace_id=trace_id,
        order_id=None,
        gate_name="commercial_sanity",
        original_verdict="NEEDS_HUMAN",
        original_decision_seq=1,
        policy_hash="ph",
        action_snapshot={},
        resume_context=None,
        sla_deadline_at=None,
    )
    r2 = gw.create_review_case(
        conn,
        trace_id=trace_id,
        order_id=None,
        gate_name="commercial_sanity",
        original_verdict="NEEDS_HUMAN",
        original_decision_seq=1,
        policy_hash="ph",
        action_snapshot={},
        resume_context=None,
        sla_deadline_at=None,
    )

    assert r1["case_id"] == r2["case_id"]
    assert r1["created"] is True
    assert r2["created"] is False


def test_create_review_case_idempotency_key_format():
    gw = _import_governance_workflow()
    conn = _Conn()
    trace_id = str(uuid4())

    gw.create_review_case(
        conn,
        trace_id=trace_id,
        order_id=None,
        gate_name="commercial_sanity",
        original_verdict="NEEDS_HUMAN",
        original_decision_seq=99,
        policy_hash="ph",
        action_snapshot={},
        resume_context=None,
        sla_deadline_at=None,
    )

    expected = f"review:{trace_id}:commercial_sanity:99"
    assert expected in conn.review_cases_by_key


def test_assign_case():
    gw = _import_governance_workflow()
    conn = _Conn()
    trace_id = str(uuid4())

    created = gw.create_review_case(
        conn,
        trace_id=trace_id,
        order_id=None,
        gate_name="commercial_sanity",
        original_verdict="NEEDS_HUMAN",
        original_decision_seq=2,
        policy_hash="ph",
        action_snapshot={},
        resume_context=None,
        sla_deadline_at=None,
    )
    case_id = created["case_id"]

    upd = gw.assign_case(conn, case_id=case_id, assigned_to="alice")
    assert upd["updated"] is True
    row = conn.review_cases_by_id[case_id]
    assert row["status"] == "assigned"
    assert row["assigned_to"] == "alice"
    assert row["assigned_at"] is not None


def test_resolve_case():
    gw = _import_governance_workflow()
    conn = _Conn()
    trace_id = str(uuid4())

    created = gw.create_review_case(
        conn,
        trace_id=trace_id,
        order_id=None,
        gate_name="commercial_sanity",
        original_verdict="NEEDS_HUMAN",
        original_decision_seq=3,
        policy_hash="ph",
        action_snapshot={},
        resume_context=None,
        sla_deadline_at=None,
    )
    case_id = created["case_id"]
    gw.assign_case(conn, case_id=case_id, assigned_to="bob")

    upd = gw.resolve_case(conn, case_id=case_id, status="rejected", resolved_by="bob", resolution_decision_seq=10)
    assert upd["updated"] is True
    row = conn.review_cases_by_id[case_id]
    assert row["status"] == "rejected"
    assert row["resolved_by"] == "bob"
    assert row["resolution_decision_seq"] == 10
    assert row["resolved_at"] is not None


def test_case_creator_replay_skips(monkeypatch):
    gcc = _import_governance_case_creator()
    conn = _Conn()

    monkeypatch.setattr(gcc, "get_config", lambda: _ConfigStub(execution_mode="REPLAY"), raising=True)
    res = gcc.execute_governance_case_create(
        {
            "trace_id": str(uuid4()),
            "gate_name": "commercial_sanity",
            "original_decision_seq": 1,
            "policy_hash": "ph",
            "action_snapshot": {},
        },
        conn,
        trace_id=None,
    )

    assert res["status"] == "success"
    assert res["skipped"] is True
    assert conn.review_cases_by_key == {}


def test_case_creator_creates_case(monkeypatch):
    gcc = _import_governance_case_creator()
    conn = _Conn()

    monkeypatch.setattr(gcc, "get_config", lambda: _ConfigStub(execution_mode="LIVE"), raising=True)
    trace_id = str(uuid4())
    res = gcc.execute_governance_case_create(
        {
            "trace_id": trace_id,
            "order_id": str(uuid4()),
            "gate_name": "commercial_sanity",
            "original_verdict": "NEEDS_HUMAN",
            "original_decision_seq": 5,
            "policy_hash": "ph",
            "action_snapshot": {"x": 1},
            "resume_context": {"y": 2},
        },
        conn,
        trace_id=None,
    )

    assert res["status"] == "success"
    assert isinstance(res["case_id"], str) and res["case_id"]
    assert res["created"] is True
    assert f"review:{trace_id}:commercial_sanity:5" in conn.review_cases_by_key


def test_resolve_order_id_excluded(monkeypatch):
    ru = _import_ru_worker_isolated(monkeypatch, _ConfigStub(execution_mode="LIVE"))

    out = ru._resolve_order_id_for_cleanup(
        "governance_case_create",
        {"order_id": str(uuid4())},
        db_conn=None,
    )
    assert out is None

