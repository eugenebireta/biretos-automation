"""
Alert Dispatcher — Phase 4 Alerting (Tier-3 side-effect module).

Responsibilities:
  4.1  IC/RC violation alerts → Telegram
  4.2  FSM staleness + zombie reservation alerts → Telegram
  4.3  Severity-based routing: CRITICAL/HIGH/WARNING → alert_chat,
       INFO/LOW → default_chat
  4.4  Dedicated Telegram alert chat via TELEGRAM_ALERT_CHAT_ID

Architecture constraints (CLAUDE.md):
  - Does NOT import from domain.reconciliation_* (absolute prohibition)
  - Does NOT write to reconciliation_* tables
  - Accepts pre-fetched alert dicts; caller is responsible for DB read & ack
  - No secrets in structured log output
  - error_class (TRANSIENT/PERMANENT) + severity + retriable on every exception
  - _send_fn injectable for deterministic testing (no live API in tests)
  - trace_id carried from alert["sweep_trace_id"]
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

import httpx

# ---------------------------------------------------------------------------
# Severity classification
# ---------------------------------------------------------------------------

_CRITICAL_SEVERITIES = frozenset({"CRITICAL", "HIGH"})
_WARNING_SEVERITIES = frozenset({"WARNING", "MEDIUM"})

_SEVERITY_EMOJI: Dict[str, str] = {
    "CRITICAL": "\U0001f534",  # 🔴
    "HIGH": "\U0001f534",      # 🔴
    "WARNING": "\U0001f7e1",   # 🟡
    "MEDIUM": "\U0001f7e1",    # 🟡
    "INFO": "\U0001f535",      # 🔵
    "LOW": "\U0001f535",       # 🔵
}

# ---------------------------------------------------------------------------
# Check-code labels — IC/RC violations (4.1) + FSM/zombie (4.2)
# ---------------------------------------------------------------------------

_CHECK_CODE_LABELS: Dict[str, str] = {
    # Integrity checks
    "IC-001": "Balance mismatch",
    "IC-002": "Payment amount mismatch",
    "IC-003": "Shipment status mismatch",
    # Reconciliation checks
    "RC-1": "Stock snapshot divergence",
    "RC-2": "Shipment cache stale",
    "RC-3": "Stock snapshot rebuild",
    "RC-5": "Document key mismatch",
    "RC-6": "Pending payment overdue",
    "RC-7": "Shipment sync divergence",
    # FSM staleness (4.2)
    "FSM-STALE": "Order stuck in FSM state",
    # Zombie reservations (4.2)
    "FSM-ZOMBIE": "Zombie reservation detected",
    # Batch alert codes
    "L3-A": "Batch alert (L3-A)",
    "L3-D": "Batch alert (L3-D)",
}


def _check_label(check_code: str) -> str:
    return _CHECK_CODE_LABELS.get(check_code, check_code)


# ---------------------------------------------------------------------------
# Pure formatter (4.1 / 4.2)
# ---------------------------------------------------------------------------

def format_alert_message(alert: Dict[str, Any]) -> str:
    """
    Pure function. Returns a Telegram-ready text string for one alert dict.

    Expected alert dict keys (matches reconciliation_alerts row):
        check_code, entity_type, entity_id, severity,
        verdict_snapshot, sweep_trace_id (optional)
    """
    severity = (alert.get("severity") or "WARNING").upper()
    check_code = str(alert.get("check_code") or "UNKNOWN")
    entity_type = str(alert.get("entity_type") or "?")
    entity_id = str(alert.get("entity_id") or "?")
    sweep_trace_id = str(alert.get("sweep_trace_id") or "")

    emoji = _SEVERITY_EMOJI.get(severity, "\u26aa")  # ⚪ fallback
    label = _check_label(check_code)

    verdict = alert.get("verdict_snapshot") or {}
    if isinstance(verdict, str):
        try:
            verdict = json.loads(verdict)
        except Exception:
            verdict = {"raw": verdict}

    lines = [
        f"{emoji} [{severity}] {check_code}: {label}",
        f"Entity: {entity_type} / {entity_id}",
    ]

    # Emit known verdict fields in a stable order
    for key in (
        "reason",
        "expected",
        "actual",
        "diff",
        "stuck_since",
        "age_hours",
        "total_count",
        "raw",
    ):
        if key in verdict:
            lines.append(f"{key}: {verdict[key]}")

    if sweep_trace_id:
        lines.append(f"Sweep: {sweep_trace_id[:8]}\u2026")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pure router (4.3 / 4.4)
# ---------------------------------------------------------------------------

def route_alert(
    severity: str,
    *,
    default_chat_id: int,
    alert_chat_id: Optional[int],
) -> int:
    """
    Pure routing. Returns the chat_id to send the alert to.

    Rules (4.3):
      CRITICAL / HIGH  → alert_chat_id  (dedicated alerts chat, 4.4)
      WARNING / MEDIUM → alert_chat_id
      INFO / LOW       → default_chat_id

    If alert_chat_id is None or 0 (not configured), falls back to default_chat_id.
    """
    sev = (severity or "INFO").upper()
    if alert_chat_id and sev in (_CRITICAL_SEVERITIES | _WARNING_SEVERITIES):
        return alert_chat_id
    return default_chat_id


# ---------------------------------------------------------------------------
# HTTP sender (thin wrapper — replaced by stub in tests)
# ---------------------------------------------------------------------------

def _send_message(*, bot_token: str, chat_id: int, text: str) -> None:
    """
    Sends one Telegram message. Raises httpx.HTTPStatusError on API error.
    Never logs bot_token.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = httpx.post(
        url,
        json={"chat_id": chat_id, "text": text},
        timeout=10.0,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

class AlertDispatchError(Exception):
    """
    Raised when dispatch_alert() cannot deliver the message.

    Attributes follow CLAUDE.md structured error schema:
        error_class:   TRANSIENT | PERMANENT | POLICY_VIOLATION
        severity_level: WARNING | ERROR
        retriable:     bool
        trace_id:      str (from alert["sweep_trace_id"])
    """

    def __init__(
        self,
        message: str,
        *,
        error_class: str,
        severity_level: str,
        retriable: bool,
        trace_id: str,
    ) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.severity_level = severity_level
        self.retriable = retriable
        self.trace_id = trace_id

    def to_log_dict(self) -> Dict[str, Any]:
        """Structured log payload — safe to print (no secrets)."""
        return {
            "error_class": self.error_class,
            "severity": self.severity_level,
            "retriable": self.retriable,
            "trace_id": self.trace_id,
            "message": str(self),
        }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_SendFn = Callable[..., None]


def dispatch_alert(
    alert: Dict[str, Any],
    *,
    bot_token: str,
    default_chat_id: int,
    alert_chat_id: Optional[int] = None,
    _send_fn: Optional[_SendFn] = None,
) -> Dict[str, Any]:
    """
    Dispatch one reconciliation alert to Telegram.

    Parameters:
        alert           Pre-fetched alert dict (keys: check_code, entity_type,
                        entity_id, severity, verdict_snapshot, sweep_trace_id).
        bot_token       Telegram bot token (never logged).
        default_chat_id Fallback / operator chat.
        alert_chat_id   Dedicated alert chat (4.4). None → fall back to default.
        _send_fn        Injectable sender for tests. Default: _send_message.

    Returns:
        {"sent": True, "chat_id": <int>, "check_code": <str>,
         "severity": <str>, "text_preview": <str>}

    Raises:
        AlertDispatchError  with error_class / retriable set appropriately.
    """
    trace_id = str(alert.get("sweep_trace_id") or "")
    severity = (alert.get("severity") or "INFO").upper()

    text = format_alert_message(alert)
    target_chat_id = route_alert(
        severity,
        default_chat_id=default_chat_id,
        alert_chat_id=alert_chat_id,
    )

    send = _send_fn if _send_fn is not None else _send_message

    try:
        send(bot_token=bot_token, chat_id=target_chat_id, text=text)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        # 4xx = bad token / chat_id → PERMANENT; 5xx = server-side → TRANSIENT
        error_class = "PERMANENT" if 400 <= status < 500 else "TRANSIENT"
        raise AlertDispatchError(
            f"Telegram API HTTP {status}",
            error_class=error_class,
            severity_level="ERROR",
            retriable=(error_class == "TRANSIENT"),
            trace_id=trace_id,
        ) from exc
    except Exception as exc:
        raise AlertDispatchError(
            str(exc),
            error_class="TRANSIENT",
            severity_level="ERROR",
            retriable=True,
            trace_id=trace_id,
        ) from exc

    return {
        "sent": True,
        "chat_id": target_chat_id,
        "check_code": alert.get("check_code"),
        "severity": severity,
        "text_preview": text[:80],
    }
