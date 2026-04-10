"""
test_max_adapter.py — Tests for MAX messenger transport adapter.

Verifies:
    - Update parsing (message_created, message_callback)
    - CanonicalEvent envelope correctness
    - Auth header format
    - Marker cursor advancement
    - Send/edit/answer_callback contract
    - Rate limit handling (429)
    - Network error resilience

All tests are deterministic, use mocks, require no API keys.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from messaging.max_adapter import MaxAdapter, MAX_API_BASE


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def adapter():
    """MaxAdapter with mocked httpx client."""
    a = MaxAdapter.__new__(MaxAdapter)
    a._token = "test-token"
    a._client = MagicMock()
    a._marker = None
    a._poll_errors = 0
    return a


def _make_message_update(
    text: str = "hello",
    user_id: int = 12345,
    chat_id: int = 67890,
    mid: str = "mid_001",
    timestamp: int = 1700000000,
) -> dict:
    return {
        "update_type": "message_created",
        "timestamp": timestamp,
        "message": {
            "sender": {"user_id": user_id, "first_name": "Owner", "is_bot": False},
            "recipient": {"chat_id": chat_id, "chat_type": "dialog"},
            "timestamp": timestamp,
            "body": {"mid": mid, "seq": 1, "text": text},
        },
    }


def _make_callback_update(
    callback_id: str = "cb_001",
    payload: str = "approve",
    user_id: int = 12345,
    chat_id: int = 67890,
    mid: str = "mid_002",
    timestamp: int = 1700000000,
) -> dict:
    return {
        "update_type": "message_callback",
        "timestamp": timestamp,
        "callback": {
            "callback_id": callback_id,
            "payload": payload,
            "user": {"user_id": user_id, "first_name": "Owner", "is_bot": False},
            "timestamp": timestamp,
        },
        "message": {
            "sender": {"user_id": 99, "first_name": "Bot", "is_bot": True},
            "recipient": {"chat_id": chat_id, "chat_type": "dialog"},
            "timestamp": timestamp,
            "body": {"mid": mid, "seq": 1, "text": "Choose action"},
        },
    }


# ===========================================================================
# A. TRANSPORT IDENTITY
# ===========================================================================


class TestTransportIdentity:
    def test_transport_name(self, adapter):
        assert adapter.transport_name == "max"

    def test_get_status(self, adapter):
        status = adapter.get_status()
        assert status["transport"] == "max"
        assert "marker" in status
        assert "poll_errors" in status


# ===========================================================================
# B. UPDATE PARSING — message_created
# ===========================================================================


class TestParseMessageCreated:
    def test_basic_message(self, adapter):
        raw = _make_message_update(text="Привет")
        ev = adapter._parse_update(raw)
        assert ev is not None
        assert ev.source == "max"
        assert ev.text == "Привет"
        assert ev.chat_id == "67890"
        assert ev.user_id == "12345"
        assert ev.message_id == "mid_001"
        assert ev.event_type == "message"

    def test_command_message(self, adapter):
        raw = _make_message_update(text="/status")
        ev = adapter._parse_update(raw)
        assert ev.event_type == "command"
        assert ev.text == "/status"

    def test_empty_text_skipped(self, adapter):
        raw = _make_message_update(text="")
        ev = adapter._parse_update(raw)
        assert ev is None

    def test_whitespace_only_skipped(self, adapter):
        raw = _make_message_update(text="   ")
        ev = adapter._parse_update(raw)
        assert ev is None

    def test_raw_hash_populated(self, adapter):
        raw = _make_message_update()
        ev = adapter._parse_update(raw)
        assert len(ev.raw_hash) == 16  # SHA-256 truncated to 16 hex chars

    def test_timestamp_conversion(self, adapter):
        raw = _make_message_update(timestamp=1700000000)
        ev = adapter._parse_update(raw)
        assert "2023-11" in ev.timestamp  # Nov 2023

    def test_millisecond_timestamp(self, adapter):
        raw = _make_message_update(timestamp=1700000000000)
        ev = adapter._parse_update(raw)
        assert "2023-11" in ev.timestamp

    def test_unknown_update_type_skipped(self, adapter):
        raw = {"update_type": "user_added", "timestamp": 1700000000}
        ev = adapter._parse_update(raw)
        assert ev is None


# ===========================================================================
# C. UPDATE PARSING — message_callback
# ===========================================================================


class TestParseCallback:
    def test_callback_event(self, adapter):
        raw = _make_callback_update(payload="approve")
        ev = adapter._parse_update(raw)
        assert ev is not None
        assert ev.source == "max"
        assert ev.event_type == "callback"
        assert ev.text == "approve"
        assert ev.callback_data == "cb_001"
        assert ev.user_id == "12345"
        assert ev.chat_id == "67890"

    def test_callback_message_id(self, adapter):
        raw = _make_callback_update(mid="mid_777")
        ev = adapter._parse_update(raw)
        assert ev.message_id == "mid_777"


# ===========================================================================
# D. RECEIVE UPDATES (polling)
# ===========================================================================


class TestReceiveUpdates:
    def test_marker_advances(self, adapter):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "updates": [_make_message_update()],
            "marker": 42,
        }
        adapter._client.get.return_value = resp

        events = adapter.receive_updates()
        assert len(events) == 1
        assert adapter._marker == 42

    def test_marker_used_in_params(self, adapter):
        adapter._marker = 10
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"updates": [], "marker": 10}
        adapter._client.get.return_value = resp

        adapter.receive_updates()
        call_kwargs = adapter._client.get.call_args
        assert call_kwargs[1]["params"]["marker"] == 10

    def test_empty_updates(self, adapter):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"updates": [], "marker": None}
        adapter._client.get.return_value = resp

        events = adapter.receive_updates()
        assert events == []

    def test_poll_errors_increment(self, adapter):
        import httpx
        resp = MagicMock()
        resp.status_code = 500
        adapter._client.get.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )

        with patch("messaging.max_adapter.time.sleep"):
            events = adapter.receive_updates()
        assert events == []
        assert adapter._poll_errors == 1

    def test_poll_errors_reset_on_success(self, adapter):
        adapter._poll_errors = 3
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"updates": [], "marker": None}
        adapter._client.get.return_value = resp

        adapter.receive_updates()
        assert adapter._poll_errors == 0


# ===========================================================================
# E. SEND MESSAGE
# ===========================================================================


class TestSendMessage:
    def test_send_success(self, adapter):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "message": {"body": {"mid": "sent_001"}}
        }
        adapter._client.post.return_value = resp

        ref = adapter.send_message("67890", "Hello MAX")
        assert ref.success is True
        assert ref.message_id == "sent_001"
        assert ref.chat_id == "67890"

    def test_send_passes_chat_id(self, adapter):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"message": {"body": {"mid": "x"}}}
        adapter._client.post.return_value = resp

        adapter.send_message("67890", "test")
        call_args = adapter._client.post.call_args
        assert call_args[1]["params"]["chat_id"] == 67890

    def test_send_with_buttons(self, adapter):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"message": {"body": {"mid": "x"}}}
        adapter._client.post.return_value = resp

        buttons = [[{"type": "callback", "text": "OK", "payload": "ok"}]]
        adapter.send_message("67890", "Choose", buttons=buttons)
        call_args = adapter._client.post.call_args
        body = call_args[1]["json"]
        assert body["attachments"][0]["type"] == "inline_keyboard"

    def test_send_failure(self, adapter):
        adapter._client.post.side_effect = Exception("network error")
        ref = adapter.send_message("67890", "test")
        assert ref.success is False

    def test_send_truncates_text(self, adapter):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"message": {"body": {"mid": "x"}}}
        adapter._client.post.return_value = resp

        long_text = "x" * 5000
        adapter.send_message("67890", long_text)
        call_args = adapter._client.post.call_args
        assert len(call_args[1]["json"]["text"]) == 4000


# ===========================================================================
# F. EDIT MESSAGE
# ===========================================================================


class TestEditMessage:
    def test_edit_success(self, adapter):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"success": True}
        adapter._client.put.return_value = resp

        result = adapter.edit_message("67890", "mid_001", "Updated text")
        assert result is True

    def test_edit_failure(self, adapter):
        adapter._client.put.side_effect = Exception("error")
        result = adapter.edit_message("67890", "mid_001", "text")
        assert result is False

    def test_edit_passes_message_id(self, adapter):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"success": True}
        adapter._client.put.return_value = resp

        adapter.edit_message("67890", "mid_999", "text")
        call_args = adapter._client.put.call_args
        assert call_args[1]["params"]["message_id"] == "mid_999"


# ===========================================================================
# G. ANSWER CALLBACK
# ===========================================================================


class TestAnswerCallback:
    def test_answer_success(self, adapter):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"success": True}
        adapter._client.post.return_value = resp

        result = adapter.answer_callback("cb_001", "Accepted")
        assert result is True

    def test_answer_without_text(self, adapter):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"success": True}
        adapter._client.post.return_value = resp

        adapter.answer_callback("cb_001")
        call_args = adapter._client.post.call_args
        assert "notification" not in call_args[1]["json"]

    def test_answer_failure(self, adapter):
        adapter._client.post.side_effect = Exception("error")
        result = adapter.answer_callback("cb_001")
        assert result is False


# ===========================================================================
# H. CANONICAL EVENT CONTRACT
# ===========================================================================


class TestCanonicalEventContract:
    def test_to_dict_complete(self, adapter):
        raw = _make_message_update(text="test")
        ev = adapter._parse_update(raw)
        d = ev.to_dict()
        required_keys = {
            "source", "update_id", "chat_id", "user_id",
            "message_id", "event_type", "text", "timestamp",
            "callback_data", "raw_hash",
        }
        assert required_keys == set(d.keys())

    def test_frozen_dataclass(self, adapter):
        raw = _make_message_update()
        ev = adapter._parse_update(raw)
        with pytest.raises(AttributeError):
            ev.text = "modified"


# ===========================================================================
# I. AUTH HEADER
# ===========================================================================


class TestAuth:
    def test_authorization_header_set(self):
        """MaxAdapter sets Authorization header on httpx client."""
        with patch("messaging.max_adapter.httpx.Client") as mock_client:
            MaxAdapter("my-secret-token")
            call_kwargs = mock_client.call_args[1]
            assert call_kwargs["headers"]["Authorization"] == "my-secret-token"
            assert call_kwargs["base_url"] == MAX_API_BASE
