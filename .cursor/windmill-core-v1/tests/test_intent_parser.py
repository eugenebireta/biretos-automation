"""
Tests for domain/intent_parser.py — Phase 7.9.
Pure unit tests: no DB, no network, deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

from domain.nlu_models import NLUConfig
from domain.intent_parser import parse_intent


def _cfg(**kwargs) -> NLUConfig:
    defaults = dict(
        nlu_enabled=True,
        degradation_level=0,
        confidence_threshold=0.80,
        shadow_mode=False,
        model_version="regex-v1",
        prompt_version="v1.0",
        max_input_bytes=1024,
    )
    defaults.update(kwargs)
    return NLUConfig(**defaults)


# ---------------------------------------------------------------------------
# button_only
# ---------------------------------------------------------------------------

def test_button_only_when_disabled():
    cfg = _cfg(nlu_enabled=False)
    result = parse_intent("проверить платёж INV-123", cfg)
    assert result.status == "button_only"
    assert result.parsed is None


def test_button_only_when_degradation_2():
    cfg = _cfg(nlu_enabled=True, degradation_level=2)
    result = parse_intent("проверить платёж INV-123", cfg)
    assert result.status == "button_only"


# ---------------------------------------------------------------------------
# check_payment intent
# ---------------------------------------------------------------------------

def test_check_payment_russian():
    cfg = _cfg()
    result = parse_intent("проверить платёж INV-123", cfg)
    assert result.status == "ok"
    assert result.parsed is not None
    assert result.parsed.intent_type == "check_payment"


def test_check_payment_status_variant():
    cfg = _cfg()
    result = parse_intent("статус оплаты INV-ABC", cfg)
    assert result.status == "ok"
    assert result.parsed.intent_type == "check_payment"


def test_check_payment_entity_extracted():
    cfg = _cfg()
    result = parse_intent("проверить платёж INV-99887", cfg)
    assert result.parsed is not None
    assert result.parsed.entities.get("invoice_id") == "99887"


def test_check_payment_entity_missing():
    cfg = _cfg()
    result = parse_intent("статус оплаты", cfg)
    assert result.status == "ok"
    assert result.parsed.entities.get("invoice_id") is None


# ---------------------------------------------------------------------------
# get_tracking intent
# ---------------------------------------------------------------------------

def test_get_tracking_russian():
    cfg = _cfg()
    result = parse_intent("отследить посылку", cfg)
    assert result.status == "ok"
    assert result.parsed.intent_type == "get_tracking"


def test_get_tracking_english():
    cfg = _cfg()
    result = parse_intent("tracking status", cfg)
    assert result.status == "ok"
    assert result.parsed.intent_type == "get_tracking"


def test_get_tracking_uuid_extracted():
    cfg = _cfg()
    text = "где посылка 550e8400-e29b-41d4-a716-446655440000"
    result = parse_intent(text, cfg)
    assert result.parsed is not None
    assert result.parsed.entities.get("carrier_external_id") == "550e8400-e29b-41d4-a716-446655440000"


# ---------------------------------------------------------------------------
# get_waybill intent
# ---------------------------------------------------------------------------

def test_get_waybill_russian():
    cfg = _cfg()
    result = parse_intent("нужна накладная CDEK-XYZ1", cfg)
    assert result.status == "ok"
    assert result.parsed.intent_type == "get_waybill"


def test_get_waybill_english():
    cfg = _cfg()
    result = parse_intent("get waybill", cfg)
    assert result.status == "ok"
    assert result.parsed.intent_type == "get_waybill"


# ---------------------------------------------------------------------------
# send_invoice intent
# ---------------------------------------------------------------------------

def test_send_invoice_russian():
    cfg = _cfg()
    result = parse_intent("выставить счёт клиенту", cfg)
    assert result.status == "ok"
    assert result.parsed.intent_type == "send_invoice"


def test_send_invoice_english():
    cfg = _cfg()
    result = parse_intent("send invoice", cfg)
    assert result.status == "ok"
    assert result.parsed.intent_type == "send_invoice"


def test_send_invoice_extracts_order_id_from_phrase():
    cfg = _cfg()
    result = parse_intent("send invoice ORDER-12345", cfg)
    assert result.status == "ok"
    assert result.parsed is not None
    assert result.parsed.intent_type == "send_invoice"
    assert result.parsed.entities["insales_order_id"] == "ORDER-12345"


def test_send_invoice_extracts_order_id_after_keyword():
    cfg = _cfg()
    result = parse_intent("send invoice order ORDER-777", cfg)
    assert result.status == "ok"
    assert result.parsed is not None
    assert result.parsed.entities["insales_order_id"] == "ORDER-777"


# ---------------------------------------------------------------------------
# fallback
# ---------------------------------------------------------------------------

def test_fallback_on_unknown_text():
    cfg = _cfg()
    result = parse_intent("привет как дела", cfg)
    assert result.status == "fallback"
    assert result.parsed is None


# ---------------------------------------------------------------------------
# shadow mode
# ---------------------------------------------------------------------------

def test_shadow_mode_does_not_return_ok():
    cfg = _cfg(shadow_mode=True)
    result = parse_intent("отследить посылку", cfg)
    assert result.status == "shadow"
    assert result.parsed is not None


# ---------------------------------------------------------------------------
# model_version / prompt_version propagation
# ---------------------------------------------------------------------------

def test_version_propagation():
    cfg = _cfg(model_version="regex-v2", prompt_version="v2.0")
    result = parse_intent("tracking status", cfg)
    assert result.parsed is not None
    assert result.parsed.model_version == "regex-v2"
    assert result.parsed.prompt_version == "v2.0"


# ---------------------------------------------------------------------------
# parse_duration_ms
# ---------------------------------------------------------------------------

def test_parse_duration_non_negative():
    cfg = _cfg()
    result = parse_intent("tracking status", cfg)
    assert result.parse_duration_ms >= 0


# ---------------------------------------------------------------------------
# raw_text_hash
# ---------------------------------------------------------------------------

def test_raw_text_hash_is_12_chars():
    cfg = _cfg()
    result = parse_intent("статус доставки", cfg)
    assert result.parsed is not None
    assert len(result.parsed.raw_text_hash) == 12
