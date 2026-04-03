"""
Tests for CDEKShipmentAdapter.get_waybill() — 3-step print flow.
Mocks httpx to verify: tracking→UUID lookup, POST print task, GET PDF download.
No live HTTP, deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

import os

os.environ.setdefault("DRY_RUN_EXTERNAL_APIS", "false")


# ---------------------------------------------------------------------------
# Helper: build adapter in non-dry-run mode with a fake token
# ---------------------------------------------------------------------------

def _make_real_adapter():
    from side_effects.adapters.cdek_adapter import CDEKShipmentAdapter

    adapter = CDEKShipmentAdapter.__new__(CDEKShipmentAdapter)
    adapter._api_url = "https://api.cdek.ru/v2/orders"
    adapter._dry_run = False
    adapter._token = "fake-static-token"
    adapter._config = MagicMock()
    adapter._config.cdek_api_token = "fake-static-token"
    adapter._config.cdek_api_url = "https://api.cdek.ru/v2/orders"
    adapter._config.dry_run_external_apis = False
    return adapter


def _make_oauth_adapter():
    from side_effects.adapters.cdek_adapter import CDEKShipmentAdapter

    adapter = CDEKShipmentAdapter.__new__(CDEKShipmentAdapter)
    adapter._api_url = "https://api.cdek.ru/v2/orders"
    adapter._dry_run = False
    adapter._token = ""
    adapter._config = MagicMock()
    adapter._config.cdek_api_token = ""
    adapter._config.cdek_client_id = "client-id"
    adapter._config.cdek_client_secret = "client-secret"
    adapter._config.cdek_api_url = "https://api.cdek.ru/v2/orders"
    adapter._config.dry_run_external_apis = False
    return adapter


# ---------------------------------------------------------------------------
# Mock HTTP response factory
# ---------------------------------------------------------------------------

def _mock_response(status_code=200, json_data=None, content=b"", headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.content = content
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code}", request=MagicMock(), response=resp
        )
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

FAKE_PDF = b"%PDF-1.4 fake waybill content here"
ORDER_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
TASK_UUID = "print-task-uuid-001"


@patch("side_effects.adapters.cdek_adapter.httpx")
def test_waybill_3step_happy_path(mock_httpx):
    """Full 3-step flow: lookup → print → download PDF."""
    from domain.ports import WaybillRequest

    adapter = _make_real_adapter()

    # Step 1: GET /v2/orders?cdek_number=10248510566 → returns order UUID
    lookup_resp = _mock_response(
        json_data={"entity": {"uuid": ORDER_UUID}},
    )
    # Step 2: POST /v2/print/barcodes → returns task UUID
    print_resp = _mock_response(
        json_data={"entity": {"uuid": TASK_UUID}},
    )
    # Step 3: GET /v2/print/barcodes/{task_uuid} → returns PDF
    pdf_resp = _mock_response(
        content=FAKE_PDF,
        headers={"content-type": "application/pdf"},
    )

    mock_httpx.get.side_effect = [lookup_resp, pdf_resp]
    mock_httpx.post.return_value = print_resp

    req = WaybillRequest(carrier_external_id="10248510566", trace_id="trace-001")

    with patch("side_effects.adapters.cdek_adapter.time") as mock_time:
        resp = adapter.get_waybill(req)

    assert resp.pdf_bytes == FAKE_PDF
    assert resp.carrier_external_id == "10248510566"
    assert resp.raw_response["order_uuid"] == ORDER_UUID
    assert resp.raw_response["print_task_uuid"] == TASK_UUID
    assert resp.raw_response["size_bytes"] == len(FAKE_PDF)

    # Verify correct URLs were called
    get_calls = mock_httpx.get.call_args_list
    assert "cdek_number=10248510566" in str(get_calls[0])
    assert f"print/barcodes/{TASK_UUID}" in str(get_calls[1])

    post_calls = mock_httpx.post.call_args_list
    assert "print/barcodes" in str(post_calls[0])


@patch("side_effects.adapters.cdek_adapter.httpx")
def test_waybill_uuid_skips_lookup(mock_httpx):
    """If carrier_external_id is already a UUID, skip the lookup step."""
    from domain.ports import WaybillRequest

    adapter = _make_real_adapter()

    print_resp = _mock_response(
        json_data={"entity": {"uuid": TASK_UUID}},
    )
    pdf_resp = _mock_response(
        content=FAKE_PDF,
        headers={"content-type": "application/pdf"},
    )

    mock_httpx.get.return_value = pdf_resp
    mock_httpx.post.return_value = print_resp

    req = WaybillRequest(carrier_external_id=ORDER_UUID, trace_id="trace-002")

    with patch("side_effects.adapters.cdek_adapter.time") as mock_time:
        resp = adapter.get_waybill(req)

    assert resp.pdf_bytes == FAKE_PDF
    # Only 1 GET call (download), no lookup call
    assert mock_httpx.get.call_count == 1
    assert f"print/barcodes/{TASK_UUID}" in str(mock_httpx.get.call_args)


@patch("side_effects.adapters.cdek_adapter.httpx")
def test_waybill_order_not_found_raises(mock_httpx):
    """If CDEK returns 400 for unknown tracking number, raise RuntimeError."""
    from domain.ports import WaybillRequest

    adapter = _make_real_adapter()

    lookup_resp = _mock_response(status_code=400)

    mock_httpx.get.return_value = lookup_resp

    req = WaybillRequest(carrier_external_id="9999999999", trace_id="trace-003")

    with pytest.raises(RuntimeError, match="order not found"):
        adapter.get_waybill(req)


@patch("side_effects.adapters.cdek_adapter.httpx")
def test_waybill_no_uuid_in_lookup_raises(mock_httpx):
    """If CDEK lookup returns empty entity, raise RuntimeError."""
    from domain.ports import WaybillRequest

    adapter = _make_real_adapter()

    lookup_resp = _mock_response(json_data={"entity": {}})
    mock_httpx.get.return_value = lookup_resp

    req = WaybillRequest(carrier_external_id="10248510566", trace_id="trace-004")

    with pytest.raises(RuntimeError, match="no order UUID"):
        adapter.get_waybill(req)


@patch("side_effects.adapters.cdek_adapter.httpx")
def test_waybill_print_task_no_uuid_raises(mock_httpx):
    """If CDEK print/barcodes returns no task UUID, raise RuntimeError."""
    from domain.ports import WaybillRequest

    adapter = _make_real_adapter()

    lookup_resp = _mock_response(json_data={"entity": {"uuid": ORDER_UUID}})
    print_resp = _mock_response(json_data={"entity": {}})

    mock_httpx.get.return_value = lookup_resp
    mock_httpx.post.return_value = print_resp

    req = WaybillRequest(carrier_external_id="10248510566", trace_id="trace-005")

    with pytest.raises(RuntimeError, match="task UUID"):
        adapter.get_waybill(req)


@patch("side_effects.adapters.cdek_adapter.httpx")
def test_waybill_pdf_timeout_raises(mock_httpx):
    """If PDF never becomes ready, raise RuntimeError after retries."""
    from domain.ports import WaybillRequest

    adapter = _make_real_adapter()

    lookup_resp = _mock_response(json_data={"entity": {"uuid": ORDER_UUID}})
    print_resp = _mock_response(json_data={"entity": {"uuid": TASK_UUID}})
    # Return JSON (not PDF) on every poll attempt
    json_resp = _mock_response(
        json_data={"entity": {"uuid": TASK_UUID, "statuses": [{"code": "PROCESSING"}]}},
        headers={"content-type": "application/json"},
        content=b'{"entity":{}}',
    )

    mock_httpx.get.side_effect = [lookup_resp] + [json_resp] * 10
    mock_httpx.post.return_value = print_resp

    req = WaybillRequest(carrier_external_id="10248510566", trace_id="trace-006")

    with patch("side_effects.adapters.cdek_adapter.time") as mock_time:
        with pytest.raises(RuntimeError, match="did not become READY"):
            adapter.get_waybill(req)


def test_waybill_dry_run_still_works():
    """Regression: dry_run mode must still return stub PDF."""
    from domain.ports import WaybillRequest

    os.environ["DRY_RUN_EXTERNAL_APIS"] = "true"
    from side_effects.adapters.cdek_adapter import CDEKShipmentAdapter

    adapter = CDEKShipmentAdapter.__new__(CDEKShipmentAdapter)
    adapter._api_url = "https://api.cdek.ru/v2/orders"
    adapter._dry_run = True
    adapter._config = MagicMock()
    adapter._config.cdek_api_token = ""
    adapter._config.dry_run_external_apis = True

    req = WaybillRequest(carrier_external_id="DRY-RUN-001", trace_id="trace-dry")
    resp = adapter.get_waybill(req)

    assert resp.pdf_bytes.startswith(b"%PDF")
    assert resp.raw_response.get("dry_run") is True
    os.environ["DRY_RUN_EXTERNAL_APIS"] = "false"


@patch("side_effects.adapters.cdek_adapter.httpx.post")
def test_oauth_token_refresh_when_static_token_missing(mock_post):
    adapter = _make_oauth_adapter()
    mock_post.return_value = _mock_response(
        json_data={"access_token": "oauth-token-001", "expires_in": 3600},
    )

    token = adapter._get_auth_token()

    assert token == "oauth-token-001"
    assert mock_post.call_count == 1
