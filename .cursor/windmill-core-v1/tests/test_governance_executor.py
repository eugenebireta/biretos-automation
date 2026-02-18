from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
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


def _import_governance_executor():
    _ensure_import_paths()
    return importlib.import_module("governance_executor")


@dataclass
class _CfgStub:
    execution_mode: str = "LIVE"

    def __getattr__(self, _: str) -> Any:
        return None


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self._conn = conn
        self._rows: List[Any] = []

    def execute(self, query: str, params=None) -> None:
        params = params or ()
        normalized = " ".join(query.strip().lower().split())
        if normalized.startswith("select status from review_cases where id = %s::uuid"):
            self._rows = [(self._conn.case_status,)] if self._conn.case_status is not None else []
            return
        if normalized.startswith("select status from action_idempotency_log where idempotency_key = %s"):
            self._rows = [(self._conn.log_status,)] if self._conn.log_status is not None else []
            return
        if normalized.startswith("delete from action_idempotency_log where idempotency_key = %s and status = 'failed'"):
            self._conn.deleted.append(str(params[0]))
            return
        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self) -> None:
        return None


class _Conn:
    def __init__(self, *, case_status: Optional[str] = None, log_status: Optional[str] = None) -> None:
        self.case_status = case_status
        self.log_status = log_status
        self.deleted: List[str] = []
        self.commits = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None


def _valid_snapshot(*, ext_key: str) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "leaf_worker_type": "cdek_shipment",
        "leaf_payload": {"order_id": "INV-ORIG"},
        "external_idempotency_key": ext_key,
    }


def test_executor_happy_path(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn()

    ext = str(uuid4())
    calls: Dict[str, Any] = {"mark": 0, "resolve": 0, "complete": []}

    gw = SimpleNamespace(
        claim_for_execution=lambda _db, *, case_id: {"action_snapshot": _valid_snapshot(ext_key=ext), "trace_id": str(uuid4())},
        read_case_for_resume=lambda *_a, **_k: None,
        resolve_case=lambda *_a, **_k: calls.__setitem__("resolve", calls["resolve"] + 1),
        mark_executed=lambda *_a, **_k: calls.__setitem__("mark", calls["mark"] + 1) or {"updated": True},
    )
    monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)

    monkeypatch.setattr(
        ge,
        "acquire_action_lock",
        lambda **_k: {"status": "ACQUIRED", "lease_token": "lt", "attempt_count": 1},
        raising=True,
    )

    def _complete(**kwargs):
        calls["complete"].append(kwargs["status"])
        return True

    monkeypatch.setattr(ge, "complete_action", _complete, raising=True)

    def _leaf(_cfg, payload):
        assert payload["order_id"] == ext
        return {"status": "success", "result": {"ok": True}}

    monkeypatch.setattr(ge, "execute_cdek_shipment", _leaf, raising=True)
    monkeypatch.setattr(ge, "log_event", lambda *_a, **_k: None, raising=True)

    out = ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=str(uuid4()))
    assert out["status"] == "success"
    assert calls["mark"] == 1
    assert calls["resolve"] == 0
    assert calls["complete"] == ["succeeded"]
    assert conn.commits == 2


def test_executor_replay_verified(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn(case_status="executed", log_status="succeeded")
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="REPLAY"), raising=True)
    out = ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=None)
    assert out["status"] == "replay_verified"


def test_executor_replay_divergence_executing(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn(case_status="executing", log_status="processing")
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="REPLAY"), raising=True)
    out = ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=None)
    assert out["status"] == "replay_divergence"
    assert out["reason"] == "incomplete_execution"


def test_executor_replay_divergence_approved(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn(case_status="approved", log_status=None)
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="REPLAY"), raising=True)
    out = ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=None)
    assert out["status"] == "replay_divergence"
    assert out["reason"] == "never_executed"


def test_executor_replay_divergence_cancelled(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn(case_status="cancelled", log_status="failed")
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="REPLAY"), raising=True)
    out = ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=None)
    assert out["status"] == "replay_divergence"
    assert out["reason"] == "execution_cancelled"


