"""Tests for orchestrator/messaging/buttons.py — Wave 4 InlineKeyboard builder."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure orchestrator/ is on sys.path for direct imports
_orch = str(Path(__file__).resolve().parent.parent.parent / "orchestrator")
if _orch not in sys.path:
    sys.path.insert(0, _orch)

from messaging.buttons import InlineKeyboard  # noqa: E402


class TestInlineKeyboardBuilder:
    """Core builder pattern tests."""

    def test_single_row(self):
        kb = InlineKeyboard().row().button("A", "a").button("B", "b").build()
        assert kb == [[{"text": "A", "callback_data": "a"},
                       {"text": "B", "callback_data": "b"}]]

    def test_multiple_rows(self):
        kb = (InlineKeyboard()
              .row().button("A", "a")
              .row().button("B", "b")
              .build())
        assert len(kb) == 2
        assert kb[0] == [{"text": "A", "callback_data": "a"}]
        assert kb[1] == [{"text": "B", "callback_data": "b"}]

    def test_no_buttons_returns_empty(self):
        kb = InlineKeyboard().build()
        assert kb == []

    def test_buttons_without_explicit_row(self):
        """Buttons added before first row() go to current row."""
        kb = InlineKeyboard().button("X", "x").build()
        assert kb == [[{"text": "X", "callback_data": "x"}]]

    def test_empty_row_not_added(self):
        """Calling row() twice doesn't create empty rows."""
        kb = InlineKeyboard().row().row().button("A", "a").build()
        assert kb == [[{"text": "A", "callback_data": "a"}]]

    def test_build_is_idempotent(self):
        builder = InlineKeyboard().row().button("A", "a")
        assert builder.build() == builder.build()


class TestYesNo:
    """Convenience yes/no keyboard."""

    def test_default_labels(self):
        kb = InlineKeyboard.yes_no()
        assert len(kb) == 1
        assert len(kb[0]) == 2
        assert kb[0][0]["callback_data"] == "approve"
        assert kb[0][1]["callback_data"] == "reject"

    def test_custom_labels(self):
        kb = InlineKeyboard.yes_no(yes_label="OK", no_label="Cancel",
                                    yes_data="ok", no_data="cancel")
        assert kb[0][0]["text"] == "OK"
        assert kb[0][1]["text"] == "Cancel"
        assert kb[0][0]["callback_data"] == "ok"
        assert kb[0][1]["callback_data"] == "cancel"


class TestChoices:
    """Convenience choices keyboard."""

    def test_single_column(self):
        kb = InlineKeyboard.choices({"a": "Option A", "b": "Option B"})
        assert len(kb) == 2
        assert kb[0] == [{"text": "Option A", "callback_data": "a"}]
        assert kb[1] == [{"text": "Option B", "callback_data": "b"}]

    def test_multi_column(self):
        kb = InlineKeyboard.choices(
            {"a": "A", "b": "B", "c": "C", "d": "D"},
            columns=2,
        )
        assert len(kb) == 2
        assert len(kb[0]) == 2
        assert len(kb[1]) == 2

    def test_empty_options(self):
        kb = InlineKeyboard.choices({})
        assert kb == []

    def test_odd_count_with_columns(self):
        kb = InlineKeyboard.choices({"a": "A", "b": "B", "c": "C"}, columns=2)
        assert len(kb) == 2
        assert len(kb[0]) == 2
        assert len(kb[1]) == 1
