"""
telegram_adapter.py — Telegram Bot API transport adapter.

Implements MessengerTransport for Telegram. Handles:
    - getUpdates long polling
    - sendMessage / editMessageText
    - answerCallbackQuery
    - Rate limit handling (429 retry)
    - Network error resilience

All Telegram-specific logic lives here. Gateway never calls Telegram API directly.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from orchestrator.messaging.base import (
    CanonicalEvent,
    MessageRef,
    MessengerTransport,
    compute_raw_hash,
)

# Telegram limits
TG_MAX_TEXT = 4096
TG_TRUNCATE_AT = 4000


class TelegramAdapter(MessengerTransport):
    """Telegram Bot API implementation of MessengerTransport."""

    def __init__(self, token: str, *, timeout: float = 40):
        self._token = token
        self._api_base = f"https://api.telegram.org/bot{token}"
        self._client = httpx.Client(timeout=timeout)
        self._last_update_id = 0
        self._poll_errors = 0

    @property
    def transport_name(self) -> str:
        return "telegram"

    # ── Polling ────────────────────────────────────────────────────────

    def receive_updates(self) -> list[CanonicalEvent]:
        """Long-poll Telegram getUpdates, return canonical events."""
        params = {
            "offset": self._last_update_id + 1,
            "limit": 20,
            "timeout": 30,
            "allowed_updates": json.dumps(["message", "callback_query"]),
        }
        try:
            resp = self._client.get(
                f"{self._api_base}/getUpdates", params=params
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                return []

            raw_updates = data.get("result", [])
            events: list[CanonicalEvent] = []
            for raw in raw_updates:
                uid = raw.get("update_id", 0)
                if uid > self._last_update_id:
                    self._last_update_id = uid
                ev = self._parse_update(raw)
                if ev is not None:
                    events.append(ev)

            self._poll_errors = 0
            return events

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                time.sleep(10)
            elif e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", "30"))
                time.sleep(retry_after)
            else:
                self._poll_errors += 1
                time.sleep(5)
            return []

        except (httpx.ConnectError, httpx.TimeoutException):
            self._poll_errors += 1
            time.sleep(5)
            return []

    def _parse_update(self, raw: dict) -> CanonicalEvent | None:
        """Convert a Telegram Update dict into a CanonicalEvent."""
        # Callback query (buttons) — Wave 4, but parse now
        cb = raw.get("callback_query")
        if cb:
            chat = cb.get("message", {}).get("chat", {})
            return CanonicalEvent(
                source="telegram",
                update_id=str(raw.get("update_id", "")),
                chat_id=str(chat.get("id", "")),
                user_id=str(cb.get("from", {}).get("id", "")),
                message_id=str(cb.get("message", {}).get("message_id", "")),
                event_type="callback",
                text=cb.get("data", ""),
                callback_data=cb.get("data", ""),
                timestamp=datetime.now(timezone.utc).isoformat(),
                raw_hash=compute_raw_hash(raw),
            )

        # Regular message
        msg = raw.get("message")
        if not msg:
            return None

        chat = msg.get("chat", {})
        text = (msg.get("text") or "").strip()
        if not text:
            return None

        # Detect command vs regular message
        event_type = "command" if text.startswith("/") else "message"

        return CanonicalEvent(
            source="telegram",
            update_id=str(raw.get("update_id", "")),
            chat_id=str(chat.get("id", "")),
            user_id=str(msg.get("from", {}).get("id", "")),
            message_id=str(msg.get("message_id", "")),
            event_type=event_type,
            text=text,
            timestamp=datetime.now(timezone.utc).isoformat(),
            raw_hash=compute_raw_hash(raw),
        )

    # ── Sending ────────────────────────────────────────────────────────

    def send_message(self, chat_id: str, text: str,
                     buttons: list[list[dict]] | None = None) -> MessageRef:
        """Send text to chat via Telegram sendMessage."""
        text = text[:TG_MAX_TEXT]
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}

        if buttons:
            payload["reply_markup"] = json.dumps({
                "inline_keyboard": buttons,
            })

        try:
            resp = self._client.post(
                f"{self._api_base}/sendMessage", json=payload
            )
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "30"))
                time.sleep(retry_after)
                resp = self._client.post(
                    f"{self._api_base}/sendMessage", json=payload
                )
            resp.raise_for_status()
            result = resp.json().get("result", {})
            return MessageRef(
                chat_id=chat_id,
                message_id=str(result.get("message_id", "")),
                success=True,
            )
        except Exception:
            return MessageRef(chat_id=chat_id, message_id="", success=False)

    def edit_message(self, chat_id: str, message_id: str, text: str,
                     buttons: list[list[dict]] | None = None) -> bool:
        """Edit existing message via Telegram editMessageText."""
        text = text[:TG_MAX_TEXT]
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": int(message_id),
            "text": text,
        }
        if buttons:
            payload["reply_markup"] = json.dumps({
                "inline_keyboard": buttons,
            })

        try:
            resp = self._client.post(
                f"{self._api_base}/editMessageText", json=payload
            )
            resp.raise_for_status()
            return True
        except Exception:
            return False

    def answer_callback(self, callback_id: str, text: str = "") -> bool:
        """Acknowledge callback query via Telegram answerCallbackQuery."""
        payload: dict[str, Any] = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text[:200]

        try:
            resp = self._client.post(
                f"{self._api_base}/answerCallbackQuery", json=payload
            )
            resp.raise_for_status()
            return True
        except Exception:
            return False

    # ── Status ─────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        return {
            "transport": self.transport_name,
            "last_update_id": self._last_update_id,
            "poll_errors": self._poll_errors,
        }