def test_executor_claim_race_loses(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn()

    gw = SimpleNamespace(
        claim_for_execution=lambda *_a, **_k: None,
        read_case_for_resume=lambda *_a, **_k: {"status": "approved", "action_snapshot": {}, "trace_id": str(uuid4())},
        resolve_case=lambda *_a, **_k: {"updated": True},
        mark_executed=lambda *_a, **_k: {"updated": True},
    )
    monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)

    out = ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=str(uuid4()))
    assert out["status"] == "skipped"
    assert out["reason"].startswith("unexpected_status:")
    assert conn.commits == 1


def test_executor_resume_no_idempotency_row(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn()

    ext = str(uuid4())
    gw = SimpleNamespace(
        claim_for_execution=lambda *_a, **_k: None,
        read_case_for_resume=lambda *_a, **_k: {"status": "executing", "action_snapshot": _valid_snapshot(ext_key=ext), "trace_id": str(uuid4())},
        resolve_case=lambda *_a, **_k: {"updated": True},
        mark_executed=lambda *_a, **_k: {"updated": True},
    )
    monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)
    monkeypatch.setattr(ge, "acquire_action_lock", lambda **_k: {"status": "ACQUIRED", "lease_token": "lt"}, raising=True)
    monkeypatch.setattr(ge, "complete_action", lambda **_k: True, raising=True)
    monkeypatch.setattr(ge, "execute_cdek_shipment", lambda *_a, **_k: {"status": "success"}, raising=True)
    monkeypatch.setattr(ge, "log_event", lambda *_a, **_k: None, raising=True)

    out = ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=str(uuid4()))
    assert out["status"] == "success"
    assert conn.commits == 2


def test_executor_resume_sweeper_failed_lock(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn()

    ext = str(uuid4())
    gw = SimpleNamespace(
        claim_for_execution=lambda *_a, **_k: None,
        read_case_for_resume=lambda *_a, **_k: {"status": "executing", "action_snapshot": _valid_snapshot(ext_key=ext), "trace_id": str(uuid4())},
        resolve_case=lambda *_a, **_k: {"updated": True},
        mark_executed=lambda *_a, **_k: {"updated": True},
    )
    monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)

    seq = {"i": 0}

    def _acquire(**_k):
        seq["i"] += 1
        if seq["i"] == 1:
            return {"status": "DUPLICATE_FAILED", "last_error": "lock_expired_by_sweeper"}
        return {"status": "ACQUIRED", "lease_token": "lt"}

    monkeypatch.setattr(ge, "acquire_action_lock", _acquire, raising=True)
    monkeypatch.setattr(ge, "complete_action", lambda **_k: True, raising=True)
    monkeypatch.setattr(ge, "execute_cdek_shipment", lambda *_a, **_k: {"status": "success"}, raising=True)
    monkeypatch.setattr(ge, "log_event", lambda *_a, **_k: None, raising=True)

    case_id = str(uuid4())
    out = ge.execute_governance_case({"case_id": case_id}, conn, trace_id=str(uuid4()))
    assert out["status"] == "success"
    assert conn.deleted == [f"gov_exec:{case_id}"]
    assert conn.commits == 3


def test_executor_genuine_failure_no_retry(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn()

    ext = str(uuid4())
    gw = SimpleNamespace(
        claim_for_execution=lambda *_a, **_k: None,
        read_case_for_resume=lambda *_a, **_k: {"status": "executing", "action_snapshot": _valid_snapshot(ext_key=ext), "trace_id": str(uuid4())},
        resolve_case=lambda *_a, **_k: {"updated": True},
        mark_executed=lambda *_a, **_k: {"updated": True},
    )
    monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)
    monkeypatch.setattr(ge, "acquire_action_lock", lambda **_k: {"status": "DUPLICATE_FAILED", "last_error": "boom"}, raising=True)

    out = ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=str(uuid4()))
    assert out["status"] == "failed"
    assert out["last_error"] == "boom"
    assert conn.deleted == []
    assert conn.commits == 1


