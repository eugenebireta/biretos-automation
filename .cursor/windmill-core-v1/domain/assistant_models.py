"""
Assistant domain models — Phase 7.

DegradationLevel enum, ConfirmationPending dataclass,
Telegram inline-button builders.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Degradation levels
# ---------------------------------------------------------------------------


class DegradationLevel(IntEnum):
    FULL_NLU = 0      # NLU enabled, confidence ok → offer confirm button
    ASSISTED = 1      # NLU low confidence → offer choice buttons
    BUTTON_ONLY = 2   # NLU disabled or unavailable → slash-commands only


# ---------------------------------------------------------------------------
# Human-readable intent labels (for Telegram messages)
# ---------------------------------------------------------------------------

INTENT_LABELS: Dict[str, str] = {
    "check_payment":  "Проверить оплату",
    "get_tracking":   "Статус доставки",
    "get_waybill":    "Получить накладную",
    "send_invoice":   "Выставить счёт",
}


# ---------------------------------------------------------------------------
# ConfirmationPending — in-memory mirror of nlu_pending_confirmations row
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfirmationPending:
    confirmation_id: str          # UUID from DB
    trace_id: str
    employee_id: str
    employee_role: str
    parsed_intent_type: str
    parsed_entities: Dict[str, str]
    model_version: str
    prompt_version: str
    confidence: float


# ---------------------------------------------------------------------------
# Telegram inline-keyboard builders
# ---------------------------------------------------------------------------


def build_confirm_buttons(confirmation_id: str, intent_type: str) -> Dict[str, Any]:
    """
    Returns a Telegram InlineKeyboardMarkup dict for confirming/cancelling
    a single parsed intent.

    callback_data format:
      nlu_confirm:<confirmation_id>   — user confirms execution
      nlu_cancel:<confirmation_id>    — user cancels

    Args:
        confirmation_id: UUID of the pending confirmation row.
        intent_type: one of SUPPORTED_NLU_INTENTS.
    """
    label = INTENT_LABELS.get(intent_type, intent_type)
    return {
        "inline_keyboard": [
            [
                {
                    "text": f"✅ Да, {label.lower()}",
                    "callback_data": f"nlu_confirm:{confirmation_id}",
                },
                {
                    "text": "❌ Отмена",
                    "callback_data": f"nlu_cancel:{confirmation_id}",
                },
            ]
        ]
    }


def build_choice_buttons(intent_types: List[str]) -> Dict[str, Any]:
    """
    Returns a Telegram InlineKeyboardMarkup dict offering the employee
    a choice between multiple possible intents (ASSISTED degradation mode).

    Each button triggers nlu_confirm:<intent_type> (no stored confirmation row;
    the handler will ask for fresh slash-command input).

    Args:
        intent_types: list of intent type strings to offer as choices.
    """
    rows: List[List[Dict[str, str]]] = []
    for it in intent_types:
        label = INTENT_LABELS.get(it, it)
        rows.append(
            [{"text": label, "callback_data": f"nlu_choice:{it}"}]
        )
    return {"inline_keyboard": rows}
