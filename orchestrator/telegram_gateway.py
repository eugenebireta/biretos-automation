"""
telegram_gateway.py — Single Telegram transport layer ("dumb pipe").

The ONLY process allowed to poll Telegram getUpdates for this bot token.
Does NOT run subprocess. Does NOT mutate manifest.json. Does NOT make decisions.

Responsibilities:
    1. Poll Telegram for owner messages -> write to owner_inbox.jsonl
    2. Read owner_outbox.jsonl -> send pending messages to Telegram
    3. Auth: only accept messages from owner_chat_id
    4. Heartbeat + structured logging

Now uses MessengerTransport abstraction (Wave 1 refactor).
All Telegram API calls are delegated to TelegramAdapter.

Usage:
    python orchestrator/telegram_gateway.py

Config: orchestrator/.env.telegram
    TELEGRAM_BOT_TOKEN=<token>
    TELEGRAM_OWNER_CHAT_ID=<chat_id>
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Import transport abstraction
try:
    from orchestrator.messaging.base import MessengerTransport, CanonicalEvent
    from orchestrator.messaging.telegram_adapter import TelegramAdapter
except ModuleNotFoundError:
    from messaging.base import MessengerTransport, CanonicalEvent
    from messaging.telegram_adapter import TelegramAdapter

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"
INBOX_PATH = ORCH_DIR / "owner_inbox.jsonl"
OUTBOX_PATH = ORCH_DIR / "owner_outbox.jsonl"
HEARTBEAT_PATH = ORCH_DIR / "gateway_heartbeat.json"
LOG_PATH = ORCH_DIR / "gateway.log"
ENV_PATH = ORCH_DIR / ".env.telegram"

# Redaction patterns — never send these to messenger
_REDACT_PATTERNS = [
    "\\Users\\",
    "/home/",
    "Traceback (most recent",
    "File \"",
]

# Truncation limit for outbound text
_TRUNCATE_AT = 4000


def _iso_z(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat()


def _redact(text: str) -> str:
    """Remove local paths, tracebacks, and secrets from outbound text."""
    lines = text.splitlines()
    clean = []
    skip_traceback = False
    for line in lines:
        if "Traceback (most recent" in line:
            skip_traceback = True
            clean.append("[traceback redacted]")
            continue
        if skip_traceback:
            if line and not line.startswith(" ") and not line.startswith("\t"):
                skip_traceback = False
            else:
                continue
        redacted = False
        for pat in _REDACT_PATTERNS:
            if pat in line:
                redacted = True
                break
        if not redacted:
            clean.append(line)
    result = "\n".join(clean).strip()
    if len(result) > _TRUNCATE_AT:
        result = result[:_TRUNCATE_AT] + "\n[...обрезано]"
    return result


# ── File locking (Windows + POSIX) ─────────────────────────────────────


def _locked_append(path: Path, line: str) -> None:
    """Append one line to a JSONL file with file locking."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a", encoding="utf-8")
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
        fh.write(line.rstrip("\n") + "\n")
        fh.flush()
    finally:
        if sys.platform == "win32":
            import msvcrt
            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except (IOError, OSError):
                pass
        fh.close()


def _atomic_write_json(path: Path, data: dict) -> None:
    """Atomic JSON write via tmp + rename."""
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


# ── Config loading ──────────────────────────────────────────────────────


def _load_env() -> tuple[str, int | None]:
    """Load (token, chat_id) from .env.telegram."""
    token = ""
    chat_id = None
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_OWNER_CHAT_ID="):
                raw = line.split("=", 1)[1].strip()
                if raw.isdigit():
                    chat_id = int(raw)
    if not token:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in .env.telegram or environment")
    return token, chat_id


# ── Gateway ─────────────────────────────────────────────────────────────


