"""
chat_session.py — persistent conversation history for MAX ↔ Claude chat.

Each owner message + Claude response is appended to owner_chat_history.jsonl.
On next message, last N exchanges are injected into the prompt so Claude
has context of what was discussed.

Max history kept: 20 exchanges (auto-trimmed).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "orchestrator" / "owner_chat_history.jsonl"
MAX_EXCHANGES = 20  # keep last N full turns in context
MAX_CONTEXT_CHARS = 8000  # cap prompt injection size


def load_history() -> list[dict]:
    """Return last MAX_EXCHANGES turns from history file."""
    if not HISTORY_PATH.exists():
        return []
    try:
        lines = [
            json.loads(ln)
            for ln in HISTORY_PATH.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        return lines[-MAX_EXCHANGES:]
    except Exception:
        return []


def save_turn(user_msg: str, assistant_reply: str) -> None:
    """Append one completed turn to history."""
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user": user_msg,
        "assistant": assistant_reply,
    }
    try:
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # non-fatal — history loss is better than crash


def build_prompt(user_msg: str, manifest: dict) -> str:
    """Build full prompt with system context + history + current message."""
    state = manifest.get("fsm_state", "unknown")
    task = manifest.get("current_task_id") or "нет"
    goal = manifest.get("current_sprint_goal") or "нет"
    park = manifest.get("park_reason") or "нет"

    system = (
        "Ты — AI-ассистент проекта biretos-automation, общаешься с владельцем "
        "через MAX мессенджер. Отвечай кратко, по-русски, строго по теме вопроса. "
        "Не придумывай задачи и не рапортуй о несуществующей работе.\n\n"
        f"Состояние оркестратора: fsm={state}, task={task}, goal={goal}, park={park}\n"
    )

    history = load_history()
    history_text = ""
    if history:
        lines = []
        for turn in history:
            lines.append(f"Владелец: {turn['user']}")
            lines.append(f"Ассистент: {turn['assistant']}")
        history_text = "\n".join(lines)
        # Cap to avoid overflowing context
        if len(history_text) > MAX_CONTEXT_CHARS:
            history_text = history_text[-MAX_CONTEXT_CHARS:]
        history_text = f"\n[История разговора]\n{history_text}\n"

    return f"{system}{history_text}\nВладелец: {user_msg}"
