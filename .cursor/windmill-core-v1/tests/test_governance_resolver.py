from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Optional
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


def _import_governance_resolver():
    _ensure_import_paths()
    return importlib.import_module("governance_resolver")


_TEST_ENV_DEFAULTS = {
    "TELEGRAM_BOT_TOKEN": "test-token",
    "TELEGRAM_WEBHOOK_SECRET": "test-secret",
    "TBANK_API_TOKEN": "test-token",
    "TBANK_API_BASE": "https://example.test",
    "CDEK_CLIENT_ID": "test-id",
    "CDEK_CLIENT_SECRET": "test-secret",
    "POSTGRES_PASSWORD": "test-password",
}
for _k, _v in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_k, _v)


@dataclass
class _CfgStub:
    execution_mode: str = "LIVE"

    def __getattr__(self, _: str) -> Any:
        return None


class _Conn:
    pass


def _install_fake_ru_worker(monkeypatch, calls: Dict[str, Any]) -> None:
    fake = ModuleType("ru_worker")

    def enqueue_job_with_trace(db_conn, job_type: str, payload: Dict[str, Any], idempotency_key: str, trace_id: Optional[str]):
        calls["enqueue"] = {
            "db_conn": db_conn,
            "job_type": job_type,
            "payload": payload,
            "idempotency_key": idempotency_key,
            "trace_id": trace_id,
        }
        return uuid4()

    fake.enqueue_job_with_trace = enqueue_job_with_trace  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ru_worker", fake)


def test_resolver_approve_with_correction_happy_path(monkeypatch):
    gr = _import_governance_resolver()
    conn = _Conn()
    calls: Dict[str, Any] = {}
    _install_fake_ru_worker(monkeypatch, calls)

    monkeypatch.setattr(gr, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)
    monkeypatch.setattr(gr, "log_event", lambda *_a, **_k: None, raising=True)

    trace_id = str(uuid4())
    case_id = str(uuid4())

    monkeypatch.setattr(
        gr.governance_workflow,
        "read_case_for_resume",
        lambda *_a, **_k: {"status": "open", "trace_id": trace_id, "action_snapshot": {}},
        raising=True,
    )

    def _approve_with_correction(_db_conn, *, case_id: str, approved_by: str, corrections_content):
        calls["approve_with_correction"] = {
            "case_id": case_id,
            "approved_by": approved_by,
            "corrections_content": corrections_content,
        }
        return {"updated": True}

    monkeypatch.setattr(gr.governance_workflow, "approve_case_with_correction", _approve_with_correction, raising=True)
    monkeypatch.setattr(gr.governance_workflow, "approve_case", lambda *_a, **_k: {"updated": True}, raising=True)
    monkeypatch.setattr(gr.governance_workflow, "resolve_case", lambda *_a, **_k: {"updated": True}, raising=True)

    def _record(_db_conn, *, trace_id: str, policy_hash: str, corrections_content, decision_context=None, override_ref=None):
        calls["record"] = {
            "trace_id": trace_id,
            "policy_hash": policy_hash,
            "corrections_content": corrections_content,
            "decision_context": decision_context,
            "override_ref": override_ref,
        }
        return 17

    monkeypatch.setattr(gr.governance_decisions, "record_human_approve_with_correction", _record, raising=True)

    out = gr.execute_governance_resolve(
        {
            "case_id": case_id,
            "verdict": "HUMAN_APPROVE_WITH_CORRECTION",
            "resolved_by": "alice",
            "policy_hash": "ph",
            "decision_context": {"source": "manual"},
            "corrections_content": [{"field_path": "leaf_payload.order_id", "new_value": "INV-CORR"}],
        },
        conn,
    )

    assert out["status"] == "success"
    assert out["decision_seq"] == 17
    assert out["execution_enqueued"] is True
    assert calls["record"]["trace_id"] == trace_id
    assert calls["approve_with_correction"]["case_id"] == case_id
    assert calls["enqueue"]["job_type"] == "governance_execute"
    assert calls["enqueue"]["payload"] == {"case_id": case_id}
    assert calls["enqueue"]["idempotency_key"] == f"gov_exec_enqueue:{case_id}"
    assert calls["enqueue"]["trace_id"] == trace_id


def test_resolver_plain_approve_happy_path(monkeypatch):
    gr = _import_governance_resolver()
    conn = _Conn()
    calls: Dict[str, Any] = {}
    _install_fake_ru_worker(monkeypatch, calls)

    monkeypatch.setattr(gr, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)
    monkeypatch.setattr(gr, "log_event", lambda *_a, **_k: None, raising=True)

    case_id = str(uuid4())
    trace_id = str(uuid4())
    monkeypatch.setattr(
        gr.governance_workflow,
        "read_case_for_resume",
        lambda *_a, **_k: {"status": "assigned", "trace_id": trace_id, "action_snapshot": {}},
        raising=True,
    )

    monkeypatch.setattr(gr.governance_decisions, "record_human_approve", lambda *_a, **_k: 11, raising=True)
    monkeypatch.setattr(gr.governance_workflow, "approve_case", lambda *_a, **_k: {"updated": True}, raising=True)

    out = gr.execute_governance_resolve(
        {
            "case_id": case_id,
            "verdict": "HUMAN_APPROVE",
            "resolved_by": "alice",
            "policy_hash": "ph",
        },
        conn,
    )

    assert out["status"] == "success"
    assert out["verdict"] == "HUMAN_APPROVE"
    assert out["execution_enqueued"] is True
    assert calls["enqueue"]["idempotency_key"] == f"gov_exec_enqueue:{case_id}"


