"""
base.py — Abstract transport interface for messenger backends.

Every messenger backend (Telegram, MAX, etc.) implements MessengerTransport.
Gateway code works exclusively through this interface.

CanonicalEvent is the universal envelope — all platform-specific update
formats are normalized into this structure before entering the inbox.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CanonicalEvent:
    """Platform-agnostic inbound event envelope.

    Every messenger adapter converts its raw update into this form
    before passing it to the gateway loop.
    """
    source: str                          # "telegram" | "max"
    update_id: str                       # platform-native update id (stringified)
    chat_id: str                         # owner conversation id
    user_id: str                         # sender id
    message_id: str                      # platform-native message id
    event_type: str                      # "message" | "callback" | "command"
    text: str                            # message body or callback data label
    timestamp: str                       # ISO-8601 UTC
    callback_data: str = ""              # callback payload (buttons)
    raw_hash: str = ""                   # SHA-256 of raw update for audit

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "update_id": self.update_id,
            "chat_id": self.chat_id,
            "user_id": self.user_id,
            "message_id": self.message_id,
            "event_type": self.event_type,
            "text": self.text,
            "timestamp": self.timestamp,
            "callback_data": self.callback_data,
            "raw_hash": self.raw_hash,
        }


@dataclass(frozen=True)
class MessageRef:
    """Reference to a sent message — used for edit_message later."""
    chat_id: str
    message_id: str
    success: bool


def compute_raw_hash(raw: dict | str) -> str:
    """SHA-256 of the raw update payload for audit trail."""
    if isinstance(raw, dict):
        import json
        raw = json.dumps(raw, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class MessengerTransport(ABC):
    """Abstract transport — one implementation per messenger platform.

    Responsibilities:
        - Convert platform API into CanonicalEvent / MessageRef
        - Handle platform rate limits and retries internally
        - Provide heartbeat-compatible status info

    Non-responsibilities (handled by Gateway):
        - Inbox/outbox file I/O
        - Auth (owner_id check)
        - Redaction
        - Dedup
    """

    @property
    @abstractmethod
    def transport_name(self) -> str:
        """Short identifier: 'telegram', 'max', etc.

        Used as `source` in inbox and `target` filter in outbox.
        """
        ...

    @abstractmethod
    def receive_updates(self) -> list[CanonicalEvent]:
        """Long-poll or fetch pending updates from the platform.

        Returns a list of canonical events. Empty list = no updates.
        Must handle network errors internally (return [] on failure).
        """
        ...

    @abstractmethod
    def send_message(self, chat_id: str, text: str,
                     buttons: list[list[dict]] | None = None) -> MessageRef:
        """Send a text message (optionally with inline buttons).

        buttons format (for future Wave 4):
            [[{"text": "Approve", "callback_data": "approve"}], ...]

        Returns MessageRef with success=True/False.
        """
        ...

    @abstractmethod
    def edit_message(self, chat_id: str, message_id: str, text: str,
                     buttons: list[list[dict]] | None = None) -> bool:
        """Edit an existing message. Returns True on success."""
        ...

    @abstractmethod
    def answer_callback(self, callback_id: str, text: str = "") -> bool:
        """Acknowledge a callback query (button press). Returns True on success."""
        ...

    def get_status(self) -> dict[str, Any]:
        """Optional: transport-specific status for heartbeat."""
        return {"transport": self.transport_name}
