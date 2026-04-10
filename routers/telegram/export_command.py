"""routers/telegram/export_command.py — /export command handler.

Sends the most recently generated InSales-ready CSV catalog export to the
requesting Telegram user.

Tier-3 module: read-only, no writes to any protected table.
Requires: trace_id (from payload), idempotency_key (per send operation).
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

# Canonical output path produced by export_pipeline.py / local_catalog_refresh.py
_EXPORT_CSV_RELPATH = "export/insales_export.csv"


def _locate_csv(root: Path) -> Path:
    """Return absolute path to the catalog CSV, or raise FileNotFoundError."""
    csv_path = root / _EXPORT_CSV_RELPATH
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Catalog CSV not found at {csv_path}. "
            "Run export_pipeline / local_catalog_refresh first."
        )
    return csv_path


async def handle_export(
    bot,
    chat_id: int,
    *,
    trace_id: str,
    root: Path | None = None,
) -> Path:
    """Handle /export: locate catalog CSV and send it to chat_id.

    Parameters
    ----------
    bot:
        Telegram Bot instance (must expose async send_document()).
    chat_id:
        Destination chat / user id.
    trace_id:
        Propagated trace identifier from the triggering payload.
    root:
        Project root directory. Defaults to three levels up from this file.

    Returns
    -------
    Path
        The CSV file that was sent.

    Raises
    ------
    FileNotFoundError
        If the catalog CSV has not been generated yet.
    Exception
        Re-raised on any Telegram API failure.
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent.parent

    idempotency_key = str(uuid.uuid4())

    log.info(
        "export_command start",
        extra={
            "trace_id": trace_id,
            "idempotency_key": idempotency_key,
            "chat_id": chat_id,
        },
    )

    csv_path = _locate_csv(root)

    log.info(
        "export_command sending",
        extra={
            "trace_id": trace_id,
            "idempotency_key": idempotency_key,
            "csv_path": str(csv_path),
        },
    )

    with open(csv_path, "rb") as fh:
        await bot.send_document(
            chat_id=chat_id,
            document=fh,
            filename=csv_path.name,
            caption=f"Каталог (trace_id={trace_id})",
        )

    log.info(
        "export_command done",
        extra={
            "trace_id": trace_id,
            "idempotency_key": idempotency_key,
            "outcome": "sent",
        },
    )

    return csv_path


async def cmd_export(update, context) -> None:
    """python-telegram-bot CommandHandler entry point for /export."""
    trace_id = f"tg_export:{update.update_id}"
    chat_id = update.effective_chat.id

    try:
        await handle_export(bot=context.bot, chat_id=chat_id, trace_id=trace_id)
        await update.message.reply_text("Экспорт отправлен.")
    except FileNotFoundError as exc:
        log.error(
            "export_command file_not_found",
            extra={
                "trace_id": trace_id,
                "error_class": "PERMANENT",
                "severity": "ERROR",
                "retriable": False,
                "detail": str(exc),
            },
        )
        await update.message.reply_text(
            "Файл экспорта не найден. Запустите pipeline сначала."
        )
        raise
    except Exception as exc:
        log.error(
            "export_command failed",
            extra={
                "trace_id": trace_id,
                "error_class": "TRANSIENT",
                "severity": "ERROR",
                "retriable": True,
                "detail": str(exc),
            },
        )
        raise