class TelegramGateway:
    """Single-process gateway. Transport-agnostic inbox/outbox bridge.

    Uses MessengerTransport for all platform API calls.
    Owns: auth, redaction, dedup, inbox/outbox file I/O, heartbeat.
    """

    def __init__(self, transport: MessengerTransport, owner_chat_id: int | None,
                 data_dir: Path):
        self.transport = transport
        self.owner_chat_id = owner_chat_id
        self.data_dir = data_dir

        self._sent_dedup: collections.deque[str] = collections.deque(maxlen=500)
        self._recv_dedup: collections.deque[str] = collections.deque(maxlen=500)
        self._started_at = datetime.now(timezone.utc)
        self._inbox_count = 0
        self._outbox_count = 0
        self._error_count = 0

    # ── Logging ─────────────────────────────────────────────────────

    def _log(self, level: str, event: str, **kw: Any) -> None:
        entry = {"ts": _iso_z(), "level": level, "event": event, **kw}
        try:
            _locked_append(LOG_PATH, json.dumps(entry, ensure_ascii=False))
        except Exception:
            pass
        print(f"[{entry['ts'][:19]}] {level} {event} {kw or ''}", flush=True)

    # ── Auth ────────────────────────────────────────────────────────

    def _is_authorized(self, chat_id: int | str) -> bool:
        if self.owner_chat_id is None:
            return True  # first message sets owner
        return int(chat_id) == self.owner_chat_id

    def _save_owner_chat_id(self, chat_id: int) -> None:
        """Persist owner chat_id on first /start."""
        self.owner_chat_id = chat_id
        if not ENV_PATH.exists():
            return
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        new_lines = [ln for ln in lines if not ln.strip().startswith("TELEGRAM_OWNER_CHAT_ID=")]
        new_lines.append(f"TELEGRAM_OWNER_CHAT_ID={chat_id}")
        ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        self._log("INFO", "owner_registered", chat_id=chat_id)

    # ── Inbound processing ──────────────────────────────────────────

    def _process_event(self, event: CanonicalEvent) -> None:
        """Process one canonical event from the transport."""
        chat_id = event.chat_id
        text = event.text

        if not chat_id:
            return

        # Auth gate
        if self.owner_chat_id is None:
            self._save_owner_chat_id(int(chat_id))
        elif not self._is_authorized(chat_id):
            self._log("WARNING", "auth_rejected", chat_id=chat_id)
            return

        if not text:
            return

        # /ping or /health — respond directly (no bridge needed)
        if text.lower() in ("/ping", "/health"):
            uptime = int((datetime.now(timezone.utc) - self._started_at).total_seconds())
            self.transport.send_message(
                str(self.owner_chat_id),
                f"Gateway alive.\n"
                f"Uptime: {uptime}s\n"
                f"Inbox: {self._inbox_count}\n"
                f"Outbox sent: {self._outbox_count}\n"
                f"Errors: {self._error_count}",
            )
            return

        # Callback events: acknowledge immediately, then write to inbox
        if event.event_type == "callback" and event.callback_data:
            try:
                self.transport.answer_callback(event.callback_data)
            except Exception as e:
                self._log("WARNING", "callback_ack_failed",
                          error=str(e)[:200],
                          error_class="TRANSIENT", retriable=True)

        # Inbound dedup — skip if same raw_hash seen this session
        dedup_key = event.raw_hash or event.message_id
        if dedup_key and dedup_key in self._recv_dedup:
            self._log("INFO", "inbox_skip_dup", msg_id=event.message_id,
                      text_preview=text[:40])
            return
        if dedup_key:
            self._recv_dedup.append(dedup_key)

        # Write to inbox — canonical event envelope
        entry = {
            "ts": _iso_z(),
            "msg_id": event.message_id,
            "update_id": event.update_id,
            "chat_id": chat_id,
            "text": text,
            "source": event.source,
            "event_type": event.event_type,
            "callback_data": event.callback_data,
            "raw_hash": event.raw_hash,
        }
        _locked_append(INBOX_PATH, json.dumps(entry, ensure_ascii=False))
        self._inbox_count += 1
        self._log("INFO", "inbox_write", msg_id=entry["msg_id"],
                  event_type=event.event_type,
                  text_preview=text[:80])

    # ── Outbox dispatch ─────────────────────────────────────────────

    def _flush_outbox(self) -> None:
        """Read outbox, send pending messages, rewrite file without sent items."""
        if not OUTBOX_PATH.exists():
            return

        try:
            lines = OUTBOX_PATH.read_text(encoding="utf-8").splitlines()
        except Exception:
            return

        if not lines:
            return

        transport_name = self.transport.transport_name
        remaining = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            status = entry.get("status", "pending")
            if status != "pending":
                continue

            # Target filter: only process messages for this transport
            target = entry.get("target")
            if target and target != transport_name:
                remaining.append(line)  # keep for other gateway
                continue

            dedup_key = entry.get("dedup_key", "")
            if dedup_key and dedup_key in self._sent_dedup:
                self._log("DEBUG", "outbox_dedup_skip", dedup_key=dedup_key)
                continue

            text = _redact(entry.get("text", ""))
            if not text:
                continue

            buttons = entry.get("buttons")
            ref = self.transport.send_message(str(self.owner_chat_id), text,
                                              buttons=buttons)
            if ref.success:
                self._outbox_count += 1
                if dedup_key:
                    self._sent_dedup.append(dedup_key)
                self._log("INFO", "outbox_send", msg_id=entry.get("msg_id"))
            else:
                # Keep for retry next cycle
                remaining.append(line)
                self._log("WARNING", "outbox_send_failed",
                          msg_id=entry.get("msg_id"))

        # Rewrite outbox with only unsent items
        try:
            if remaining:
                OUTBOX_PATH.write_text("\n".join(remaining) + "\n",
                                       encoding="utf-8")
            else:
                OUTBOX_PATH.write_text("", encoding="utf-8")
        except Exception as e:
            self._log("ERROR", "outbox_rewrite_failed", error=str(e)[:200])

    # ── Heartbeat ───────────────────────────────────────────────────

    def _write_heartbeat(self) -> None:
        uptime = int((datetime.now(timezone.utc) - self._started_at).total_seconds())
        transport_status = self.transport.get_status()
        data = {
            "pid": os.getpid(),
            "transport": self.transport.transport_name,
            "started_at": _iso_z(self._started_at),
            "last_poll_ts": _iso_z(),
            "inbox_lines_written": self._inbox_count,
            "outbox_lines_sent": self._outbox_count,
            "errors_last_hour": self._error_count,
            "uptime_seconds": uptime,
            **transport_status,
        }
        try:
            _atomic_write_json(HEARTBEAT_PATH, data)
        except Exception:
            pass

    # ── Main loop ───────────────────────────────────────────────────

    def run(self) -> None:
        transport_label = self.transport.transport_name.upper()
        self._log("INFO", "gateway_start", pid=os.getpid(),
                  transport=transport_label)
        print(flush=True)
        print("=" * 50, flush=True)
        print(f"  {transport_label} GATEWAY v2.0", flush=True)
        print("  Dumb pipe — inbox/outbox only", flush=True)
        print("=" * 50, flush=True)
        print(flush=True)

        try:
            while True:
                try:
                    events = self.transport.receive_updates()
                    for ev in events:
                        self._process_event(ev)
                    self._flush_outbox()
                    self._write_heartbeat()
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    self._log("ERROR", "loop_error", error=str(e)[:200])
                    self._error_count += 1
                    time.sleep(5)
        except KeyboardInterrupt:
            self._log("INFO", "gateway_stop", reason="keyboard_interrupt")
            print("\nGateway stopped.", flush=True)


