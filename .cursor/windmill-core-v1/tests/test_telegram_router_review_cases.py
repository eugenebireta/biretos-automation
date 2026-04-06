from __future__ import annotations

import sys
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_path()

import ru_worker.telegram_router as telegram_router


def _message_update(text: str) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "text": text,
            "from": {"id": 186497598, "is_bot": False},
            "chat": {"id": 186497598, "type": "private"},
        },
    }


def _callback_update(data: str) -> dict:
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb-1",
            "data": data,
            "from": {"id": 186497598, "is_bot": False},
            "message": {
                "message_id": 2,
                "chat": {"id": 186497598, "type": "private"},
            },
        },
    }


def test_review_cases_command_routes_to_list_action(monkeypatch):
    monkeypatch.setattr(telegram_router, "ALLOWED_USER_IDS", {186497598}, raising=False)

    response_text, action = telegram_router.route_update(_message_update("/review_cases"))

    assert response_text == "OK"
    assert action["action_type"] == "review_case_list"
    assert action["payload"]["limit"] == 10


def test_review_assign_command_routes_to_assign_action(monkeypatch):
    monkeypatch.setattr(telegram_router, "ALLOWED_USER_IDS", {186497598}, raising=False)
    case_id = "11111111-1111-1111-1111-111111111111"

    response_text, action = telegram_router.route_update(_message_update(f"/review_assign {case_id}"))

    assert response_text == "OK"
    assert action["action_type"] == "review_case_assign"
    assert action["payload"]["case_id"] == case_id


def test_review_resolve_command_routes_to_resolve_action(monkeypatch):
    monkeypatch.setattr(telegram_router, "ALLOWED_USER_IDS", {186497598}, raising=False)
    case_id = "11111111-1111-1111-1111-111111111111"

    response_text, action = telegram_router.route_update(_message_update(f"/review_resolve {case_id} executed"))

    assert response_text == "OK"
    assert action["action_type"] == "review_case_resolve"
    assert action["payload"]["case_id"] == case_id
    assert action["payload"]["resolution_status"] == "executed"


def test_review_assign_callback_routes(monkeypatch):
    monkeypatch.setattr(telegram_router, "ALLOWED_USER_IDS", {186497598}, raising=False)
    case_id = "11111111-1111-1111-1111-111111111111"

    response_text, action = telegram_router.route_update(_callback_update(f"review_assign:{case_id}"))

    assert response_text is None
    assert action["action_type"] == "review_case_assign"
    assert action["payload"]["case_id"] == case_id


def test_review_resolve_callback_routes(monkeypatch):
    monkeypatch.setattr(telegram_router, "ALLOWED_USER_IDS", {186497598}, raising=False)
    case_id = "11111111-1111-1111-1111-111111111111"

    response_text, action = telegram_router.route_update(_callback_update(f"review_resolve:{case_id}:cancelled"))

    assert response_text is None
    assert action["action_type"] == "review_case_resolve"
    assert action["payload"]["case_id"] == case_id
    assert action["payload"]["resolution_status"] == "cancelled"
