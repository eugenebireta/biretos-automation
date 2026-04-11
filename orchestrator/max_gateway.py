"""
max_gateway.py — MAX messenger transport layer ("dumb pipe").

Identical architecture to telegram_gateway.py but uses MaxAdapter.
Polls MAX Bot API, writes to owner_inbox.jsonl, reads owner_outbox.jsonl.

Usage:
    python orchestrator/max_gateway.py

Config: orchestrator/.env.max
    MAX_BOT_TOKEN=<token>
    MAX_OWNER_USER_ID=<user_id>
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"
ENV_PATH = ORCH_DIR / ".env.max"
PID_LOCK_PATH = ORCH_DIR / "max_gateway.pid"
MARKER_PATH = ORCH_DIR / "max_marker.json"


def _acquire_pid_lock() -> bool:
    """Return True if this process acquired the lock.

    Returns False if another max_gateway instance is already running.
    Writes current PID to lockfile; clears stale locks from dead processes.
    """
    if PID_LOCK_PATH.exists():
        try:
            old_pid = int(PID_LOCK_PATH.read_text(encoding="utf-8").strip())
            if old_pid != os.getpid():
                # Check if old process is still alive
                try:
                    os.kill(old_pid, 0)   # raises if process does not exist
                    return False           # still running
                except (OSError, ProcessLookupError):
                    pass                   # stale lock — overwrite
        except Exception:
            pass  # unreadable lock — overwrite
    PID_LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _release_pid_lock() -> None:
    try:
        PID_LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _load_env() -> tuple[str, int | None]:
    """Load (token, owner_user_id) from .env.max."""
    token = ""
    owner_id = None
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MAX_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
            elif line.startswith("MAX_OWNER_USER_ID="):
                raw = line.split("=", 1)[1].strip()
                if raw.isdigit():
                    owner_id = int(raw)
    if not token:
        token = os.environ.get("MAX_BOT_TOKEN", "")
    if not token:
        raise ValueError("MAX_BOT_TOKEN not found in .env.max or environment")
    return token, owner_id


def main():
    if not _acquire_pid_lock():
        existing_pid = PID_LOCK_PATH.read_text(encoding="utf-8").strip()
        print(
            f"[max_gateway] Another instance already running (PID {existing_pid}). Exiting.",
            file=sys.stderr,
        )
        sys.exit(0)

    try:
        from orchestrator.messaging.max_adapter import MaxAdapter
    except ModuleNotFoundError:
        from messaging.max_adapter import MaxAdapter
    try:
        from orchestrator.telegram_gateway import TelegramGateway
    except ModuleNotFoundError:
        from telegram_gateway import TelegramGateway

    token, owner_id = _load_env()
    adapter = MaxAdapter(token, marker_path=MARKER_PATH)
    gw = TelegramGateway(adapter, owner_id, ORCH_DIR)
    try:
        gw.run()
    finally:
        _release_pid_lock()


if __name__ == "__main__":
    main()
