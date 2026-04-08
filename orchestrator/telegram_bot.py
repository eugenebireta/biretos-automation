"""
telegram_bot.py — Telegram bridge for ИИ-стройка.

Listens for messages, runs strojka.py, sends results back.

PC console: full technical output in real-time.
Telegram: only human-friendly summaries + escalation questions.

Usage:
    python orchestrator/telegram_bot.py

Commands:
    Стройка: <задача>     — запустить задачу
    ок / да / нет         — ответ на эскалацию
    /status               — текущий статус
    /help                 — справка

Token: loaded from orchestrator/.env.telegram (gitignored).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
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

# Console logging — full technical detail on PC
logging.basicConfig(
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
    stream=sys.stdout,
)
# Suppress noisy httpx polling logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

log = logging.getLogger("strojka")

OWNER_CHAT_ID: int | None = None

# ── Console helpers ─────────────────────────────────────────────────────

def _pc(msg: str) -> None:
    """Print to PC console with timestamp."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── Token / Auth ────────────────────────────────────────────────────────

def _load_token() -> str:
    env_path = ORCH_DIR / ".env.telegram"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not found")
    return token


def _is_owner(update: Update) -> bool:
    global OWNER_CHAT_ID
    if OWNER_CHAT_ID is None:
        return True
    return update.effective_chat.id == OWNER_CHAT_ID


