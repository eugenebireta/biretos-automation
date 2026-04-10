#!/usr/bin/env python3
"""
tg_send.py — Enqueue a message for Telegram delivery via Gateway.

Usage:
    python tools/tg_send.py "Текст сообщения"
    echo "Текст" | python tools/tg_send.py

Writes to orchestrator/owner_outbox.jsonl. Gateway picks up and sends.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "orchestrator"))
from telegram_gateway import enqueue_outbox  # noqa: E402


def main():
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    elif not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    else:
        print("Usage: python tools/tg_send.py \"message\"")
        sys.exit(1)

    if not text:
        print("Empty message, skipping.")
        sys.exit(0)

    msg_id = enqueue_outbox(text, event_type="manual")
    print(f"Queued: {msg_id}")


if __name__ == "__main__":
    main()