def test_executor_duplicate_succeeded(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn()

    ext = str(uuid4())
    calls: Dict[str, Any] = {"mark": 0}
    gw = SimpleNamespace(
        claim_for_execution=lambda _db, *, case_id: {"action_snapshot": _valid_snapshot(ext_key=ext), "trace_id": str(uuid4())},
        read_case_for_resume=lambda *_a, **_k: None,
        resolve_case=lambda *_a, **_k: {"updated": True},
        mark_executed=lambda *_a, **_k: calls.__setitem__("mark", calls["mark"] + 1) or {"updated": True},
    )
    monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)
    monkeypatch.setattr(ge, "acquire_action_lock", lambda **_k: {"status": "DUPLICATE_SUCCEEDED", "result_ref": {}}, raising=True)
    monkeypatch.setattr(ge, "execute_cdek_shipment", lambda *_a, **_k: {"status": "error"}, raising=True)
    monkeypatch.setattr(ge, "complete_action", lambda **_k: True, raising=True)

    out = ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=str(uuid4()))
    assert out["status"] == "success"
    assert calls["mark"] == 1
    assert conn.commits == 2


def test_executor_duplicate_processing(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn()

    ext = str(uuid4())
    gw = SimpleNamespace(
        claim_for_execution=lambda _db, *, case_id: {"action_snapshot": _valid_snapshot(ext_key=ext), "trace_id": str(uuid4())},
        read_case_for_resume=lambda *_a, **_k: None,
        resolve_case=lambda *_a, **_k: {"updated": True},
        mark_executed=lambda *_a, **_k: {"updated": True},
    )
    monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)
    monkeypatch.setattr(ge, "acquire_action_lock", lambda **_k: {"status": "DUPLICATE_PROCESSING"}, raising=True)

    out = ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=str(uuid4()))
    assert out["status"] == "skipped"
    assert out["reason"] == "another_worker_processing"
    assert conn.commits == 1


def test_executor_leaf_failure_marks_cancelled(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn()

    ext = str(uuid4())
    calls: Dict[str, Any] = {"resolve": 0, "complete": []}
    gw = SimpleNamespace(
        claim_for_execution=lambda _db, *, case_id: {"action_snapshot": _valid_snapshot(ext_key=ext), "trace_id": str(uuid4())},
        read_case_for_resume=lambda *_a, **_k: None,
        resolve_case=lambda *_a, **_k: calls.__setitem__("resolve", calls["resolve"] + 1) or {"updated": True},
        mark_executed=lambda *_a, **_k: {"updated": True},
    )
    monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)
    monkeypatch.setattr(ge, "acquire_action_lock", lambda **_k: {"status": "ACQUIRED", "lease_token": "lt"}, raising=True)

    def _complete(**kwargs):
        calls["complete"].append(kwargs["status"])
        return True

    monkeypatch.setattr(ge, "complete_action", _complete, raising=True)
    monkeypatch.setattr(ge, "execute_cdek_shipment", lambda *_a, **_k: {"status": "error", "error": "bad"}, raising=True)
    monkeypatch.setattr(ge, "log_event", lambda *_a, **_k: None, raising=True)

    out = ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=str(uuid4()))
    assert out["status"] == "error"
    assert calls["resolve"] == 1
    assert calls["complete"] == ["failed"]
    assert conn.commits == 2


def test_executor_snapshot_validation_failure(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn()

    calls: Dict[str, Any] = {"resolve": 0}
    gw = SimpleNamespace(
        claim_for_execution=lambda _db, *, case_id: {"action_snapshot": {"schema_version": 1}, "trace_id": str(uuid4())},
        read_case_for_resume=lambda *_a, **_k: None,
        resolve_case=lambda *_a, **_k: calls.__setitem__("resolve", calls["resolve"] + 1) or {"updated": True},
        mark_executed=lambda *_a, **_k: {"updated": True},
    )
    monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)

    out = ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=str(uuid4()))
    assert out["status"] == "error"
    assert calls["resolve"] == 1
    assert conn.commits == 2


