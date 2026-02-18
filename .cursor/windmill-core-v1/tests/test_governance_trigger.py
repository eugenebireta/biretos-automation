from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

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


def _import_governance_trigger():
    _ensure_import_paths()
    return importlib.import_module("governance_trigger")


@dataclass
class _CfgStub:
    execution_mode: str = "LIVE"

    def __getattr__(self, _: str) -> Any:
        return None


class _Cursor:
    def __init__(self) -> None:
        self._rows: List[Any] = []

    def execute(self, query: str, params=None) -> None:
        normalized = " ".join(query.strip().lower().split())
        if normalized.startswith("select decision_seq, gate_name, policy_hash from control_decisions"):
            self._rows = [(5, "commercial_sanity", "ph")]
            return
        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self) -> None:
        return None


class _Conn:
    def cursor(self) -> _Cursor:
        return _Cursor()


def _install_fake_ru_worker(monkeypatch, calls: Dict[str, Any]) -> None:
    fake = ModuleType("ru_worker")

    def enqueue_job_with_trace(db_conn, job_type: str, payload: Dict[str, Any], idempotency_key: str, trace_id: Optional[str]):
        calls["enqueue"] = {
            "job_type": job_type,
            "payload": payload,
            "idempotency_key": idempotency_key,
            "trace_id": trace_id,
        }
        return uuid4()

    fake.enqueue_job_with_trace = enqueue_job_with_trace  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ru_worker", fake)


def test_trigger_happy_path(monkeypatch):
    gt = _import_governance_trigger()
    calls: Dict[str, Any] = {}
    _install_fake_ru_worker(monkeypatch, calls)

    def _tbank(_cfg, _payload):
        return {"status": "success", "result_status": "paid", "response": {"city": "X", "address": "Y", "name": "Z", "phone": "+1"}}

    def _mapper(_cfg, invoice_id: str, invoice_data: Dict[str, Any]):
        return ({"order_id": invoice_id, "to_location": {"city": "X", "address": "Y"}}, None)

    monkeypatch.setattr(gt, "execute_tbank_invoice_status", _tbank, raising=True)
    monkeypatch.setattr(gt, "map_tbank_invoice_to_cdek_payload", _mapper, raising=True)

    trace_id = str(uuid4())
    action = {"action_type": "ship_paid", "payload": {"invoice_id": "INV-1"}}
    pending = {"status": "pending_approval"}

    out = gt.handle_pending_approval(action, pending, _Conn(), trace_id=trace_id, config=_CfgStub())
    assert out["status"] == "governance_case_enqueued"
    assert "enqueue" in calls
    assert calls["enqueue"]["job_type"] == "governance_case_create"
    assert calls["enqueue"]["payload"]["trace_id"] == trace_id


def test_trigger_snapshot_has_required_fields(monkeypatch):
    gt = _import_governance_trigger()
    calls: Dict[str, Any] = {}
    _install_fake_ru_worker(monkeypatch, calls)

    monkeypatch.setattr(
        gt,
        "execute_tbank_invoice_status",
        lambda _cfg, _payload: {"status": "success", "result_status": "paid", "response": {"city": "X", "address": "Y", "name": "Z", "phone": "+1"}},
        raising=True,
    )
    monkeypatch.setattr(
        gt,
        "map_tbank_invoice_to_cdek_payload",
        lambda _cfg, invoice_id, _data: ({"order_id": invoice_id}, None),
        raising=True,
    )

    trace_id = str(uuid4())
    action = {"action_type": "ship_paid", "payload": {"invoice_id": "INV-2"}}
    pending = {"status": "pending_approval"}
    gt.handle_pending_approval(action, pending, _Conn(), trace_id=trace_id, config=_CfgStub())

    snap = calls["enqueue"]["payload"]["action_snapshot"]
    for k in (
        "schema_version",
        "action_type",
        "original_payload",
        "leaf_worker_type",
        "leaf_payload",
        "external_idempotency_key",
        "resolved_at",
        "resolution_source_snapshot",
    ):
        assert k in snap


