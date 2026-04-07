from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from supervisor import ROOT


DEFAULT_CONFIG: dict[str, Any] = {
    "batch_limits": {
        "photo": 10,
        "price": 20,
    },
    "telegram": {
        "enabled": True,
        "api_base": "https://api.telegram.org",
        "bot_token_key": "SUPERVISOR_TELEGRAM_BOT_TOKEN",
        "chat_id_key": "SUPERVISOR_TELEGRAM_CHAT_ID",
        "poll_limit": 20,
        "send_timeout_seconds": 15,
        "poll_timeout_seconds": 15,
        "delivery_retry_backoff_seconds": [60, 300, 1800],
        "decision_timeout_hours": 24,
    }
}


def config_path() -> Path:
    return ROOT / "config" / "supervisor.yaml"


def secrets_path() -> Path:
    return ROOT / "config" / ".env.supervisor"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def load_supervisor_config(path: Path | None = None) -> dict[str, Any]:
    path = path or config_path()
    payload: dict[str, Any] = {}
    if path.exists():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _deep_merge(DEFAULT_CONFIG, payload)


def load_batch_limits(config: dict[str, Any] | None = None) -> dict[str, int]:
    config = config or load_supervisor_config()
    raw = dict(config.get("batch_limits") or {})
    photo_limit = int(raw.get("photo") or DEFAULT_CONFIG["batch_limits"]["photo"])
    price_limit = int(raw.get("price") or DEFAULT_CONFIG["batch_limits"]["price"])
    return {
        "photo": max(photo_limit, 1),
        "price": max(price_limit, 1),
    }


def load_supervisor_secrets(path: Path | None = None) -> dict[str, str]:
    path = path or secrets_path()
    if not path.exists():
        return {}
    return {str(k): str(v) for k, v in dict(dotenv_values(str(path))).items() if v is not None}


def load_telegram_runtime(
    *,
    config: dict[str, Any] | None = None,
    secrets: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    config = config or load_supervisor_config()
    secrets = secrets or load_supervisor_secrets()
    telegram_cfg = dict(config.get("telegram") or {})
    if not bool(telegram_cfg.get("enabled", True)):
        return None
    token_key = str(telegram_cfg.get("bot_token_key") or "").strip()
    chat_key = str(telegram_cfg.get("chat_id_key") or "").strip()
    bot_token = str(secrets.get(token_key) or "").strip()
    chat_id = str(secrets.get(chat_key) or "").strip()
    if not bot_token or not chat_id:
        return None
    return {
        "api_base": str(telegram_cfg.get("api_base") or "https://api.telegram.org").rstrip("/"),
        "bot_token": bot_token,
        "chat_id": chat_id,
        "poll_limit": int(telegram_cfg.get("poll_limit") or 20),
        "send_timeout_seconds": float(telegram_cfg.get("send_timeout_seconds") or 15),
        "poll_timeout_seconds": float(telegram_cfg.get("poll_timeout_seconds") or 15),
        "delivery_retry_backoff_seconds": list(telegram_cfg.get("delivery_retry_backoff_seconds") or [60, 300, 1800]),
        "decision_timeout_hours": int(telegram_cfg.get("decision_timeout_hours") or 24),
    }
