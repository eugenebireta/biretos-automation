from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import requests
from psycopg2.pool import SimpleConnectionPool

from config import get_config
from domain import observability_service as observability
from ru_worker.lib_integrations import log_event


TERMINAL_STATES = ("completed", "cancelled", "failed")
SEVERITY_LEVELS = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}
SEVERITY_EMOJI = {"CRITICAL": "\U0001f534", "WARNING": "\u26a0\ufe0f", "INFO": "\u2139\ufe0f"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _build_pool() -> SimpleConnectionPool:
    config = get_config()
    db_pool_min = _env_int("ALERT_DB_POOL_MIN", 1)
    db_pool_max = max(db_pool_min, _env_int("ALERT_DB_POOL_MAX", 2))
    return SimpleConnectionPool(
        minconn=db_pool_min,
        maxconn=db_pool_max,
        host=config.postgres_host or "localhost",
        port=config.postgres_port or 5432,
        dbname=config.postgres_db or "biretos_automation",
        user=config.postgres_user or "biretos_user",
        password=config.postgres_password,
    )


def _run_select(conn, query: str, params=()) -> List[tuple]:
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        return list(cursor.fetchall())
    finally:
        cursor.close()


def _scan_active_orders(conn, *, limit: int) -> List[UUID]:
    rows = _run_select(
        conn,
        """
        SELECT order_id
        FROM order_ledger
        WHERE state NOT IN %s
        ORDER BY updated_at DESC NULLS LAST
        LIMIT %s
        """,
        (TERMINAL_STATES, limit),
    )
    return [UUID(str(row[0])) for row in rows]


def _build_cooldown_key(check_code: str, entity_id: str, now_ts: datetime) -> str:
    bucket = now_ts.strftime("%Y-%m-%d-%H")
    return f"{check_code}:{entity_id}:{bucket}"


def _short_details(details: Any) -> str:
    raw = json.dumps(details or {}, ensure_ascii=False, sort_keys=True)
    if len(raw) <= 220:
        return raw
    return raw[:217] + "..."


def _format_alert_message(verdict: Dict[str, Any], *, trace_id: str) -> str:
    check_name = str(verdict.get("check_name") or "unknown")
    verdict_name = str(verdict.get("verdict") or "UNKNOWN")
    entity_type = str(verdict.get("entity_type") or "entity")
    entity_id = str(verdict.get("entity_id") or "unknown")
    severity = str(verdict.get("severity") or "WARNING").upper()
    details = _short_details(verdict.get("details"))
    emoji = SEVERITY_EMOJI.get(severity, "")
    return (
        f"{emoji} {severity} IC/RC Alert: {check_name} = {verdict_name}\n"
        f"Entity: {entity_type} {entity_id}\n"
        f"Severity: {severity}\n"
        f"Details: {details}\n"
        f"Trace: {trace_id}"
    )


def _is_alertable_verdict(verdict: Dict[str, Any]) -> bool:
    check_name = str(verdict.get("check_name") or "")
    verdict_name = str(verdict.get("verdict") or "")
    return verdict_name in {"FAIL", "STALE"} and (
        check_name.startswith("IC-") or check_name.startswith("RC-")
    )


def _should_send(severity: str, min_severity: str) -> bool:
    severity_key = severity.upper()
    min_key = min_severity.upper()
    return SEVERITY_LEVELS.get(severity_key, 1) >= SEVERITY_LEVELS.get(min_key, 1)


def _resolve_chat_id(
    severity: str,
    *,
    default_chat_id: Optional[int],
    critical_chat_id: Optional[int],
    warning_chat_id: Optional[int],
) -> Optional[int]:
    severity_key = severity.upper()
    if severity_key == "CRITICAL" and critical_chat_id is not None:
        return critical_chat_id
    if severity_key == "WARNING" and warning_chat_id is not None:
        return warning_chat_id
    return default_chat_id


def _reserve_alert_row(
    conn,
    *,
    check_code: str,
    entity_id: str,
    severity: str,
    verdict_name: str,
    message_text: str,
    chat_id: int,
    trace_id: str,
    cooldown_key: str,
) -> Optional[str]:
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO alert_telegram_log (
                check_code,
                entity_id,
                severity,
                verdict,
                message_text,
                chat_id,
                trace_id,
                cooldown_key
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::uuid, %s)
            ON CONFLICT (cooldown_key) DO NOTHING
            RETURNING id
            """,
            (
                check_code,
                entity_id,
                severity,
                verdict_name,
                message_text,
                int(chat_id),
                trace_id,
                cooldown_key,
            ),
        )
        row = cursor.fetchone()
        return str(row[0]) if row else None
    finally:
        cursor.close()


def _mark_alert_sent(conn, *, alert_id: str, telegram_message_id: Optional[int]) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE alert_telegram_log
            SET telegram_message_id = %s,
                sent_at = NOW()
            WHERE id = %s::uuid
            """,
            (telegram_message_id, alert_id),
        )
    finally:
        cursor.close()


