"""
buttons.py — Transport-agnostic inline keyboard builder (Wave 4).

Builds button layouts compatible with both Telegram and MAX APIs.
Both platforms use the same wire format for inline keyboards:
    [[{"text": "Label", "callback_data": "payload"}], ...]

This module provides a clean builder API so callers never construct
raw dicts manually.

Usage:
    from orchestrator.messaging.buttons import InlineKeyboard

    kb = (InlineKeyboard()
          .row()
          .button("Approve", "approve")
          .button("Reject", "reject")
          .row()
          .button("Details", "details")
          .build())

    transport.send_message(chat_id, "Choose action:", buttons=kb)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InlineKeyboard:
    """Builder for transport-agnostic inline button layouts.

    Produces list[list[dict]] compatible with both Telegram and MAX.
    Each row is a list of buttons; each button is {"text": ..., "callback_data": ...}.
    """
    _rows: list[list[dict[str, str]]] = field(default_factory=list)
    _current_row: list[dict[str, str]] = field(default_factory=list)

    def row(self) -> "InlineKeyboard":
        """Start a new row. Flushes any pending buttons to previous row."""
        if self._current_row:
            self._rows.append(self._current_row)
            self._current_row = []
        return self

    def button(self, text: str, callback_data: str) -> "InlineKeyboard":
        """Add a button to the current row.

        Args:
            text: visible button label
            callback_data: payload sent back on click (max 64 bytes recommended)
        """
        self._current_row.append({
            "text": text,
            "callback_data": callback_data,
        })
        return self

    def build(self) -> list[list[dict[str, str]]]:
        """Finalize and return the button layout.

        Returns list of rows, each row is a list of button dicts.
        Returns empty list if no buttons were added.
        """
        rows = list(self._rows)
        if self._current_row:
            rows.append(self._current_row)
        return rows

    @staticmethod
    def yes_no(
        yes_label: str = "Да",
        no_label: str = "Нет",
        yes_data: str = "approve",
        no_data: str = "reject",
    ) -> list[list[dict[str, str]]]:
        """Convenience: single-row Yes/No keyboard."""
        return [[
            {"text": yes_label, "callback_data": yes_data},
            {"text": no_label, "callback_data": no_data},
        ]]

    @staticmethod
    def choices(
        options: dict[str, str],
        columns: int = 1,
    ) -> list[list[dict[str, str]]]:
        """Convenience: build keyboard from {callback_data: label} dict.

        Args:
            options: mapping of callback_data → display text
            columns: buttons per row (default 1 = vertical layout)
        """
        buttons = [
            {"text": label, "callback_data": data}
            for data, label in options.items()
        ]
        rows: list[list[dict[str, str]]] = []
        for i in range(0, len(buttons), columns):
            rows.append(buttons[i : i + columns])
        return rows
