"""
Tests for CDEKShipmentAdapter.get_waybill() — Phase 6.6.
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

import os

import pytest


# ---------------------------------------------------------------------------
# Helper: create adapter in dry_run mode without touching config file
# ---------------------------------------------------------------------------

def _make_adapter():
    """Create CDEKShipmentAdapter in dry_run mode via env override."""
    os.environ.setdefault("DRY_RUN_EXTERNAL_APIS", "true")
    # Lazy import after env is set
    from side_effects.adapters.cdek_adapter import CDEKShipmentAdapter
    adapter = CDEKShipmentAdapter.__new__(CDEKShipmentAdapter)
    adapter._api_url = "https://api.cdek.ru/v2/orders"
    adapter._token = ""
    adapter._dry_run = True
    return adapter


# ---------------------------------------------------------------------------
# get_waybill — dry_run tests
# ---------------------------------------------------------------------------

def test_get_waybill_dry_run_returns_pdf_bytes():
    from domain.ports import WaybillRequest
    adapter = _make_adapter()
    req = WaybillRequest(
        carrier_external_id="CDEK-UUID-WAYBILL-001",
        trace_id="trace-waybill-001",
    )
    resp = adapter.get_waybill(req)
    assert resp.pdf_bytes.startswith(b"%PDF")
    assert len(resp.pdf_bytes) > 0


def test_get_waybill_dry_run_carrier_id_preserved():
    from domain.ports import WaybillRequest
    adapter = _make_adapter()
    req = WaybillRequest(
        carrier_external_id="CDEK-UUID-WAYBILL-002",
        trace_id="trace-waybill-002",
    )
    resp = adapter.get_waybill(req)
    assert resp.carrier_external_id == "CDEK-UUID-WAYBILL-002"


def test_get_waybill_dry_run_raw_response_has_flag():
    from domain.ports import WaybillRequest
    adapter = _make_adapter()
    req = WaybillRequest(
        carrier_external_id="CDEK-UUID-WAYBILL-003",
        trace_id="trace-waybill-003",
    )
    resp = adapter.get_waybill(req)
    assert resp.raw_response.get("dry_run") is True


def test_get_waybill_no_token_dry_run_does_not_raise():
    """No CDEK token + dry_run=True must not raise RuntimeError."""
    from domain.ports import WaybillRequest
    adapter = _make_adapter()
    req = WaybillRequest(
        carrier_external_id="CDEK-UUID-WAYBILL-004",
        trace_id="trace-waybill-004",
    )
    # Must not raise RuntimeError("CDEK_API_TOKEN is not set")
    resp = adapter.get_waybill(req)
    assert resp is not None