def _drop_reserved_alert(conn, *, alert_id: str) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM alert_telegram_log WHERE id = %s::uuid",
            (alert_id,),
        )
    finally:
        cursor.close()


def _send_telegram_message(*, bot_token: str, chat_id: int, text: str) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    body = response.json()
    if not body.get("ok", False):
        error_code = body.get("error_code", "unknown")
        description = body.get("description", "Unknown Telegram API error")
        return {"ok": False, "error": f"Telegram API error {error_code}: {description}"}
    message_id = body.get("result", {}).get("message_id")
    try:
        parsed_message_id = int(message_id) if message_id is not None else None
    except (TypeError, ValueError):
        parsed_message_id = None
    return {"ok": True, "message_id": parsed_message_id}


def _deliver_verdict_alert(
    conn,
    verdict: Dict[str, Any],
    *,
    chat_id: int,
    bot_token: str,
    trace_id: str,
    now_ts: datetime,
) -> Dict[str, Any]:
    check_code = str(verdict.get("check_name") or "unknown")
    entity_id = str(verdict.get("entity_id") or "unknown")
    severity = str(verdict.get("severity") or "WARNING")
    verdict_name = str(verdict.get("verdict") or "UNKNOWN")
    cooldown_key = _build_cooldown_key(check_code, entity_id, now_ts)
    message_text = _format_alert_message(verdict, trace_id=trace_id)

    try:
        alert_id = _reserve_alert_row(
            conn,
            check_code=check_code,
            entity_id=entity_id,
            severity=severity,
            verdict_name=verdict_name,
            message_text=message_text,
            chat_id=chat_id,
            trace_id=trace_id,
            cooldown_key=cooldown_key,
        )
        if not alert_id:
            return {"status": "deduped", "cooldown_key": cooldown_key}

        try:
            send_result = _send_telegram_message(bot_token=bot_token, chat_id=chat_id, text=message_text)
        except Exception as exc:
            send_result = {"ok": False, "error": str(exc)}
        if send_result.get("ok"):
            _mark_alert_sent(
                conn,
                alert_id=alert_id,
                telegram_message_id=send_result.get("message_id"),
            )
            conn.commit()
            return {
                "status": "sent",
                "cooldown_key": cooldown_key,
                "alert_id": alert_id,
                "telegram_message_id": send_result.get("message_id"),
            }

        _drop_reserved_alert(conn, alert_id=alert_id)
        conn.commit()
        return {
            "status": "send_error",
            "cooldown_key": cooldown_key,
            "alert_id": alert_id,
            "error": send_result.get("error", "unknown_error"),
        }
    except Exception as exc:
        if hasattr(conn, "rollback"):
            conn.rollback()
        log_event(
            "alert_notifier_delivery_error",
            {
                "error": str(exc),
                "check_code": check_code,
                "entity_id": entity_id,
                "trace_id": trace_id,
            },
        )
        return {"status": "internal_error", "error": str(exc), "cooldown_key": cooldown_key}


def _collect_global_verdicts(conn, *, trace_id: str, now_ts: datetime) -> List[Dict[str, Any]]:
    return [
        observability.check_zombie_reservations(conn, trace_id=trace_id, now_ts=now_ts),
        observability.check_orphan_payment_transactions(conn, trace_id=trace_id, now_ts=now_ts),
    ]