def test_executor_external_key_injected(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn()

    ext = str(uuid4())
    gw = SimpleNamespace(
        claim_for_execution=lambda _db, *, case_id: {"action_snapshot": _valid_snapshot(ext_key=ext), "trace_id": str(uuid4())},
        read_case_for_resume=lambda *_a, **_k: None,
        resolve_case=lambda *_a, **_k: {"updated": True},
        mark_executed=lambda *_a, **_k: {"updated": True},
    )
    monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)
    monkeypatch.setattr(ge, "acquire_action_lock", lambda **_k: {"status": "ACQUIRED", "lease_token": "lt"}, raising=True)
    monkeypatch.setattr(ge, "complete_action", lambda **_k: True, raising=True)

    seen: Dict[str, Any] = {}

    def _leaf(_cfg, payload):
        seen["order_id"] = payload["order_id"]
        return {"status": "success"}

    monkeypatch.setattr(ge, "execute_cdek_shipment", _leaf, raising=True)
    monkeypatch.setattr(ge, "log_event", lambda *_a, **_k: None, raising=True)

    ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=str(uuid4()))
    assert seen["order_id"] == ext


def test_executor_cdek_409_treated_as_success(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn()

    ext = str(uuid4())
    calls: Dict[str, Any] = {"resolve": 0, "complete": []}
    gw = SimpleNamespace(
        claim_for_execution=lambda _db, *, case_id: {"action_snapshot": _valid_snapshot(ext_key=ext), "trace_id": str(uuid4())},
        read_case_for_resume=lambda *_a, **_k: None,
        resolve_case=lambda *_a, **_k: calls.__setitem__("resolve", calls["resolve"] + 1) or {"updated": True},
        mark_executed=lambda *_a, **_k: {"updated": True},
    )
    monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)
    monkeypatch.setattr(ge, "acquire_action_lock", lambda **_k: {"status": "ACQUIRED", "lease_token": "lt"}, raising=True)

    def _complete(**kwargs):
        calls["complete"].append(kwargs["status"])
        return True

    monkeypatch.setattr(ge, "complete_action", _complete, raising=True)
    monkeypatch.setattr(ge, "execute_cdek_shipment", lambda *_a, **_k: {"status": "error", "error": "HTTP 409: already exists"}, raising=True)
    monkeypatch.setattr(ge, "log_event", lambda *_a, **_k: None, raising=True)

    out = ge.execute_governance_case({"case_id": str(uuid4())}, conn, trace_id=str(uuid4()))
    assert out["status"] == "success"
    assert calls["resolve"] == 0
    assert calls["complete"] == ["succeeded"]


def test_executor_step3b_retry_limit(monkeypatch):
    ge = _import_governance_executor()
    conn = _Conn()

    ext = str(uuid4())
    gw = SimpleNamespace(
        claim_for_execution=lambda *_a, **_k: None,
        read_case_for_resume=lambda *_a, **_k: {"status": "executing", "action_snapshot": _valid_snapshot(ext_key=ext), "trace_id": str(uuid4())},
        resolve_case=lambda *_a, **_k: {"updated": True},
        mark_executed=lambda *_a, **_k: {"updated": True},
    )
    monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
    monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)

    monkeypatch.setattr(
        ge,
        "acquire_action_lock",
        lambda **_k: {"status": "DUPLICATE_FAILED", "last_error": "lock_expired_by_sweeper"},
        raising=True,
    )

    case_id = str(uuid4())
    out = ge.execute_governance_case({"case_id": case_id}, conn, trace_id=str(uuid4()))
    assert out["status"] == "failed"
    assert out["last_error"] == "lock_expired_by_sweeper"
    assert conn.deleted == [f"gov_exec:{case_id}"]
    assert conn.commits == 2