def test_resolver_reject_does_not_enqueue_execution(monkeypatch):
    gr = _import_governance_resolver()
    conn = _Conn()
    calls: Dict[str, Any] = {}
    _install_fake_ru_worker(monkeypatch, calls)

    monkeypatch.setattr(gr, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)
    monkeypatch.setattr(gr, "log_event", lambda *_a, **_k: None, raising=True)

    case_id = str(uuid4())
    trace_id = str(uuid4())
    monkeypatch.setattr(
        gr.governance_workflow,
        "read_case_for_resume",
        lambda *_a, **_k: {"status": "open", "trace_id": trace_id, "action_snapshot": {}},
        raising=True,
    )
    monkeypatch.setattr(gr.governance_decisions, "record_human_reject", lambda *_a, **_k: 23, raising=True)

    def _resolve(_db_conn, *, case_id: str, status: str, resolved_by: str, resolution_decision_seq: int):
        calls["resolve"] = {
            "case_id": case_id,
            "status": status,
            "resolved_by": resolved_by,
            "resolution_decision_seq": resolution_decision_seq,
        }
        return {"updated": True}

    monkeypatch.setattr(gr.governance_workflow, "resolve_case", _resolve, raising=True)

    out = gr.execute_governance_resolve(
        {
            "case_id": case_id,
            "verdict": "HUMAN_REJECT",
            "resolved_by": "alice",
            "policy_hash": "ph",
        },
        conn,
    )

    assert out["status"] == "success"
    assert out["execution_enqueued"] is False
    assert calls["resolve"]["status"] == "rejected"
    assert calls["resolve"]["resolution_decision_seq"] == 23
    assert "enqueue" not in calls


def test_resolver_already_resolved_returns_early(monkeypatch):
    gr = _import_governance_resolver()
    conn = _Conn()

    monkeypatch.setattr(gr, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)
    monkeypatch.setattr(
        gr.governance_workflow,
        "read_case_for_resume",
        lambda *_a, **_k: {"status": "approved", "trace_id": str(uuid4()), "action_snapshot": {}},
        raising=True,
    )

    out = gr.execute_governance_resolve(
        {
            "case_id": str(uuid4()),
            "verdict": "HUMAN_APPROVE",
            "resolved_by": "alice",
            "policy_hash": "ph",
        },
        conn,
    )

    assert out["status"] == "success"
    assert out["already_resolved"] is True
    assert out["case_status"] == "approved"


def test_resolver_missing_case_returns_error(monkeypatch):
    gr = _import_governance_resolver()
    conn = _Conn()

    monkeypatch.setattr(gr, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)
    monkeypatch.setattr(gr.governance_workflow, "read_case_for_resume", lambda *_a, **_k: None, raising=True)

    out = gr.execute_governance_resolve(
        {
            "case_id": str(uuid4()),
            "verdict": "HUMAN_APPROVE",
            "resolved_by": "alice",
            "policy_hash": "ph",
        },
        conn,
    )

    assert out["status"] == "error"
    assert out["reason"] == "case_not_found"


def test_resolver_invalid_verdict_raises(monkeypatch):
    gr = _import_governance_resolver()
    monkeypatch.setattr(gr, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)

    with pytest.raises(ValueError, match="unsupported verdict"):
        gr.execute_governance_resolve(
            {
                "case_id": str(uuid4()),
                "verdict": "BAD_VERDICT",
                "resolved_by": "alice",
                "policy_hash": "ph",
            },
            _Conn(),
        )


def test_resolver_correction_requires_non_empty_list(monkeypatch):
    gr = _import_governance_resolver()
    conn = _Conn()
    monkeypatch.setattr(gr, "get_config", lambda: _CfgStub(execution_mode="LIVE"), raising=True)
    monkeypatch.setattr(
        gr.governance_workflow,
        "read_case_for_resume",
        lambda *_a, **_k: {"status": "open", "trace_id": str(uuid4()), "action_snapshot": {}},
        raising=True,
    )

    with pytest.raises(ValueError, match="corrections_content must be a non-empty list"):
        gr.execute_governance_resolve(
            {
                "case_id": str(uuid4()),
                "verdict": "HUMAN_APPROVE_WITH_CORRECTION",
                "resolved_by": "alice",
                "policy_hash": "ph",
                "corrections_content": [],
            },
            conn,
        )


def test_resolver_replay_mode_skips(monkeypatch):
    gr = _import_governance_resolver()
    monkeypatch.setattr(gr, "get_config", lambda: _CfgStub(execution_mode="REPLAY"), raising=True)

    out = gr.execute_governance_resolve(
        {
            "case_id": str(uuid4()),
            "verdict": "HUMAN_APPROVE",
            "resolved_by": "alice",
            "policy_hash": "ph",
        },
        _Conn(),
    )

    assert out["status"] == "success"
    assert out["skipped"] is True
    assert out["reason"] == "replay_mode"