def _run_cycle(
    pool: SimpleConnectionPool,
    *,
    bot_token: str,
    default_chat_id: Optional[int],
    critical_chat_id: Optional[int],
    warning_chat_id: Optional[int],
    min_severity: str,
) -> None:
    conn = pool.getconn()
    try:
        conn.autocommit = False
        trace_id = str(uuid4())
        now_ts = datetime.now(timezone.utc)
        order_limit = _env_int("ALERT_ACTIVE_ORDER_LIMIT", 100)

        scanned_orders = 0
        candidate_verdicts = 0
        sent_count = 0
        deduped_count = 0
        error_count = 0
        filtered_count = 0

        for order_id in _scan_active_orders(conn, limit=order_limit):
            scanned_orders += 1
            verdicts = observability.collect_order_invariant_verdicts(
                conn,
                order_id=order_id,
                trace_id=trace_id,
                now_ts=now_ts,
            )
            for verdict in verdicts:
                if not _is_alertable_verdict(verdict):
                    continue
                severity = str(verdict.get("severity") or "WARNING")
                if not _should_send(severity, min_severity):
                    filtered_count += 1
                    continue
                target_chat_id = _resolve_chat_id(
                    severity,
                    default_chat_id=default_chat_id,
                    critical_chat_id=critical_chat_id,
                    warning_chat_id=warning_chat_id,
                )
                if target_chat_id is None:
                    filtered_count += 1
                    continue
                candidate_verdicts += 1
                result = _deliver_verdict_alert(
                    conn,
                    verdict,
                    chat_id=target_chat_id,
                    bot_token=bot_token,
                    trace_id=trace_id,
                    now_ts=now_ts,
                )
                if result["status"] == "sent":
                    sent_count += 1
                elif result["status"] == "deduped":
                    deduped_count += 1
                else:
                    error_count += 1

        for verdict in _collect_global_verdicts(conn, trace_id=trace_id, now_ts=now_ts):
            if not _is_alertable_verdict(verdict):
                continue
            severity = str(verdict.get("severity") or "WARNING")
            if not _should_send(severity, min_severity):
                filtered_count += 1
                continue
            target_chat_id = _resolve_chat_id(
                severity,
                default_chat_id=default_chat_id,
                critical_chat_id=critical_chat_id,
                warning_chat_id=warning_chat_id,
            )
            if target_chat_id is None:
                filtered_count += 1
                continue
            candidate_verdicts += 1
            result = _deliver_verdict_alert(
                conn,
                verdict,
                chat_id=target_chat_id,
                bot_token=bot_token,
                trace_id=trace_id,
                now_ts=now_ts,
            )
            if result["status"] == "sent":
                sent_count += 1
            elif result["status"] == "deduped":
                deduped_count += 1
            else:
                error_count += 1

        log_event(
            "alert_notifier_cycle_summary",
            {
                "trace_id": trace_id,
                "active_orders_scanned": scanned_orders,
                "candidate_verdicts": candidate_verdicts,
                "alerts_sent": sent_count,
                "alerts_deduped": deduped_count,
                "alerts_error": error_count,
                "alerts_filtered": filtered_count,
                "order_limit": order_limit,
            },
        )
    finally:
        pool.putconn(conn)


def main() -> None:
    config = get_config()
    default_chat_id = config.alert_telegram_chat_id
    critical_chat_id = config.alert_chat_id_critical
    warning_chat_id = config.alert_chat_id_warning
    bot_token = config.telegram_bot_token or ""
    min_severity = (config.alert_min_severity or "WARNING").upper()
    interval_sec = max(1, int(config.alert_poll_interval or 300))
    has_any_chat_id = (
        default_chat_id is not None
        or critical_chat_id is not None
        or warning_chat_id is not None
    )

    if not bot_token or not has_any_chat_id:
        log_event(
            "alert_notifier_disabled",
            {
                "reason": "missing_telegram_config",
                "has_bot_token": bool(bot_token),
                "has_any_chat_id": has_any_chat_id,
            },
        )
        return

    pool = _build_pool()
    log_event(
        "alert_notifier_started",
        {
            "interval_sec": interval_sec,
            "active_order_limit": _env_int("ALERT_ACTIVE_ORDER_LIMIT", 100),
        },
    )
    try:
        while True:
            started = time.time()
            try:
                _run_cycle(
                    pool,
                    bot_token=bot_token,
                    default_chat_id=default_chat_id,
                    critical_chat_id=critical_chat_id,
                    warning_chat_id=warning_chat_id,
                    min_severity=min_severity,
                )
            except Exception as exc:
                log_event("alert_notifier_cycle_error", {"error": str(exc)})

            elapsed = time.time() - started
            delay = max(0.0, interval_sec - elapsed)
            time.sleep(delay)
    finally:
        pool.closeall()


if __name__ == "__main__":
    main()
