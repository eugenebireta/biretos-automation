"""
chat_engine.py — contextual Q&A for owner messages.

Called by owner_bridge._handle_chat when the owner sends a free-text
question that is not a task, approve/reject, or status command.

Uses Gemini 2.5 Flash with manifest context so answers are relevant
to the current orchestrator state (which task is running, what happened
last, etc.). Falls back to a manifest summary if Gemini is unavailable.
"""
from __future__ import annotations

import os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
_ENV_PATHS = [
    ROOT / "downloads" / ".env",
    ROOT / "orchestrator" / ".env.max",
]
_MAX_RESPONSE = 1500


def _load_gemini_key() -> str:
    for path in _ENV_PATHS:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return os.environ.get("GEMINI_API_KEY", "")


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
    """Answer owner question with manifest context via Gemini.

    Falls back to manifest summary if Gemini is unavailable.
    """
    key = _load_gemini_key()
    if not key:
        return f"(Gemini недоступен)\n{_manifest_summary(manifest)}"

    try:
        from google import genai  # type: ignore[import-untyped]
        client = genai.Client(api_key=key)

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

        prompt = f"{system_ctx}\nВопрос владельца: {message}"

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return (response.text or "").strip()[:_MAX_RESPONSE]

    except Exception as exc:
        return (
            f"(Ошибка Gemini: {str(exc)[:80]})\n"
            f"{_manifest_summary(manifest)}"
        )
