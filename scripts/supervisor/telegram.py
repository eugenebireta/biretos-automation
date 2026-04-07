from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx

from supervisor.rules import isoformat_z


PostJsonFn = Callable[[str, dict[str, Any], float], dict[str, Any]]


def _post_json(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    response = httpx.post(url, json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Telegram response is not a JSON object")
    if not bool(data.get("ok")):
        raise RuntimeError(str(data.get("description") or "Telegram API returned ok=false"))
    return data


def _callback_data(packet_id: str, option_id: str) -> str:
    return f"sup|{packet_id}|{option_id}"


def _format_options(packet: dict[str, Any]) -> str:
    rows = []
    for option in list(packet.get("options") or []):
        rows.append(f"- {option['id']}: {option['label']}")
    return "\n".join(rows)


def format_packet_text(packet: dict[str, Any]) -> str:
    packet_type = str(packet.get("type") or "")
    if packet_type == "incident":
        return (
            "[incident]\n"
            f"trace_id: {packet.get('trace_id')}\n"
            f"packet_id: {packet.get('packet_id')}\n"
            f"script: {packet.get('script')}\n"
            f"exit_code: {packet.get('exit_code')}\n"
            f"error_class: {packet.get('error_class')}\n"
            "action_required: technical review\n"
        )
    return (
        "[owner_decision]\n"
        f"trace_id: {packet.get('trace_id')}\n"
        f"packet_id: {packet.get('packet_id')}\n"
        f"what_blocked: {packet.get('what_blocked')}\n"
        f"question: {packet.get('business_question')}\n"
        f"affected_sku_count: {packet.get('affected_sku_count')}\n"
        f"recommended_option: {packet.get('recommended_option')}\n"
        "options:\n"
        f"{_format_options(packet)}\n"
    )


def build_reply_markup(packet: dict[str, Any]) -> dict[str, Any] | None:
    if str(packet.get("type") or "") != "owner_decision":
        return None
    keyboard = []
    for option in list(packet.get("options") or []):
        keyboard.append(
            [
                {
                    "text": str(option["label"]),
                    "callback_data": _callback_data(str(packet["packet_id"]), str(option["id"])),
                }
            ]
        )
    return {"inline_keyboard": keyboard}


def send_packet(
    packet: dict[str, Any],
    runtime: dict[str, Any],
    *,
    now: datetime | None = None,
    post_json: PostJsonFn | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    post_json = post_json or _post_json
    attempts = int(packet.get("delivery_attempts") or 0) + 1
    timeout_seconds = float(runtime.get("send_timeout_seconds") or 15)
    url = f"{runtime['api_base']}/bot{runtime['bot_token']}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": runtime["chat_id"],
        "text": format_packet_text(packet),
    }
    reply_markup = build_reply_markup(packet)
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        response = post_json(url, payload, timeout_seconds)
        message = dict(response.get("result") or {})
        return {
            "event_type": "delivery_update",
            "packet_id": packet["packet_id"],
            "delivery_status": "sent",
            "delivery_attempts": attempts,
            "next_retry_at": None,
            "last_send_error": None,
            "telegram_message_id": message.get("message_id"),
            "sent_at": isoformat_z(now),
            "decision_status": packet.get("decision_status"),
            "applied_option_id": packet.get("applied_option_id"),
        }
    except Exception as exc:
        backoff = list(runtime.get("delivery_retry_backoff_seconds") or [60, 300, 1800])
        index = min(attempts - 1, len(backoff) - 1)
        next_retry_at = now + timedelta(seconds=float(backoff[index]))
        return {
            "event_type": "delivery_update",
            "packet_id": packet["packet_id"],
            "delivery_status": "send_failed",
            "delivery_attempts": attempts,
            "next_retry_at": isoformat_z(next_retry_at),
            "last_send_error": str(exc),
            "telegram_message_id": packet.get("telegram_message_id"),
            "decision_status": packet.get("decision_status"),
            "applied_option_id": packet.get("applied_option_id"),
            "error_class": "TRANSIENT",
            "severity": "ERROR",
            "retriable": True,
        }
