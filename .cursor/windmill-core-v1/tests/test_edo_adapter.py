"""
Tests for side_effects/adapters/edo_adapter.py — Phase 6.5.
Pure unit tests: dry_run mode only, no live HTTP, deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

import pytest

from side_effects.adapters.edo_adapter import (
    SberkorpEDOAdapter,
    SBISEDOAdapter,
    get_edo_adapter,
)
from domain.ports import EDOSendRequest, EDOStatusRequest


# ---------------------------------------------------------------------------
# SberkorpEDOAdapter
# ---------------------------------------------------------------------------

def _send_req(document_type: str = "invoice", trace_id: str = "trace-edo-001") -> "EDOSendRequest":
    return EDOSendRequest(
        document_type=document_type,
        recipient_inn="7700000001",
        document_id="DOC-001",
        payload={"key": "value"},
        trace_id=trace_id,
    )


def _status_req(edo_document_id: str, provider: str = "sberkorus", trace_id: str = "trace-edo-s") -> "EDOStatusRequest":
    return EDOStatusRequest(
        edo_document_id=edo_document_id,
        provider=provider,
        trace_id=trace_id,
    )


def test_sberkorus_send_document_dry_run():
    adapter = SberkorpEDOAdapter(dry_run=True)
    resp = adapter.send_document(_send_req())
    assert resp.provider == "sberkorus"
    assert resp.edo_document_id.startswith("SBKR-DRY-")
    assert resp.raw_response.get("dry_run") is True


def test_sberkorus_get_document_status_dry_run():
    adapter = SberkorpEDOAdapter(dry_run=True)
    resp = adapter.get_document_status(_status_req("SBKR-DRY-ABCDEF12", provider="sberkorus"))
    assert resp.provider == "sberkorus"
    assert resp.edo_document_id == "SBKR-DRY-ABCDEF12"
    assert resp.provider_status == "dry_run_pending"
    assert resp.raw_response.get("dry_run") is True


def test_sberkorus_no_api_key_forces_dry_run():
    adapter = SberkorpEDOAdapter(api_key="", dry_run=False)
    # No key → still dry_run
    resp = adapter.send_document(_send_req(trace_id="trace-edo-003"))
    assert resp.raw_response.get("dry_run") is True


def test_sberkorus_send_returns_unique_ids():
    adapter = SberkorpEDOAdapter(dry_run=True)
    id1 = adapter.send_document(_send_req(trace_id="trace-edo-004a")).edo_document_id
    id2 = adapter.send_document(_send_req(trace_id="trace-edo-004b")).edo_document_id
    assert id1 != id2


def test_sberkorus_send_document_type_in_response():
    adapter = SberkorpEDOAdapter(dry_run=True)
    resp = adapter.send_document(_send_req(document_type="act", trace_id="trace-edo-005"))
    assert resp.raw_response.get("document_type") == "act"


# ---------------------------------------------------------------------------
# SBISEDOAdapter
# ---------------------------------------------------------------------------

def test_sbis_send_document_dry_run():
    adapter = SBISEDOAdapter(dry_run=True)
    resp = adapter.send_document(_send_req(trace_id="trace-sbis-001"))
    assert resp.provider == "sbis"
    assert resp.edo_document_id.startswith("SBIS-DRY-")
    assert resp.raw_response.get("dry_run") is True


def test_sbis_get_document_status_dry_run():
    adapter = SBISEDOAdapter(dry_run=True)
    resp = adapter.get_document_status(_status_req("SBIS-DRY-12345678", provider="sbis", trace_id="trace-sbis-002"))
    assert resp.provider == "sbis"
    assert resp.provider_status == "dry_run_pending"


def test_sbis_no_api_key_forces_dry_run():
    adapter = SBISEDOAdapter(api_key="", dry_run=False)
    resp = adapter.send_document(_send_req(trace_id="trace-sbis-003"))
    assert resp.raw_response.get("dry_run") is True


# ---------------------------------------------------------------------------
# Factory — get_edo_adapter
# ---------------------------------------------------------------------------

def test_factory_returns_sberkorus():
    adapter = get_edo_adapter(provider="sberkorus", dry_run=True)
    assert isinstance(adapter, SberkorpEDOAdapter)


def test_factory_returns_sbis():
    adapter = get_edo_adapter(provider="sbis", dry_run=True)
    assert isinstance(adapter, SBISEDOAdapter)


def test_factory_case_insensitive():
    adapter = get_edo_adapter(provider="SBERKORUS", dry_run=True)
    assert isinstance(adapter, SberkorpEDOAdapter)


def test_factory_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown EDO provider"):
        get_edo_adapter(provider="kontur", dry_run=True)
