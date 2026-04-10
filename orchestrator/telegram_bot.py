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

# Add orchestrator to path for task_queue import
if str(ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(ORCH_DIR))

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

def _save_chat_id(chat_id: int) -> None:
    """Persist TELEGRAM_OWNER_CHAT_ID to .env.telegram so notifier can push without bot."""
    env_path = ORCH_DIR / ".env.telegram"
    if not env_path.exists():
        return
    lines = env_path.read_text(encoding="utf-8").splitlines()
    new_lines = [ln for ln in lines if not ln.strip().startswith("TELEGRAM_OWNER_CHAT_ID=")]
    new_lines.append(f"TELEGRAM_OWNER_CHAT_ID={chat_id}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global OWNER_CHAT_ID
    if OWNER_CHAT_ID is None:
        OWNER_CHAT_ID = update.effective_chat.id
        _save_chat_id(OWNER_CHAT_ID)
        _pc(f"Owner registered: {update.effective_user.first_name} (chat_id={OWNER_CHAT_ID})")
    await update.message.reply_text(
        "ИИ-Стройка на связи.\n\n"
        "Быстрый старт:\n"
        "  /enqueue <id> <цель> — добавить задачу в очередь\n"
        "  /queue — посмотреть очередь\n"
        "  /run — запустить один цикл\n\n"
        "Или напрямую:\n"
        "  Стройка: <задача>\n\n"
        "  /help — все команды"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    await update.message.reply_text(
        "Стройка: <задача> — запустить задачу напрямую\n"
        "ок / да — одобрить эскалацию\n"
        "нет — отклонить\n\n"
        "Очередь задач:\n"
        "  /enqueue <id> <цель> [SEMI|CORE] — добавить задачу\n"
        "  /queue — показать очередь\n"
        "  /pop — достать следующую задачу\n"
        "  /confirm — подтвердить SEMI/CORE задачу\n\n"
        "Оркестратор:\n"
        "  /run — запустить один цикл main.py\n"
        "  /status — текущий статус манифеста\n"
        "  /help — эта справка"
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


# ── Queue management commands ──────────────────────────────────────────

async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current task queue."""
    if not _is_owner(update):
        return
    try:
        import task_queue as tq
        queue = sorted(tq.load_queue(), key=tq._sort_key)
        if not queue:
            await update.message.reply_text("Очередь пуста.")
            return
        lines = [f"Очередь ({len(queue)} задач):"]
        for i, t in enumerate(queue, 1):
            risk = t.get("risk_class", "LOW")
            pri = t.get("priority", 0)
            goal = t.get("sprint_goal", "")[:60]
            lines.append(f"{i}. [{risk}] {t.get('task_id','')} (pri={pri})\n   {goal}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_enqueue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/enqueue <task_id> <goal...> [SEMI|CORE]"""
    if not _is_owner(update):
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Использование: /enqueue <task_id> <цель> [SEMI|CORE]\n"
            "Пример: /enqueue fix-auth Починить авторизацию SEMI"
        )
        return
    task_id = args[0]
    # Last arg may be risk class
    risk_class = "LOW"
    goal_parts = args[1:]
    if goal_parts and goal_parts[-1].upper() in ("LOW", "SEMI", "CORE"):
        risk_class = goal_parts[-1].upper()
        goal_parts = goal_parts[:-1]
    sprint_goal = " ".join(goal_parts)
    if not sprint_goal:
        sprint_goal = task_id
    try:
        import task_queue as tq
        entry = tq.enqueue(task_id, sprint_goal, risk_class=risk_class)
        depth = tq.queue_depth()
        await update.message.reply_text(
            f"Добавлено в очередь.\n"
            f"ID: {entry['task_id']}\n"
            f"Риск: {entry['risk_class']}\n"
            f"Цель: {entry['sprint_goal'][:100]}\n"
            f"Позиция в очереди: {depth}"
        )
        _pc(f"Enqueued from Telegram: {task_id} ({risk_class})")
    except ValueError as e:
        await update.message.reply_text(f"Ошибка: {e}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_pop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually dequeue and show next task."""
    if not _is_owner(update):
        return
    try:
        import task_queue as tq
        task = tq.dequeue()
        if task is None:
            await update.message.reply_text("Очередь пуста.")
            return
        remaining = tq.queue_depth()
        await update.message.reply_text(
            f"Задача извлечена.\n"
            f"ID: {task['task_id']}\n"
            f"Риск: {task.get('risk_class','LOW')}\n"
            f"Цель: {task.get('sprint_goal','')[:150]}\n"
            f"Осталось в очереди: {remaining}"
        )
        _pc(f"Popped from queue via Telegram: {task['task_id']}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Confirm SEMI/CORE task — sets manifest to allow auto-advance."""
    if not _is_owner(update):
        return
    if not MANIFEST_PATH.exists():
        await update.message.reply_text("Манифест не найден.")
        return
    try:
        import task_queue as tq
        m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        next_task = tq.peek_next()
        if next_task is None:
            await update.message.reply_text("Очередь пуста — нечего подтверждать.")
            return
        risk = next_task.get("risk_class", "LOW")
        if risk == "LOW":
            await update.message.reply_text(
                f"Задача {next_task['task_id']} уже LOW — подтверждение не нужно. "
                "Используй /run для запуска."
            )
            return
        # Dequeue and set as current task in manifest
        task = tq.dequeue()
        m["current_task_id"] = task["task_id"]
        m["current_sprint_goal"] = task["sprint_goal"]
        m["_last_risk_class"] = task["risk_class"]
        m["attempt_count"] = 0
        m["retry_count"] = 0
        m.pop("_retry_reason", None)
        m["last_verdict"] = None
        m["last_audit_result"] = None
        m["fsm_state"] = "ready"
        m["updated_at"] = datetime.now(timezone.utc).isoformat()
        MANIFEST_PATH.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
        await update.message.reply_text(
            f"Подтверждено.\n"
            f"Задача: {task['task_id']} ({risk})\n"
            f"Цель: {task.get('sprint_goal','')[:150]}\n"
            f"Манифест обновлён. Используй /run для запуска."
        )
        _pc(f"Confirmed {risk} task via Telegram: {task['task_id']}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


_MAX_AUTO_CYCLES = 5  # hard limit to prevent infinite loop


async def _run_cycle(update: Update, _depth: int = 0) -> None:
    """Run one orchestrator cycle and report result in Russian.

    After owner replies (ок/инструкция/решение), this auto-runs main.py
    so the owner doesn't need to manually trigger /run.

    If the resulting state is awaiting_execution, auto-runs again (up to _MAX_AUTO_CYCLES).
    Park states are already notified by _notify_park in main.py.
    """
    if _depth >= _MAX_AUTO_CYCLES:
        await update.message.reply_text(
            f"Остановлено после {_MAX_AUTO_CYCLES} циклов подряд.\n"
            "Посмотри на ПК что происходит. Ответь 'ок' чтобы продолжить."
        )
        return

    if not MANIFEST_PATH.exists():
        return

    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    task_id = m.get("current_task_id", "?")
    if _depth == 0:
        await update.message.reply_text(f"Запускаю... (задача: {task_id})")

    try:
        env = _load_env()
        proc = subprocess.Popen(
            [sys.executable, str(ORCH_DIR / "main.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            env=env,
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                _pc(f"  {line}")
        proc.wait(timeout=600)
    except subprocess.TimeoutExpired:
        proc.kill()
        await update.message.reply_text("Таймаут (10 мин). Посмотри на ПК.")
        return
    except Exception as e:
        await update.message.reply_text(f"Ошибка запуска: {e}")
        return

    # Re-read manifest for result
    if not MANIFEST_PATH.exists():
        await update.message.reply_text("Цикл завершён. Посмотри результат на ПК.")
        return

    m2 = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    new_state = m2.get("fsm_state", "?")
    task_id = m2.get("current_task_id", "?")

    _pc(f"Run cycle complete: state={new_state}, exit={proc.returncode}")

    # Success — task completed
    if new_state == "ready" and m2.get("last_verdict") in ("PASS", "APPROVED", None):
        await update.message.reply_text(
            f"Задача «{task_id}» выполнена успешно.\n"
            f"Тесты прошли, код закоммичен."
        )
        return

    # Awaiting execution — auto-run again (with depth guard)
    if new_state == "awaiting_execution":
        _pc(f"State is awaiting_execution — auto-running cycle {_depth + 1}/{_MAX_AUTO_CYCLES}")
        await _run_cycle(update, _depth + 1)
        return

    # Park states — _notify_park already sent Telegram notification from main.py
    # Just log to console, don't double-message
    park_states = ("awaiting_owner_reply", "error", "blocked", "blocked_by_consensus",
                   "parked_budget_daily", "parked_budget_run", "parked_api_outage")
    if new_state in park_states:
        _pc(f"Parked at {new_state} — notification already sent by _notify_park")
        return

    # Anything else — generic result
    verdict = m2.get("last_verdict") or "—"
    await update.message.reply_text(
        f"Цикл завершён.\n"
        f"Состояние: {new_state}\n"
        f"Вердикт: {verdict}\n"
        f"Задача: {task_id}"
    )


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger one orchestrator cycle (main.py)."""
    if not _is_owner(update):
        return
    if not MANIFEST_PATH.exists():
        await update.message.reply_text("Манифест не найден. Используй /enqueue и /confirm.")
        return
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    state = m.get("fsm_state", "?")
    if state not in ("ready", "awaiting_execution"):
        await update.message.reply_text(
            f"Оркестратор не в состоянии ready (текущий: {state}).\n"
            "Для ошибок/эскалаций используй 'ок' или 'нет'."
        )
        return
    await _run_cycle(update)


# ── Owner reply to escalation ──────────────────────────────────────────

async def _handle_owner_reply(update: Update, text: str) -> bool:
    """Handle owner replies to pending escalations or decisions. Returns True if handled."""
    if not MANIFEST_PATH.exists():
        return False
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    state = m.get("fsm_state", "")
    lower = text.lower().strip()

    # --- Structured A/B/C decision reply ---
    pending = m.get("pending_decision")
    if pending and isinstance(pending, dict):
        options = pending.get("options", {})
        # Match single letter or "A", "b", etc.
        reply_key = text.strip().upper()
        if reply_key in options:
            m["owner_decision"] = reply_key
            m["owner_decision_text"] = options[reply_key]
            m.pop("pending_decision", None)
            m["fsm_state"] = "ready"
            m["updated_at"] = datetime.now(timezone.utc).isoformat()
            MANIFEST_PATH.write_text(
                json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            _pc(f"Owner decision: {reply_key} = {options[reply_key]}")
            await update.message.reply_text(
                f"Принято: {reply_key} — {options[reply_key]}"
            )
            await _run_cycle(update)
            return True

    # --- Simple ок/нет for park states ---
    park_states = ("awaiting_owner_reply", "error", "blocked", "blocked_by_consensus",
                   "parked_budget_daily", "parked_budget_run", "parked_api_outage")
    if state not in park_states:
        return False

    if lower in ("ок", "ok", "да", "yes", "го", "давай", "продолжай"):
        m["fsm_state"] = "ready"
        m["last_verdict"] = None
        m.pop("park_reason", None)
        m["updated_at"] = datetime.now(timezone.utc).isoformat()
        MANIFEST_PATH.write_text(
            json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _pc("Owner approved -> fsm_state=ready")
        await update.message.reply_text("Принято. Продолжаю...")
        await _run_cycle(update)
        return True
    elif lower in ("нет", "no", "стоп", "stop"):
        _pc(f"Owner rejected — fsm stays at {state}")
        await update.message.reply_text("Понял. Задача остаётся на паузе.")
        return True

    # Free-text instruction — save and resume
    if len(text) >= 5:
        m["owner_instruction"] = text
        m["fsm_state"] = "ready"
        m["last_verdict"] = None
        m.pop("park_reason", None)
        m["updated_at"] = datetime.now(timezone.utc).isoformat()
        MANIFEST_PATH.write_text(
            json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _pc(f"Owner instruction saved: {text[:80]}")
        preview = text[:120] + ("…" if len(text) > 120 else "")
        await update.message.reply_text(
            f"Принял инструкцию:\n\"{preview}\"\n\nВыполняю..."
        )
        await _run_cycle(update)
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

    # Check for strojka trigger — ONLY with explicit prefix
    task_text = None
    for prefix in ("Стройка:", "стройка:", "Strojka:", "strojka:"):
        if text.startswith(prefix):
            task_text = text[len(prefix):].strip()
            break

    if task_text is None:
        # Free text without prefix — save as owner message for Claude Code to read
        inbox = ORCH_DIR / "owner_inbox.jsonl"
        entry = json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "text": text,
        }, ensure_ascii=False)
        with open(inbox, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
        _pc(f"Owner message saved: {text[:80]}")
        await update.message.reply_text("Принял. Передам в рабочий чат.")
        return

    if not task_text:
        await update.message.reply_text("Напиши задачу после 'Стройка:'")
        return

    # ── Run strojka ─────────────────────────────────────────────────
    _pc("")
    _pc(f"{'='*60}")
    _pc(f"ЗАДАЧА: {task_text}")
    _pc(f"{'='*60}")

    await update.message.reply_text("Принял. Работаю...")

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
    print("  II-STROIKA -- Telegram Bot", flush=True)
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
    # P4: Queue management
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CommandHandler("enqueue", cmd_enqueue))
    app.add_handler(CommandHandler("pop", cmd_pop))
    app.add_handler(CommandHandler("confirm", cmd_confirm))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
