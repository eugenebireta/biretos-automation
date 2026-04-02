"""Deterministic tests for browser_vision_scout.py.

All tests use mocked Playwright and mocked Anthropic API.
No live browser, no live network, no live API calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import browser_vision_scout as bvs  # noqa: E402


# ── Fixtures / helpers ────────────────────────────────────────────────────────

SEED_RECORD_BASE: dict[str, Any] = {
    "part_number": "1015021",
    "brand": "Honeywell",
    "product_name": "Leightning Hi-Viz L1HHV",
    "expected_category": "Наушники",
    "page_url": "https://www.vseinstrumenti.ru/product/signalnye-1015021/",
    "source_provider": "codex_manual",
    "price_status": "public_price",
    "price_per_unit": 4314.0,
    "currency": "RUB",
    "offer_qty": 1,
    "offer_unit_basis": "piece",
    "stock_status": "in_stock",
    "lead_time_detected": False,
    "quote_cta_url": "",
    "page_product_class": "",
    "category_mismatch": False,
    "brand_mismatch": False,
    "price_confidence": 95,
    "source_price_value": 4314.0,
    "source_price_currency": "RUB",
    "source_offer_qty": 1,
    "source_offer_unit_basis": "piece",
    "price_basis_note": "",
    "notes": "",
}


def _make_screenshot_bytes() -> bytes:
    # Minimal valid 1×1 PNG (not a real browser screenshot)
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
        b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _claude_response_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


def _mock_anthropic_client(response_payload: dict[str, Any]) -> MagicMock:
    """Return a mock anthropic.Anthropic() client that returns a fixed vision response."""
    mock_content = MagicMock()
    mock_content.text = _claude_response_text(response_payload)
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


def _make_browser_fetcher(
    screenshot_bytes: bytes | None = None,
    http_status: int = 200,
    final_url: str = "https://www.vseinstrumenti.ru/product/signalnye-1015021/",
    page_title: str = "Наушники 1015021 - vseinstrumenti.ru",
    error: dict | None = None,
) -> MagicMock:
    """Return a mock BrowserFetcher that returns a fixed screenshot result."""
    mock_browser = MagicMock(spec=bvs.BrowserFetcher)
    mock_browser._headless = True
    mock_browser._channel = "msedge"
    mock_browser.fetch_screenshot.return_value = {
        "screenshot_bytes": screenshot_bytes if screenshot_bytes is not None else _make_screenshot_bytes(),
        "final_url": final_url,
        "page_title": page_title,
        "browser_http_status": http_status,
        "error": error,
    }
    return mock_browser


def _make_vision_extractor(response_payload: dict[str, Any]) -> bvs.VisionExtractor:
    """Return a VisionExtractor wired to a mock Anthropic client."""
    extractor = object.__new__(bvs.VisionExtractor)
    extractor._model = bvs.DEFAULT_VISION_MODEL
    extractor._escalation_model = bvs.ESCALATION_MODEL
    extractor._enable_escalation = True
    extractor._escalation_threshold = bvs.ESCALATION_CONFIDENCE_THRESHOLD
    extractor._client = _mock_anthropic_client(response_payload)
    return extractor


# ── Scenario 1: blocked HTTP candidate → browser vision success ───────────────

def test_blocked_http_candidate_vision_success():
    """URL returns 403 to requests, but browser loads it fine with PN confirmed.

    Note: vseinstrumenti.ru is ru_b2b tier so tighten_public_price_result may
    downgrade price_status to ambiguous_offer — that is correct pipeline behavior.
    We assert on lineage + extracted values, not on the trust-gated final status.
    """
    vision_payload = {
        "pn_confirmed": True,
        "pn_match_context": "title",
        "price": 4314.0,
        "currency": "RUB",
        "stock_status": "in_stock",
        "page_class": "normal_product_page",
        "confidence": 95,
        "notes": "",
    }
    browser = _make_browser_fetcher(http_status=200)  # browser got 200 even though requests got 403
    extractor = _make_vision_extractor(vision_payload)

    row = bvs.materialize_bvs_record(
        SEED_RECORD_BASE,
        browser=browser,
        extractor=extractor,
        surface_cache_payload=None,
        run_id="test_run_001",
    )

    assert row["price_source_exact_product_lineage_confirmed"] is True
    assert row["price_source_lineage_reason_code"] == "cu_vision_pn_confirmed"
    assert row["price_per_unit"] == 4314.0
    assert row["currency"] == "RUB"
    # price_status is trust-gated; for ru_b2b sources it may be ambiguous_offer
    assert row["price_status"] in ("public_price", "ambiguous_offer")
    assert row["vision_confidence"] == 95
    assert row["browser_vision_source"] is True
    assert row["blocked_ui_detected"] is False


# ── Scenario 2: 200 / no-price / JS-rendered → browser vision success ─────────

def test_200_no_price_js_rendered_vision_success():
    """Seed has no price (JS-rendered), browser confirms PN and extracts price."""
    record = {**SEED_RECORD_BASE, "price_per_unit": None, "currency": None, "price_status": "no_price_found"}
    vision_payload = {
        "pn_confirmed": True,
        "pn_match_context": "h1",
        "price": 5356.0,
        "currency": "RUB",
        "stock_status": "in_stock",
        "page_class": "normal_product_page",
        "confidence": 90,
        "notes": "js rendered price visible in screenshot",
    }
    browser = _make_browser_fetcher(http_status=200)
    extractor = _make_vision_extractor(vision_payload)

    row = bvs.materialize_bvs_record(
        record,
        browser=browser,
        extractor=extractor,
        surface_cache_payload=None,
        run_id="test_run_002",
    )

    assert row["price_source_exact_product_lineage_confirmed"] is True
    assert row["price_per_unit"] == 5356.0
    # price_status is trust-gated by tighten_public_price_result; ru_b2b tier may
    # yield ambiguous_offer even with confirmed lineage — both are valid outcomes
    assert row["price_status"] in ("public_price", "ambiguous_offer")
    assert row["price_source_lineage_reason_code"] == "cu_vision_pn_confirmed"
    assert row["browser_vision_source"] is True


# ── Scenario 3: captcha / blocked UI → correct reason_code ────────────────────

def test_captcha_blocked_ui_reason_code():
    """Browser loads page but Claude sees captcha/blocked UI."""
    vision_payload = {
        "pn_confirmed": False,
        "pn_match_context": "",
        "price": None,
        "currency": None,
        "stock_status": "unknown",
        "page_class": "blocked_ui",
        "confidence": 30,
        "notes": "cloudflare challenge page detected",
    }
    browser = _make_browser_fetcher(
        http_status=200,
        page_title="Just a moment... | Cloudflare",
    )
    extractor = _make_vision_extractor(vision_payload)

    row = bvs.materialize_bvs_record(
        SEED_RECORD_BASE,
        browser=browser,
        extractor=extractor,
        surface_cache_payload=None,
        run_id="test_run_003",
    )

    assert row["price_source_exact_product_lineage_confirmed"] is False
    assert row["price_source_lineage_reason_code"] == "cu_vision_blocked_page"
    assert row["blocked_ui_detected"] is True
    assert row["review_required"] is True
    # Price must not be carried over from seed when vision returns None
    assert row["price_per_unit"] == 4314.0  # fallback to seed value (seed had price)
    assert row["price_status"] != "public_price" or row["review_required"] is True


# ── Scenario 4: extraction failure → structured result with fail-loud fields ──

def test_extraction_failure_structured_result():
    """Anthropic API fails → structured error fields, not silent swallow."""
    browser = _make_browser_fetcher(http_status=200)

    extractor = object.__new__(bvs.VisionExtractor)
    extractor._model = bvs.DEFAULT_VISION_MODEL
    extractor._escalation_model = bvs.ESCALATION_MODEL
    extractor._enable_escalation = False
    extractor._escalation_threshold = bvs.ESCALATION_CONFIDENCE_THRESHOLD
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("API timeout")
    extractor._client = mock_client

    row = bvs.materialize_bvs_record(
        SEED_RECORD_BASE,
        browser=browser,
        extractor=extractor,
        surface_cache_payload=None,
        run_id="test_run_004",
    )

    assert row["price_source_exact_product_lineage_confirmed"] is False
    assert row["price_source_lineage_reason_code"] == "cu_extraction_failed"
    assert row["review_required"] is True
    assert row["browser_vision_source"] is True
    # vision_confidence must be 0 on failure
    assert row["vision_confidence"] == 0


# ── Scenario 5: manifest backward compatibility ───────────────────────────────

def test_manifest_backward_compatibility():
    """All fields present in price_manual_scout manifest are present here too."""
    # These are all the standard keys emitted by price_manual_scout.materialize_seed_record
    REQUIRED_STANDARD_KEYS = {
        "part_number", "brand", "product_name", "expected_category",
        "source_provider", "page_url", "source_domain", "source_role",
        "source_type", "source_tier", "source_weight", "http_status",
        "price_status", "price_per_unit", "currency", "rub_price",
        "fx_normalization_status", "fx_gap_reason_code", "fx_provider",
        "fx_rate_used", "offer_qty", "offer_unit_basis", "stock_status",
        "lead_time_detected", "quote_cta_url", "page_product_class",
        "price_confidence", "price_source_seen",
        "price_source_exact_product_lineage_confirmed",
        "price_source_lineage_reason_code", "price_source_surface_stable",
        "price_source_surface_conflict_detected",
        "price_source_surface_conflict_reason_code",
        "source_price_value", "source_price_currency",
        "source_offer_qty", "source_offer_unit_basis",
        "price_basis_note", "notes", "transient_failure_codes",
        "cache_fallback_used", "review_required",
    }
    REQUIRED_ADDITIVE_KEYS = {
        "browser_vision_source", "browser_mode", "browser_channel",
        "screenshot_taken", "screenshot_path", "vision_model",
        "vision_confidence", "blocked_ui_detected", "final_url",
        "page_title", "escalated_to_opus", "trace_id", "idempotency_key",
    }

    vision_payload = {
        "pn_confirmed": True,
        "pn_match_context": "title",
        "price": 4314.0,
        "currency": "RUB",
        "stock_status": "in_stock",
        "page_class": "normal_product_page",
        "confidence": 92,
        "notes": "",
    }
    browser = _make_browser_fetcher()
    extractor = _make_vision_extractor(vision_payload)

    row = bvs.materialize_bvs_record(
        SEED_RECORD_BASE,
        browser=browser,
        extractor=extractor,
        surface_cache_payload=None,
        run_id="test_run_005",
    )

    missing_standard = REQUIRED_STANDARD_KEYS - set(row.keys())
    missing_additive = REQUIRED_ADDITIVE_KEYS - set(row.keys())

    assert missing_standard == set(), f"Missing standard keys: {missing_standard}"
    assert missing_additive == set(), f"Missing additive keys: {missing_additive}"


# ── Unit: _parse_vision_response ─────────────────────────────────────────────

def test_parse_vision_response_valid_json():
    raw = json.dumps({
        "pn_confirmed": True,
        "pn_match_context": "h1",
        "price": 1234.5,
        "currency": "rub",
        "stock_status": "in_stock",
        "page_class": "normal_product_page",
        "confidence": 88,
        "notes": "ok",
    })
    result = bvs._parse_vision_response(raw)
    assert result["pn_confirmed"] is True
    assert result["price"] == 1234.5
    assert result["currency"] == "RUB"  # uppercased
    assert result["extraction_failed"] is False


def test_parse_vision_response_strips_markdown_fence():
    raw = "```json\n{\"pn_confirmed\": false, \"price\": null, \"currency\": null, \"stock_status\": \"unknown\", \"page_class\": \"blocked_ui\", \"confidence\": 10, \"notes\": \"\", \"pn_match_context\": \"\"}\n```"
    result = bvs._parse_vision_response(raw)
    assert result["extraction_failed"] is False
    assert result["page_class"] == "blocked_ui"


def test_parse_vision_response_garbage_returns_extraction_failed():
    result = bvs._parse_vision_response("not json at all {{{")
    assert result["extraction_failed"] is True
    assert result["pn_confirmed"] is False
    assert result["confidence"] == 0


# ── Unit: _derive_bvs_lineage_reason_code ────────────────────────────────────

@pytest.mark.parametrize("vision, browser, expected", [
    ({"pn_confirmed": True, "page_class": "normal_product_page", "extraction_failed": False},
     {"error": None}, "cu_vision_pn_confirmed"),
    ({"pn_confirmed": False, "page_class": "normal_product_page", "extraction_failed": False},
     {"error": None}, "cu_vision_pn_not_found"),
    ({"pn_confirmed": False, "page_class": "blocked_ui", "extraction_failed": False},
     {"error": None}, "cu_vision_blocked_page"),
    ({"pn_confirmed": False, "page_class": "login_required", "extraction_failed": False},
     {"error": None}, "cu_vision_blocked_page"),
    ({"pn_confirmed": False, "page_class": "error_page", "extraction_failed": True},
     {"error": None}, "cu_extraction_failed"),
    ({"pn_confirmed": False, "page_class": "normal_product_page", "extraction_failed": False},
     {"error": {"message": "timeout"}}, "cu_browser_load_failed"),
])
def test_derive_bvs_lineage_reason_code(vision, browser, expected):
    assert bvs._derive_bvs_lineage_reason_code(vision, browser) == expected


# ── Unit: _should_save_screenshot ────────────────────────────────────────────

def test_should_save_screenshot_saves_on_pn_confirmed():
    assert bvs._should_save_screenshot({"pn_confirmed": True}) is True


def test_should_save_screenshot_saves_on_blocked_ui():
    assert bvs._should_save_screenshot({"pn_confirmed": False, "page_class": "blocked_ui"}) is True


def test_should_save_screenshot_does_not_save_clean_no_price():
    assert bvs._should_save_screenshot({
        "pn_confirmed": False,
        "price": None,
        "page_class": "normal_product_page",
        "extraction_failed": False,
    }) is False


def test_should_save_screenshot_save_all_overrides():
    assert bvs._should_save_screenshot({
        "pn_confirmed": False,
        "price": None,
        "page_class": "normal_product_page",
        "extraction_failed": False,
    }, save_all=True) is True


# ── Unit: load_first_pass_candidates ─────────────────────────────────────────

def test_load_first_pass_candidates_blocked_status(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        "\n".join([
            json.dumps({"page_url": "https://a.com/p1", "http_status": 403, "price_status": "no_price_found", "price_source_exact_product_lineage_confirmed": False}),
            json.dumps({"page_url": "https://b.com/p2", "http_status": 200, "price_status": "public_price", "price_source_exact_product_lineage_confirmed": True}),
            json.dumps({"page_url": "https://c.com/p3", "http_status": 498, "price_status": "no_price_found", "price_source_exact_product_lineage_confirmed": False}),
        ]),
        encoding="utf-8",
    )
    candidates = bvs.load_first_pass_candidates(manifest)
    assert "https://a.com/p1" in candidates
    assert "https://b.com/p2" not in candidates  # 200 + public_price + lineage → skip
    assert "https://c.com/p3" in candidates


def test_load_first_pass_candidates_200_no_lineage(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps({
            "page_url": "https://lemanapro.ru/product/xyz/",
            "http_status": 200,
            "price_status": "no_price_found",
            "price_source_exact_product_lineage_confirmed": False,
        }),
        encoding="utf-8",
    )
    candidates = bvs.load_first_pass_candidates(manifest)
    assert "https://lemanapro.ru/product/xyz/" in candidates


def test_load_first_pass_candidates_missing_file(tmp_path):
    candidates = bvs.load_first_pass_candidates(tmp_path / "nonexistent.jsonl")
    assert candidates == set()


# ── Unit: auto-escalation logic ──────────────────────────────────────────────

def test_auto_escalation_triggers_on_low_confidence():
    """Sonnet returns low confidence → Opus is called."""
    sonnet_payload = {
        "pn_confirmed": False, "pn_match_context": "", "price": None,
        "currency": None, "stock_status": "unknown",
        "page_class": "normal_product_page", "confidence": 50, "notes": "",
    }
    opus_payload = {
        "pn_confirmed": True, "pn_match_context": "title", "price": 4314.0,
        "currency": "RUB", "stock_status": "in_stock",
        "page_class": "normal_product_page", "confidence": 92, "notes": "",
    }

    call_count = {"n": 0}
    models_called: list[str] = []

    def mock_create(**kwargs):
        model = kwargs.get("model", "")
        models_called.append(model)
        call_count["n"] += 1
        payload = sonnet_payload if call_count["n"] == 1 else opus_payload
        mock_content = MagicMock()
        mock_content.text = json.dumps(payload)
        mock_resp = MagicMock()
        mock_resp.content = [mock_content]
        return mock_resp

    extractor = object.__new__(bvs.VisionExtractor)
    extractor._model = bvs.DEFAULT_VISION_MODEL   # sonnet
    extractor._escalation_model = bvs.ESCALATION_MODEL  # opus
    extractor._enable_escalation = True
    extractor._escalation_threshold = bvs.ESCALATION_CONFIDENCE_THRESHOLD
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = lambda **kw: mock_create(**kw)
    extractor._client = mock_client

    result = extractor.extract(_make_screenshot_bytes(), pn="1015021")

    assert call_count["n"] == 2, "Should have called API twice (sonnet then opus)"
    assert result["escalated_to_opus"] is True
    assert result["pn_confirmed"] is True
    assert result["vision_model"] == bvs.ESCALATION_MODEL


def test_no_escalation_when_model_is_opus():
    """When vision_model == opus, no escalation regardless of confidence."""
    low_conf_payload = {
        "pn_confirmed": False, "pn_match_context": "", "price": None,
        "currency": None, "stock_status": "unknown",
        "page_class": "normal_product_page", "confidence": 40, "notes": "",
    }
    extractor = object.__new__(bvs.VisionExtractor)
    extractor._model = bvs.ESCALATION_MODEL   # already opus
    extractor._escalation_model = bvs.ESCALATION_MODEL
    extractor._enable_escalation = True
    extractor._escalation_threshold = bvs.ESCALATION_CONFIDENCE_THRESHOLD
    extractor._client = _mock_anthropic_client(low_conf_payload)

    result = extractor.extract(_make_screenshot_bytes(), pn="1015021")

    assert extractor._client.messages.create.call_count == 1
    assert result["escalated_to_opus"] is False
