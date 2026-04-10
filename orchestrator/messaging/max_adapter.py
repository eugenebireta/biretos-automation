"""
max_adapter.py — MAX messenger Bot API transport adapter.

Implements MessengerTransport for MAX (https://max.ru).
API docs: https://dev.max.ru/docs-api

Key differences from Telegram:
    - Base URL: https://platform-api.max.ru
    - Auth: Authorization header (not URL token)
    - Long polling: GET /updates with marker cursor (not offset)
    - Send: POST /messages?chat_id=<id> or ?user_id=<id>
    - Edit: PUT /messages?message_id=<id>
    - Callback: POST /answers?callback_id=<id>
    - Update structure: update_type, message.body.text, message.body.mid
    - Rate limit: 30 rps
    - Message text limit: 4000 chars
    - Edit window: 24 hours
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

try:
    from orchestrator.messaging.base import (
        CanonicalEvent, MessageRef, MessengerTransport, compute_raw_hash,
    )
except ModuleNotFoundError:
    from messaging.base import (
        CanonicalEvent, MessageRef, MessengerTransport, compute_raw_hash,
    )

MAX_API_BASE = "https://platform-api.max.ru"
MAX_MAX_TEXT = 4000


class MaxAdapter(MessengerTransport):
    """MAX messenger Bot API implementation of MessengerTransport."""

    def __init__(self, token: str, *, timeout: float = 40):
        self._token = token
        self._client = httpx.Client(
            base_url=MAX_API_BASE,
            headers={"Authorization": token},
            timeout=timeout,
        )
        self._marker: int | None = None
        self._poll_errors = 0

    @property
    def transport_name(self) -> str:
        return "max"

    # ── Polling ────────────────────────────────────────────────────────

    def receive_updates(self) -> list[CanonicalEvent]:
        """Long-poll MAX GET /updates, return canonical events."""
        params: dict[str, Any] = {
            "limit": 100,
            "timeout": 30,
            "types": "message_created,message_callback",
        }
        if self._marker is not None:
            params["marker"] = self._marker

        try:
            resp = self._client.get("/updates", params=params)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "5"))
                time.sleep(retry_after)
                return []

            resp.raise_for_status()
            data = resp.json()

            # Advance marker cursor
            new_marker = data.get("marker")
            if new_marker is not None:
                self._marker = new_marker

            raw_updates = data.get("updates", [])
            events: list[CanonicalEvent] = []
            for raw in raw_updates:
                ev = self._parse_update(raw)
                if ev is not None:
                    events.append(ev)

            self._poll_errors = 0
            return events

        except httpx.HTTPStatusError:
            self._poll_errors += 1
            time.sleep(5)
            return []

        except (httpx.ConnectError, httpx.TimeoutException):
            self._poll_errors += 1
            time.sleep(5)
            return []

    def _parse_update(self, raw: dict) -> CanonicalEvent | None:
        """Convert a MAX Update dict into a CanonicalEvent."""
        update_type = raw.get("update_type", "")
        timestamp_unix = raw.get("timestamp", 0)
        ts_iso = datetime.fromtimestamp(
            timestamp_unix / 1000 if timestamp_unix > 1e12 else timestamp_unix,
            tz=timezone.utc,
        ).isoformat()

        if update_type == "message_callback":
            return self._parse_callback(raw, ts_iso)

        if update_type == "message_created":
            return self._parse_message(raw, ts_iso)

        return None

    def _parse_message(self, raw: dict, ts_iso: str) -> CanonicalEvent | None:
        """Parse message_created update."""
        msg = raw.get("message", {})
        body = msg.get("body", {})
        text = (body.get("text") or "").strip()
        if not text:
            return None

        sender = msg.get("sender", {})
        recipient = msg.get("recipient", {})
        chat_id = str(recipient.get("chat_id") or sender.get("user_id") or "")
        user_id = str(sender.get("user_id", ""))
        message_id = str(body.get("mid", ""))

        event_type = "command" if text.startswith("/") else "message"

        return CanonicalEvent(
            source="max",
            update_id=message_id,
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
            event_type=event_type,
            text=text,
            timestamp=ts_iso,
            raw_hash=compute_raw_hash(raw),
        )

    def _parse_callback(self, raw: dict, ts_iso: str) -> CanonicalEvent | None:
        """Parse message_callback update."""
        callback = raw.get("callback", {})
        callback_id = callback.get("callback_id", "")
        payload = callback.get("payload", "")
        user = callback.get("user", {})
        user_id = str(user.get("user_id", ""))

        msg = raw.get("message", {})
        recipient = msg.get("recipient", {})
        body = msg.get("body", {})
        chat_id = str(recipient.get("chat_id") or "")
        message_id = str(body.get("mid", ""))

        return CanonicalEvent(
            source="max",
            update_id=callback_id,
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
            event_type="callback",
            text=payload,
            callback_data=callback_id,
            timestamp=ts_iso,
            raw_hash=compute_raw_hash(raw),
        )

    # ── Sending ────────────────────────────────────────────────────────

    def send_message(self, chat_id: str, text: str,
                     buttons: list[list[dict]] | None = None) -> MessageRef:
        """Send text via MAX POST /messages."""
        text = text[:MAX_MAX_TEXT]
        body: dict[str, Any] = {"text": text}

        if buttons:
            body["attachments"] = [{
                "type": "inline_keyboard",
                "payload": {"buttons": buttons},
            }]

        try:
            resp = self._client.post(
                "/messages",
                params={"chat_id": int(chat_id)},
                json=body,
            )

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "5"))
                time.sleep(retry_after)
                resp = self._client.post(
                    "/messages",
                    params={"chat_id": int(chat_id)},
                    json=body,
                )

            resp.raise_for_status()
            result = resp.json().get("message", {})
            msg_body = result.get("body", {})
            return MessageRef(
                chat_id=chat_id,
                message_id=str(msg_body.get("mid", "")),
                success=True,
            )
        except Exception:
            return MessageRef(chat_id=chat_id, message_id="", success=False)

    def edit_message(self, chat_id: str, message_id: str, text: str,
                     buttons: list[list[dict]] | None = None) -> bool:
        """Edit existing message via MAX PUT /messages."""
        text = text[:MAX_MAX_TEXT]
        body: dict[str, Any] = {"text": text}

        if buttons:
            body["attachments"] = [{
                "type": "inline_keyboard",
                "payload": {"buttons": buttons},
            }]

        try:
            resp = self._client.put(
                "/messages",
                params={"message_id": message_id},
                json=body,
            )
            resp.raise_for_status()
            return resp.json().get("success", False)
        except Exception:
            return False

    def answer_callback(self, callback_id: str, text: str = "") -> bool:
        """Acknowledge callback via MAX POST /answers."""
        body: dict[str, Any] = {}
        if text:
            body["notification"] = text[:200]

        try:
            resp = self._client.post(
                "/answers",
                params={"callback_id": callback_id},
                json=body,
            )
            resp.raise_for_status()
            return resp.json().get("success", False)
        except Exception:
            return False

    # ── Status ─────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        return {
            "transport": self.transport_name,
            "marker": self._marker,
            "poll_errors": self._poll_errors,
        }