def _load_env() -> dict:
    """Load API keys from .env.auditors for subprocess."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env_auditors = ROOT / "auditor_system" / "config" / ".env.auditors"
    if env_auditors.exists():
        for line in env_auditors.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


# ── Telegram commands ───────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global OWNER_CHAT_ID
    if OWNER_CHAT_ID is None:
        OWNER_CHAT_ID = update.effective_chat.id
        _pc(f"Owner registered: {update.effective_user.first_name} (chat_id={OWNER_CHAT_ID})")
    await update.message.reply_text(
        "ИИ-Стройка на связи.\n\n"
        "Напиши задачу, например:\n"
        "  Стройка: добавить тесты для batch gate\n\n"
        "Команды:\n"
        "  /status — текущий статус\n"
        "  /help — справка"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    await update.message.reply_text(
        "Стройка: <задача> — запустить\n"
        "ок / да — одобрить эскалацию\n"
        "нет — отклонить\n"
        "/status — статус манифеста\n"
        "/help — эта справка"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    if not MANIFEST_PATH.exists():
        await update.message.reply_text("Стройка не запущена.")
        return
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    state = m.get("fsm_state", "?")
    task = m.get("current_task_id", "?")
    goal = (m.get("current_sprint_goal") or "?")[:200]
    verdict = m.get("last_verdict") or "—"
    await update.message.reply_text(
        f"Состояние: {state}\n"
        f"Задача: {task}\n"
        f"Цель: {goal}\n"
        f"Вердикт: {verdict}"
    )


# ── Owner reply to escalation ──────────────────────────────────────────

async def _handle_owner_reply(update: Update, text: str) -> bool:
    """Handle 'ок/да/нет' replies to pending escalations. Returns True if handled."""
    if not MANIFEST_PATH.exists():
        return False
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    state = m.get("fsm_state", "")

    if state not in ("awaiting_owner_reply", "error"):
        return False

    lower = text.lower().strip()
    if lower in ("ок", "ok", "да", "yes", "го", "давай"):
        m["fsm_state"] = "ready"
        m["last_verdict"] = None
        m["updated_at"] = datetime.now(timezone.utc).isoformat()
        MANIFEST_PATH.write_text(
            json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _pc(f"Owner approved escalation → fsm_state=ready")
        await update.message.reply_text("Принято. Стройка продолжит при следующем запуске.")
        return True
    elif lower in ("нет", "no", "стоп", "stop"):
        _pc(f"Owner rejected escalation — fsm stays at {state}")
        await update.message.reply_text("Понял. Задача остаётся на паузе.")
        return True

    return False


# ── Main message handler ───────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    # Check for escalation reply first
    if await _handle_owner_reply(update, text):
        return

    # Check for strojka trigger
    task_text = None
    for prefix in ("Стройка:", "стройка:", "Strojka:", "strojka:"):
        if text.startswith(prefix):
            task_text = text[len(prefix):].strip()
            break

    if task_text is None:
        return  # Not a command, ignore

    if not task_text:
        await update.message.reply_text("Напиши задачу после 'Стройка:'")
        return

    # ── Run strojka ─────────────────────────────────────────────────
    _pc(f"")
    _pc(f"{'='*60}")
    _pc(f"ЗАДАЧА: {task_text}")
    _pc(f"{'='*60}")

    await update.message.reply_text(f"Принял. Работаю...")

    try:
        env = _load_env()

        # Run strojka — stream output to PC console in real-time
        proc = subprocess.Popen(
            [sys.executable, str(ORCH_DIR / "strojka.py"), task_text],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            env=env,
        )

        full_output = []
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                _pc(f"  {line}")
                full_output.append(line)

        proc.wait(timeout=600)
        output = "\n".join(full_output)

        _pc(f"Exit code: {proc.returncode}")
        _pc(f"{'='*60}")

        # ── Send human-friendly result to Telegram ──────────────────
        tg_msg = _build_telegram_message(output, task_text)
        await update.message.reply_text(tg_msg)

    except subprocess.TimeoutExpired:
        proc.kill()
        _pc("TIMEOUT — killed after 600s")
        await update.message.reply_text("Не уложилась в 10 минут. Посмотри на ПК.")
    except Exception as e:
        _pc(f"ERROR: {e}")
        await update.message.reply_text(f"Ошибка: {e}")


def _build_telegram_message(output: str, task: str) -> str:
    """Build human-friendly Telegram message — no technical jargon."""

    # Determine outcome
    if "FSM -> ready" in output:
        # Success — tell what was done
        files_changed = "?"
        for line in output.splitlines():
            if "files=" in line and "tiers=" in line:
                for p in line.split():
                    if p.startswith("files="):
                        files_changed = p.split("=", 1)[1]
        return (
            f"Готово.\n\n"
            f"Задача: {task[:200]}\n"
            f"Изменено файлов: {files_changed}\n"
            f"Проверки пройдены."
        )

    if "BATCH GATE FAILED" in output:
        reason = ""
        for line in output.splitlines():
            if "Reason:" in line:
                reason = line.split("Reason:", 1)[1].strip()
        return (
            f"Задача выполнена, но проверка не прошла.\n\n"
            f"Причина: {reason[:300]}\n\n"
            f"Что делать: посмотри детали на ПК и ответь 'ок' чтобы продолжить."
        )

    if "EXECUTOR FAILED" in output or "COLLECT FAILED" in output:
        return (
            f"Ошибка выполнения.\n\n"
            f"Задача: {task[:200]}\n\n"
            f"Детали на ПК. Ответь 'ок' когда починишь."
        )

    if "ESCALAT" in output:
        # Extract rationale
        rationale = ""
        for line in output.splitlines():
            if "Rationale:" in line:
                rationale = line.split("Rationale:", 1)[1].strip()
        return (
            f"Нужно твоё решение.\n\n"
            f"Задача: {task[:200]}\n"
            f"Причина: {rationale[:300]}\n\n"
            f"Ответь 'ок' чтобы продолжить или 'нет' чтобы отменить."
        )

    if "CORE_GATE" in output or "CORE RISK" in output:
        return (
            f"Задача затрагивает ядро системы. Нужен полный аудит.\n\n"
            f"Задача: {task[:200]}\n\n"
            f"Детали на ПК."
        )

    if "BLOCKED" in output:
        rationale = ""
        for line in output.splitlines():
            if "Rationale:" in line:
                rationale = line.split("Rationale:", 1)[1].strip()
        return (
            f"Заблокировано.\n\n"
            f"Причина: {rationale[:300]}\n\n"
            f"Детали на ПК. Ответь 'ок' когда будет готово."
        )

    if "lock_busy" in output:
        return "Другой процесс уже работает. Подожди."

    # Unknown outcome
    return (
        f"Стройка завершилась.\n\n"
        f"Задача: {task[:200]}\n\n"
        f"Посмотри результат на ПК."
    )


# ── Entry point ─────────────────────────────────────────────────────────

def main():
    token = _load_token()

    print(flush=True)
    print("=" * 60, flush=True)
    print("  ИИ-СТРОЙКА — Telegram Bot", flush=True)
    print("  @bireta_code_bot", flush=True)
    print("=" * 60, flush=True)
    print(flush=True)
    _pc("Бот запущен. Ожидаю команды из Telegram...")
    _pc("Ctrl+C чтобы остановить.")
    print(flush=True)

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
