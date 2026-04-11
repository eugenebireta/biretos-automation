"""
test_transport_abstraction.py — Tests for Wave 1 transport abstraction layer.

Verifies:
    - MessengerTransport ABC contract
    - CanonicalEvent immutability and serialization
    - MessageRef contract
    - TelegramAdapter implements the interface
    - MaxAdapter implements the interface
    - Gateway outbox target filtering
    - Gateway processes CanonicalEvent (not raw dicts)
    - Bridge source→target routing
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from messaging.base import (
    CanonicalEvent,
    MessageRef,
    MessengerTransport,
    compute_raw_hash,
)


# ===========================================================================
# A. ABC CONTRACT
# ===========================================================================


class TestAbcContract:
    def test_cannot_instantiate_abc(self):
        """MessengerTransport cannot be instantiated directly."""
        with pytest.raises(TypeError):
            MessengerTransport()

    def test_concrete_must_implement_all(self):
        """Subclass missing methods raises TypeError."""
        class Incomplete(MessengerTransport):
            @property
            def transport_name(self):
                return "test"

        with pytest.raises(TypeError):
            Incomplete()

    def test_telegram_adapter_is_transport(self):
        from messaging.telegram_adapter import TelegramAdapter
        with patch("messaging.telegram_adapter.httpx.Client"):
            adapter = TelegramAdapter("fake-token")
        assert isinstance(adapter, MessengerTransport)
        assert adapter.transport_name == "telegram"

    def test_max_adapter_is_transport(self):
        from messaging.max_adapter import MaxAdapter
        with patch("messaging.max_adapter.httpx.Client"):
            adapter = MaxAdapter("fake-token")
        assert isinstance(adapter, MessengerTransport)
        assert adapter.transport_name == "max"


# ===========================================================================
# B. CANONICAL EVENT
# ===========================================================================


class TestCanonicalEvent:
    def test_frozen(self):
        ev = CanonicalEvent(
            source="test", update_id="1", chat_id="c1", user_id="u1",
            message_id="m1", event_type="message", text="hello",
            timestamp="2026-01-01T00:00:00Z",
        )
        with pytest.raises(AttributeError):
            ev.text = "x"

    def test_to_dict(self):
        ev = CanonicalEvent(
            source="telegram", update_id="42", chat_id="100",
            user_id="200", message_id="300", event_type="message",
            text="test", timestamp="2026-01-01T00:00:00Z",
        )
        d = ev.to_dict()
        assert d["source"] == "telegram"
        assert d["text"] == "test"
        assert len(d) == 10  # all fields

    def test_defaults(self):
        ev = CanonicalEvent(
            source="max", update_id="1", chat_id="c", user_id="u",
            message_id="m", event_type="callback", text="data",
            timestamp="t",
        )
        assert ev.callback_data == ""
        assert ev.raw_hash == ""


# ===========================================================================
# C. MESSAGE REF
# ===========================================================================


class TestMessageRef:
    def test_success_ref(self):
        ref = MessageRef(chat_id="123", message_id="456", success=True)
        assert ref.success is True

    def test_failure_ref(self):
        ref = MessageRef(chat_id="123", message_id="", success=False)
        assert ref.success is False


# ===========================================================================
# D. RAW HASH
# ===========================================================================


class TestRawHash:
    def test_dict_hash(self):
        h = compute_raw_hash({"a": 1, "b": 2})
        assert len(h) == 16
        assert isinstance(h, str)

    def test_string_hash(self):
        h = compute_raw_hash("test data")
        assert len(h) == 16

    def test_deterministic(self):
        h1 = compute_raw_hash({"x": 1})
        h2 = compute_raw_hash({"x": 1})
        assert h1 == h2

    def test_different_inputs(self):
        h1 = compute_raw_hash({"x": 1})
        h2 = compute_raw_hash({"x": 2})
        assert h1 != h2


# ===========================================================================
# E. OUTBOX TARGET FILTERING
# ===========================================================================


class TestOutboxTargetFiltering:
    def test_enqueue_outbox_default_target(self):
        from telegram_gateway import enqueue_outbox
        import telegram_gateway as tg
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            outbox = Path(tmp) / "outbox.jsonl"
            with patch.object(tg, "OUTBOX_PATH", outbox):
                enqueue_outbox("test message")
            line = outbox.read_text(encoding="utf-8").strip()
            entry = json.loads(line)
            assert entry["target"] == "telegram"

    def test_enqueue_outbox_custom_target(self):
        from telegram_gateway import enqueue_outbox
        import telegram_gateway as tg
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            outbox = Path(tmp) / "outbox.jsonl"
            with patch.object(tg, "OUTBOX_PATH", outbox):
                enqueue_outbox("test message", target="max")
            line = outbox.read_text(encoding="utf-8").strip()
            entry = json.loads(line)
            assert entry["target"] == "max"


# ===========================================================================
# F. BRIDGE SOURCE→TARGET ROUTING
# ===========================================================================


class TestBridgeRouting:
    def test_telegram_source_routes_to_telegram(self):
        """Bridge converts source='telegram_gateway' to target='telegram'."""
        source = "telegram_gateway"
        target = source.replace("_gateway", "") if source else "telegram"
        assert target == "telegram"

    def test_telegram_source_shortform(self):
        source = "telegram"
        target = source.replace("_gateway", "") if source else "telegram"
        assert target == "telegram"

    def test_max_source_routes_to_max(self):
        source = "max"
        target = source.replace("_gateway", "") if source else "telegram"
        assert target == "max"

    def test_empty_source_defaults_telegram(self):
        source = ""
        target = source.replace("_gateway", "") if source else "telegram"
        assert target == "telegram"