# ── Outbox helper for other modules ─────────────────────────────────────


def enqueue_outbox(
    text: str,
    *,
    run_id: str | None = None,
    event_type: str = "message",
    state: str | None = None,
    reason_code: str | None = None,
    target: str = "telegram",
    buttons: list[list[dict]] | None = None,
) -> str:
    """Write a message to owner_outbox.jsonl for Gateway to deliver.

    Args:
        target: transport name filter. Gateway only sends messages
                matching its own transport_name. Default: "telegram".
        buttons: optional inline keyboard layout (Wave 4).
                 Format: [[{"text": "Label", "callback_data": "payload"}], ...]

    Returns the msg_id.
    """
    msg_id = f"out_{hashlib.md5(f'{time.time()}'.encode()).hexdigest()[:12]}"

    # Build dedup_key from structured fields if available
    dedup_parts = [run_id or "", event_type, state or "", reason_code or ""]
    dedup_key = hashlib.md5("|".join(dedup_parts).encode()).hexdigest()

    entry = {
        "ts": _iso_z(),
        "msg_id": msg_id,
        "text": text,
        "priority": "normal",
        "dedup_key": dedup_key,
        "status": "pending",
        "run_id": run_id,
        "event_type": event_type,
        "target": target,
    }
    if buttons:
        entry["buttons"] = buttons
    _locked_append(OUTBOX_PATH, json.dumps(entry, ensure_ascii=False))
    return msg_id


# ── Entry point ─────────────────────────────────────────────────────────


def main():
    token, chat_id = _load_env()
    adapter = TelegramAdapter(token)
    gw = TelegramGateway(adapter, chat_id, ORCH_DIR)
    gw.run()


if __name__ == "__main__":
    main()