def test_trigger_external_key_is_uuid(monkeypatch):
    gt = _import_governance_trigger()
    calls: Dict[str, Any] = {}
    _install_fake_ru_worker(monkeypatch, calls)

    monkeypatch.setattr(
        gt,
        "execute_tbank_invoice_status",
        lambda _cfg, _payload: {"status": "success", "result_status": "paid", "response": {"city": "X", "address": "Y", "name": "Z", "phone": "+1"}},
        raising=True,
    )
    monkeypatch.setattr(
        gt,
        "map_tbank_invoice_to_cdek_payload",
        lambda _cfg, invoice_id, _data: ({"order_id": invoice_id}, None),
        raising=True,
    )

    trace_id = str(uuid4())
    action = {"action_type": "ship_paid", "payload": {"invoice_id": "INV-3"}}
    pending = {"status": "pending_approval"}
    gt.handle_pending_approval(action, pending, _Conn(), trace_id=trace_id, config=_CfgStub())

    ext = calls["enqueue"]["payload"]["action_snapshot"]["external_idempotency_key"]
    UUID(str(ext))


def test_trigger_unsupported_action_type(monkeypatch):
    gt = _import_governance_trigger()
    calls: Dict[str, Any] = {}
    _install_fake_ru_worker(monkeypatch, calls)

    def _boom(*_a, **_k):
        raise AssertionError("should not be called")

    monkeypatch.setattr(gt, "execute_tbank_invoice_status", _boom, raising=True)
    monkeypatch.setattr(gt, "map_tbank_invoice_to_cdek_payload", _boom, raising=True)

    out = gt.handle_pending_approval({"action_type": "tbank_payment", "payload": {}}, {"status": "pending_approval"}, _Conn(), trace_id=str(uuid4()), config=_CfgStub())
    assert out["status"] == "error"
    assert "enqueue" not in calls


def test_trigger_resolution_failure_tbank(monkeypatch):
    gt = _import_governance_trigger()
    calls: Dict[str, Any] = {}
    _install_fake_ru_worker(monkeypatch, calls)

    def _tbank(_cfg, _payload):
        raise RuntimeError("tbank_down")

    monkeypatch.setattr(gt, "execute_tbank_invoice_status", _tbank, raising=True)

    with pytest.raises(RuntimeError):
        gt.handle_pending_approval({"action_type": "ship_paid", "payload": {"invoice_id": "INV-4"}}, {"status": "pending_approval"}, _Conn(), trace_id=str(uuid4()), config=_CfgStub())


def test_trigger_resolution_failure_mapping(monkeypatch):
    gt = _import_governance_trigger()
    calls: Dict[str, Any] = {}
    _install_fake_ru_worker(monkeypatch, calls)

    monkeypatch.setattr(
        gt,
        "execute_tbank_invoice_status",
        lambda _cfg, _payload: {"status": "success", "result_status": "paid", "response": {"city": "X", "address": "Y", "name": "Z", "phone": "+1"}},
        raising=True,
    )
    monkeypatch.setattr(gt, "map_tbank_invoice_to_cdek_payload", lambda *_a, **_k: (None, "bad"), raising=True)

    with pytest.raises(RuntimeError):
        gt.handle_pending_approval({"action_type": "ship_paid", "payload": {"invoice_id": "INV-5"}}, {"status": "pending_approval"}, _Conn(), trace_id=str(uuid4()), config=_CfgStub())


def test_trigger_idempotent_enqueue_key_format(monkeypatch):
    gt = _import_governance_trigger()
    calls: Dict[str, Any] = {}
    _install_fake_ru_worker(monkeypatch, calls)

    monkeypatch.setattr(
        gt,
        "execute_tbank_invoice_status",
        lambda _cfg, _payload: {"status": "success", "result_status": "paid", "response": {"city": "X", "address": "Y", "name": "Z", "phone": "+1"}},
        raising=True,
    )
    monkeypatch.setattr(
        gt,
        "map_tbank_invoice_to_cdek_payload",
        lambda _cfg, invoice_id, _data: ({"order_id": invoice_id}, None),
        raising=True,
    )

    trace_id = str(uuid4())
    gt.handle_pending_approval({"action_type": "ship_paid", "payload": {"invoice_id": "INV-6"}}, {"status": "pending_approval"}, _Conn(), trace_id=trace_id, config=_CfgStub())
    assert calls["enqueue"]["idempotency_key"].startswith(f"gov_trigger:{trace_id}:commercial_sanity:5")
