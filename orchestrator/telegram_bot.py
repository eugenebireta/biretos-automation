"""
telegram_bot.py — Telegram bridge for ИИ-стройка.

Listens for messages, runs strojka.py, sends results back.

Usage:
    python orchestrator/telegram_bot.py

Commands:
    Стройка: <задача>     — запустить задачу
    /status               — текущий статус манифеста
    /help                 — справка

Token: loaded from orchestrator/.env.telegram (gitignored).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"
MANIFEST_PATH = ORCH_DIR / "manifest.json"

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("strojka_bot")

# Owner chat ID — set on first /start, then only this user can use the bot
OWNER_CHAT_ID: int | None = None


def _load_token() -> str:
    """Load bot token from .env.telegram."""
    env_path = ORCH_DIR / ".env.telegram"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN not found in .env.telegram or environment"
        )
    return token


def _is_owner(update: Update) -> bool:
    """Check if message is from the owner."""
    global OWNER_CHAT_ID
    if OWNER_CHAT_ID is None:
        return True  # First user becomes owner
    return update.effective_chat.id == OWNER_CHAT_ID


def _truncate(text: str, limit: int = 4000) -> str:
    """Truncate text to fit Telegram message limit."""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n... (truncated)"


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register owner on first /start."""
    global OWNER_CHAT_ID
    if OWNER_CHAT_ID is None:
        OWNER_CHAT_ID = update.effective_chat.id
        logger.info("Owner registered: chat_id=%d", OWNER_CHAT_ID)
    await update.message.reply_text(
        "ИИ-Стройка на связи.\n\n"
        "Напиши:\n"
        "  Стройка: <описание задачи>\n\n"
        "Или:\n"
        "  /status — текущий статус\n"
        "  /help — справка"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    await update.message.reply_text(
        "Стройка: <задача> — запустить задачу\n"
        "/status — показать манифест\n"
        "/help — эта справка\n\n"
        "Примеры:\n"
        "  Стройка: добавить тесты для batch gate\n"
        "  Стройка: следующая задача по роадмапу\n"
        "  Стройка: спроектировать систему уведомлений"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    if not MANIFEST_PATH.exists():
        await update.message.reply_text("Манифест не найден. Стройка не запущена.")
        return
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    status_text = (
        f"FSM: {manifest.get('fsm_state', '?')}\n"
        f"Task: {manifest.get('current_task_id', '?')}\n"
        f"Goal: {manifest.get('current_sprint_goal', '?')[:200]}\n"
        f"Attempt: {manifest.get('attempt_count', 0)}\n"
        f"Verdict: {manifest.get('last_verdict', 'none')}\n"
        f"Updated: {manifest.get('updated_at', '?')}"
    )
    await update.message.reply_text(f"📋 Статус стройки:\n\n{status_text}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages."""
    if not _is_owner(update):
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    # Check for strojka trigger
    task_text = None
    for prefix in ("Стройка:", "стройка:", "Strojka:", "strojka:"):
        if text.startswith(prefix):
            task_text = text[len(prefix):].strip()
            break

    if not task_text:
        # Not a strojka command — ignore
        return

    if not task_text:
        await update.message.reply_text("Пустая задача. Напиши: Стройка: <описание>")
        return

    # Acknowledge
    msg = await update.message.reply_text(
        f"🔨 Принял задачу:\n{task_text[:200]}\n\nЗапускаю стройку..."
    )

    # Run strojka.py as subprocess
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        # Load API key from .env.auditors
        env_auditors = ROOT / "auditor_system" / "config" / ".env.auditors"
        if env_auditors.exists():
            for line in env_auditors.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

        result = subprocess.run(
            [sys.executable, str(ORCH_DIR / "strojka.py"), task_text],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
            cwd=str(ROOT),
            env=env,
        )

        output = (result.stdout or "") + (result.stderr or "")
        output = output.strip()

        if not output:
            output = "(нет вывода)"

        # Parse key info from output for a clean summary
        summary = _build_summary(output, task_text)
        await context.bot.edit_message_text(
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            text=summary,
        )

        # If output is long, send full log as a follow-up
        if len(output) > 500:
            await update.message.reply_text(
                f"📜 Полный лог:\n\n```\n{_truncate(output, 3800)}\n```",
                parse_mode="Markdown",
            )

    except subprocess.TimeoutExpired:
        await context.bot.edit_message_text(
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            text="⏰ Стройка не уложилась в 10 минут. Проверь вручную.",
        )
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            text=f"❌ Ошибка: {e}",
        )


def _build_summary(output: str, task: str) -> str:
    """Build a clean Telegram-friendly summary from strojka output."""
    lines = output.splitlines()

    # Extract key fields
    risk = "?"
    action = "?"
    gate = "?"
    trace = "?"
    files = "?"

    for line in lines:
        if "risk=" in line and "route=" in line:
            # [orchestrator] risk=LOW route=none
            parts = line.split()
            for p in parts:
                if p.startswith("risk="):
                    risk = p.split("=", 1)[1]
                    break
        if "synth action=" in line:
            for p in line.split():
                if p.startswith("action="):
                    action = p.split("=", 1)[1]
                    break
        if "Batch gate:" in line:
            if "passed=True" in line:
                gate = "PASS ✅"
            else:
                gate = "FAIL ❌"
        if "trace_id=" in line:
            for p in line.split():
                if p.startswith("trace_id="):
                    trace = p.split("=", 1)[1]
                    break
        if "files=" in line and "tiers=" in line:
            for p in line.split():
                if p.startswith("files="):
                    files = p.split("=", 1)[1]
                    break
        if "ESCALAT" in line or "BLOCKED" in line or "CORE_GATE" in line:
            action = line.strip()[:80]

    # Check for various outcomes
    if "FSM -> ready" in output:
        status = "✅ Выполнено"
    elif "BATCH GATE FAILED" in output:
        status = "❌ Gate failed"
    elif "EXECUTOR FAILED" in output:
        status = "❌ Executor failed"
    elif "COLLECT FAILED" in output:
        status = "❌ Collect failed"
    elif "ESCALAT" in output:
        status = "⚠️ Эскалация (нужен ответ)"
    elif "CORE_GATE" in output or "CORE RISK" in output:
        status = "🔴 CORE — нужен аудит"
    elif "BLOCKED" in output:
        status = "🚫 Заблокировано"
    elif "lock_busy" in output:
        status = "🔒 Другой процесс работает"
    else:
        status = "❓ Проверь вручную"

    return (
        f"{status}\n\n"
        f"📌 Задача: {task[:150]}\n"
        f"🎯 Risk: {risk}\n"
        f"⚙️ Action: {action}\n"
        f"📦 Files: {files}\n"
        f"🚦 Gate: {gate}\n"
        f"🔗 Trace: {trace}"
    )


def main():
    token = _load_token()
    logger.info("Starting strojka Telegram bot...")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is polling. Send /start in Telegram to register.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
