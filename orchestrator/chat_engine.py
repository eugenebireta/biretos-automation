"""
chat_engine.py — contextual Q&A for owner messages.

Called by owner_bridge._handle_chat when the owner sends a free-text
question that is not a task, approve/reject, or status command.

Uses Claude (Anthropic API) with manifest context so answers are relevant
to the current orchestrator state (which task is running, what happened
last, etc.). Falls back to a manifest summary if Anthropic is unavailable.

Key loading uses scripts/secrets.py (centralized hub) with legacy fallback.
"""
from __future__ import annotations

import os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
_MAX_RESPONSE = 1500


def _load_secret(name: str) -> str:
    """Load secret via centralized hub (scripts/secrets.py) with env fallback."""
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from scripts.secrets import get_secret  # type: ignore[import-untyped]
        return get_secret(name, default="")
    except Exception:
        pass
    return os.environ.get(name, "")


def _load_gemini_key() -> str:
    return _load_secret("GEMINI_API_KEY")


def _load_anthropic_key() -> str:
    return _load_secret("ANTHROPIC_API_KEY")


def _manifest_summary(manifest: dict) -> str:
    state = manifest.get("fsm_state", "unknown")
    task = manifest.get("current_task_id") or "нет"
    goal = manifest.get("current_sprint_goal") or "нет"
    park = manifest.get("park_reason") or "нет"
    verdict = manifest.get("last_verdict") or "нет"
    return (
        f"FSM: {state} | Задача: {task} | Цель: {goal} | "
        f"Причина паузы: {park} | Вердикт: {verdict}"
    )


def answer(message: str, manifest: dict) -> str:
    """Answer owner question with manifest context via Claude (Anthropic API).

    Falls back to manifest summary if Anthropic is unavailable.
    """
    key = _load_anthropic_key()
    if not key:
        return f"(Нет ключа Anthropic)\n{_manifest_summary(manifest)}"

    try:
        import anthropic  # type: ignore[import-untyped]

        state = manifest.get("fsm_state", "unknown")
        task = manifest.get("current_task_id") or "нет"
        goal = manifest.get("current_sprint_goal") or "нет"
        park = manifest.get("park_reason") or "нет"
        verdict = manifest.get("last_verdict") or "нет"
        trace = manifest.get("trace_id") or "нет"

        system_ctx = (
            "Ты — AI-ассистент проекта biretos-automation. "
            "Отвечаешь владельцу проекта на вопросы через MAX мессенджер. "
            "Отвечай кратко, по-русски, без лишних вводных слов.\n\n"
            "Текущее состояние оркестратора:\n"
            f"  fsm_state: {state}\n"
            f"  task_id: {task}\n"
            f"  sprint_goal: {goal}\n"
            f"  park_reason: {park}\n"
            f"  last_verdict: {verdict}\n"
            f"  trace_id: {trace}\n"
        )

        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system_ctx,
            messages=[{"role": "user", "content": message}],
        )
        return (response.content[0].text or "").strip()[:_MAX_RESPONSE]

    except Exception as exc:
        return (
            f"(Ошибка Anthropic: {str(exc)[:80]})\n"
            f"{_manifest_summary(manifest)}"
        )
