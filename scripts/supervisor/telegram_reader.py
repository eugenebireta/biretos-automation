from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from supervisor.rules import isoformat_z


GetJsonFn = Callable[[str, dict[str, Any], float], dict[str, Any]]


def _get_json(url: str, params: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    response = httpx.get(url, params=params, timeout=timeout_seconds)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Telegram response is not a JSON object")
    if not bool(data.get("ok")):
        raise RuntimeError(str(data.get("description") or "Telegram API returned ok=false"))
    return data


def poll_updates(
    runtime: dict[str, Any],
    telegram_state: dict[str, Any],
    *,
    now: datetime | None = None,
    get_json: GetJsonFn | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    get_json = get_json or _get_json
    last_update_id = int(telegram_state.get("last_update_id") or 0)
    url = f"{runtime['api_base']}/bot{runtime['bot_token']}/getUpdates"
    params = {
        "offset": last_update_id + 1,
        "limit": int(runtime.get("poll_limit") or 20),
        "allowed_updates": ["callback_query"],
    }
    response = get_json(url, params, float(runtime.get("poll_timeout_seconds") or 15))
    updates = list(response.get("result") or [])
    max_update_id = last_update_id
    for update in updates:
        update_id = int(update.get("update_id") or 0)
        if update_id > max_update_id:
            max_update_id = update_id
    next_state = {
        "last_update_id": max_update_id,
        "last_poll_ts": isoformat_z(now),
    }
    return updates, next_state


def apply_callback_updates(
    updates: list[dict[str, Any]],
    packet_states: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for update in updates:
        update_id = int(update.get("update_id") or 0)
        callback = dict(update.get("callback_query") or {})
        if not callback:
            continue
        data = str(callback.get("data") or "").strip()
        if not data.startswith("sup|"):
            continue
        _, packet_id, option_id = (data.split("|", 2) + ["", ""])[:3]
        packet = dict(packet_states.get(packet_id) or {})
        if not packet:
            events.append(
                {
                    "event_type": "callback_ignored",
                    "packet_id": packet_id,
                    "decision_status": "ignored",
                    "applied_option_id": None,
                    "telegram_update_id": update_id,
                    "ignored_reason": "unknown_packet",
                }
            )
            continue
        current_status = str(packet.get("decision_status") or "").strip()
        valid_options = {str(option.get("id")) for option in list(packet.get("options") or [])}
        if current_status != "pending":
            events.append(
                {
                    "event_type": "callback_ignored",
                    "packet_id": packet_id,
                    "decision_status": current_status,
                    "applied_option_id": packet.get("applied_option_id"),
                    "telegram_update_id": update_id,
                    "ignored_reason": "already_processed",
                }
            )
            continue
        if option_id not in valid_options:
            events.append(
                {
                    "event_type": "callback_ignored",
                    "packet_id": packet_id,
                    "decision_status": current_status,
                    "applied_option_id": packet.get("applied_option_id"),
                    "telegram_update_id": update_id,
                    "ignored_reason": "invalid_option",
                }
            )
            continue
        events.append(
            {
                "event_type": "callback_applied",
                "packet_id": packet_id,
                "decision_status": "applied",
                "applied_option_id": option_id,
                "applied_at": isoformat_z(datetime.now(timezone.utc)),
                "telegram_update_id": update_id,
            }
        )
        packet_states[packet_id] = {**packet, "decision_status": "applied", "applied_option_id": option_id}
    return events
