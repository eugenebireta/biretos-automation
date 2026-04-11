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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"
ENV_PATH = ORCH_DIR / ".env.max"


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
    try:
        from orchestrator.messaging.max_adapter import MaxAdapter
    except ModuleNotFoundError:
        from messaging.max_adapter import MaxAdapter
    from telegram_gateway import TelegramGateway

    token, owner_id = _load_env()
    adapter = MaxAdapter(token)
    gw = TelegramGateway(adapter, owner_id, ORCH_DIR)
    gw.run()


if __name__ == "__main__":
    main()
