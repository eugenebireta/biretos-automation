"""
telegram_notifier.py — Proactive push notifications to owner via Telegram.

Sends messages when orchestrator parks tasks or needs owner decisions.
Works WITHOUT the bot being running — makes direct HTTP calls to Bot API.

Config: orchestrator/.env.telegram
  TELEGRAM_BOT_TOKEN=<token>
  TELEGRAM_OWNER_CHAT_ID=<chat_id>   ← saved automatically by /start in telegram_bot.py

Usage:
    from telegram_notifier import notify_park, notify_decision, send
    notify_park("awaiting_owner_reply", "#blocker_loop: ...", task_id="fix-auth")
    notify_decision("Что делать?", {"A": "Вариант А", "B": "Вариант Б"})
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"
MANIFEST_PATH = ORCH_DIR / "manifest.json"
ENV_PATH = ORCH_DIR / ".env.telegram"

logger = logging.getLogger(__name__)

# Injectable for tests — replaces HTTP send
_send_fn: Optional[object] = None

# Config-flag guard: disabled when telegram_gateway is active
_notifier_enabled: Optional[bool] = None
_notifier_checked_at: float = 0


def _is_notifier_enabled() -> bool:
    """Check config.yaml flag. Cached for 60s to avoid disk reads."""
    global _notifier_enabled, _notifier_checked_at
    import time
    now = time.time()
    if _notifier_enabled is not None and (now - _notifier_checked_at) < 60:
        return _notifier_enabled
    _notifier_checked_at = now
    config_path = ORCH_DIR / "config.yaml"
    if config_path.exists():
        try:
            text = config_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.strip().startswith("telegram_notifier_enabled:"):
                    val = line.split(":", 1)[1].strip().lower()
                    _notifier_enabled = val in ("true", "yes", "1")
                    return _notifier_enabled
        except Exception:
            pass
    _notifier_enabled = True  # default: enabled if flag missing
    return _notifier_enabled

# Dedup: remember last sent message to avoid spamming owner with repeats
_last_sent_hash: Optional[str] = None


def _load_config() -> tuple[str | None, str | None]:
    """Load (token, chat_id) from .env.telegram. Returns (None, None) if missing."""
    if not ENV_PATH.exists():
        return None, None
    token = None
    chat_id = None
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            token = line.split("=", 1)[1].strip()
        elif line.startswith("TELEGRAM_OWNER_CHAT_ID="):
            chat_id = line.split("=", 1)[1].strip()
    return token, chat_id


def send(text: str) -> bool:
    """Send plain text message to owner chat.

    Returns True on success, False if not configured or delivery failed.
    Silently no-ops if TELEGRAM_OWNER_CHAT_ID is not set (bot not yet started).
    Disabled when telegram_notifier_enabled: false in config.yaml.
    """
    global _send_fn
    if _send_fn is not None:
        return _send_fn(text)  # type: ignore[operator]

    token, chat_id = _load_config()
    if not token or not chat_id:
        logger.debug("telegram_notifier: not configured (token=%s chat_id=%s)", bool(token), bool(chat_id))
        return False

    if not _is_notifier_enabled():
        logger.debug("telegram_notifier: disabled via config.yaml (gateway active)")
        return True  # return True so callers don't treat as failure

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status == 200
            if not ok:
                logger.warning("telegram_notifier: HTTP %s", resp.status)
            return ok
    except urllib.error.URLError as exc:
        logger.warning("telegram_notifier: send failed: %s", exc)
        return False


def notify_park(
    fsm_state: str,
    park_reason: str,
    task_id: Optional[str] = None,
) -> bool:
    """Notify owner when orchestrator parks a task.

    Translates technical state to plain Russian, sends to Telegram.
    Deduplicates: same (state, reason, task) won't be sent twice in a row.
    Returns True if message was sent successfully.
    """
    global _last_sent_hash
    import hashlib
    dedup_key = hashlib.md5(f"{fsm_state}|{park_reason}|{task_id}".encode()).hexdigest()
    if dedup_key == _last_sent_hash:
        logger.debug("telegram_notifier: dedup skip (same park state)")
        return True  # already sent
    try:
        from decision_translator import translate_park
        msg = translate_park(fsm_state, park_reason, task_id)
    except Exception as exc:
        logger.warning("telegram_notifier: translate failed: %s", exc)
        task_info = f"\nЗадача: {task_id}" if task_id else ""
        msg = f"Задача поставлена на паузу.{task_info}\n\nПричина: {park_reason[:200]}"

    ok = send(msg)
    if ok:
        _last_sent_hash = dedup_key
    return ok


def notify_decision(
    question: str,
    options: dict[str, str],
    save_to_manifest: bool = True,
) -> bool:
    """Ask owner a structured A/B/C decision question.

    Saves pending_decision to manifest so telegram_bot.py can parse the reply.

    Args:
        question: Plain-language question.
        options: {"A": "description", "B": "description", ...}
        save_to_manifest: Whether to persist pending_decision in manifest.

    Returns:
        True if message sent successfully.
    """
    try:
        from decision_translator import translate_decision
        msg = translate_decision(question, options)
    except Exception:
        lines = [question, ""]
        for k, v in options.items():
            lines.append(f"{k} — {v}")
        lines.append("\nОтветь: " + " / ".join(options.keys()))
        msg = "\n".join(lines)

    if save_to_manifest and MANIFEST_PATH.exists():
        try:
            m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            m["pending_decision"] = {"question": question, "options": options}
            MANIFEST_PATH.write_text(
                json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:
            logger.warning("telegram_notifier: manifest save failed: %s", exc)

    return send(msg)
