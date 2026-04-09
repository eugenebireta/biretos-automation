"""
decision_translator.py — Translates technical FSM park states to plain Russian.

Used by telegram_notifier.py to build human-friendly messages.
No external dependencies.
"""
from __future__ import annotations


def translate_park(
    fsm_state: str,
    park_reason: str,
    task_id: str | None = None,
) -> str:
    """Convert orchestrator park state to a plain-language Telegram message.

    Args:
        fsm_state: Value of manifest["fsm_state"] at park point.
        park_reason: Value of manifest["park_reason"].
        task_id: Current task ID for context, optional.

    Returns:
        Human-readable Russian message suitable for Telegram.
    """
    task_info = f"\nЗадача: {task_id}" if task_id else ""

    if fsm_state == "parked_budget_daily":
        return (
            f"Бюджет на сегодня исчерпан.{task_info}\n\n"
            f"Все задачи поставлены на паузу до завтра. "
            f"Стройка продолжит сама в следующий день.\n\n"
            f"Если нужно срочно — ответь 'ок'."
        )

    if fsm_state == "parked_budget_run":
        return (
            f"Эта задача оказалась слишком дорогой.{task_info}\n\n"
            f"Один прогон превысил лимит стоимости.\n\n"
            f"Ответь 'ок' чтобы продолжить, или 'нет' чтобы отменить."
        )

    if fsm_state == "parked_api_outage":
        return (
            f"Внешний сервис не отвечает.{task_info}\n\n"
            f"Задача поставлена на паузу. Система попробует снова позже.\n\n"
            f"Ответь 'ок' чтобы попробовать прямо сейчас."
        )

    if fsm_state == "awaiting_owner_reply":
        if "#blocker_loop" in park_reason:
            tries = "нескольких"
            if "after" in park_reason:
                parts = park_reason.split("after", 1)
                word = parts[1].strip().split()[0]
                if word.isdigit():
                    tries = word
            return (
                f"Задача застряла после {tries} попыток.{task_info}\n\n"
                f"Система не может исправить ошибку сама — "
                f"нужен взгляд со стороны.\n\n"
                f"Посмотри на ПК что именно не так.\n"
                f"Ответь 'ок' чтобы попробовать ещё раз, или 'нет' чтобы закрыть задачу."
            )
        if "#stalled" in park_reason:
            return (
                f"Стройка ждёт тебя слишком долго.{task_info}\n\n"
                f"Задача поставлена на паузу.\n\n"
                f"Ответь 'ок' когда будешь готов продолжить."
            )
        # Generic awaiting
        clean_reason = park_reason.lstrip("#").replace("_", " ")
        return (
            f"Стройке нужно твоё решение.{task_info}\n\n"
            f"Причина: {clean_reason[:200]}\n\n"
            f"Ответь 'ок' чтобы продолжить, или 'нет' чтобы остановить."
        )

    if fsm_state == "blocked":
        return (
            f"Задача заблокирована.{task_info}\n\n"
            f"Аудитор нашёл проблему которую нельзя исправить автоматически. "
            f"Посмотри детали на ПК.\n\n"
            f"Ответь 'ок' после того как разберёшься."
        )

    if "timeout" in fsm_state.lower() or "TIMEOUT" in park_reason:
        return (
            f"Задача выполнялась слишком долго и была остановлена.{task_info}\n\n"
            f"Ответь 'ок' чтобы запустить заново, или 'нет' чтобы отменить."
        )

    # Generic fallback
    clean = park_reason.replace("#", "").replace("_", " ")[:200]
    return (
        f"Задача поставлена на паузу.{task_info}\n\n"
        f"Причина: {clean}\n\n"
        f"Ответь 'ок' чтобы продолжить, или 'нет' чтобы остановить."
    )


def translate_decision(question: str, options: dict[str, str]) -> str:
    """Format a structured A/B/C decision question for Telegram.

    Args:
        question: Plain-language question text.
        options: Dict like {"A": "Добавить товары", "B": "Исправить категории"}.

    Returns:
        Formatted message string.
    """
    lines = [question, ""]
    for key, desc in options.items():
        lines.append(f"{key} — {desc}")
    lines.append("")
    keys = " / ".join(options.keys())
    lines.append(f"Ответь: {keys}")
    return "\n".join(lines)
