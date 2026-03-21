"""
Backoffice Rate Limiter. Phase 6.10 — INV-RATE.

DB-backed: counts employee actions in the last RATE_WINDOW_SECONDS.
Reads from employee_actions_log (SELECT only — no write here).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .backoffice_models import DEFAULT_RATE_LIMITS, RATE_WINDOW_SECONDS, RiskLevel


@dataclass(frozen=True)
class RateLimitResult:
    allowed:       bool
    current_count: int
    limit:         int
    risk_level:    str
    employee_id:   str
    intent_type:   str


def _resolve_limit(risk_level: RiskLevel) -> int:
    """
    Returns the configured per-hour limit for this risk level.
    Reads env overrides:
      BACKOFFICE_RATE_LIMIT_LOW_PER_HOUR
      BACKOFFICE_RATE_LIMIT_MEDIUM_PER_HOUR
      BACKOFFICE_RATE_LIMIT_HIGH_PER_HOUR
    Falls back to DEFAULT_RATE_LIMITS.
    """
    env_key = f"BACKOFFICE_RATE_LIMIT_{risk_level.value}_PER_HOUR"
    raw = (os.getenv(env_key) or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return DEFAULT_RATE_LIMITS[risk_level]


def check_rate_limit(
    db_conn: Any,
    *,
    employee_id: str,
    intent_type: str,
    risk_level: RiskLevel,
) -> RateLimitResult:
    """
    Check whether employee has exceeded their rate limit for this intent.

    Counts rows in employee_actions_log with:
      - employee_id = employee_id
      - intent_type = intent_type
      - created_at  > NOW() - INTERVAL (RATE_WINDOW_SECONDS seconds)

    Returns RateLimitResult. Does NOT raise — caller (guardian) raises
    GuardianVeto if result.allowed is False.
    """
    limit = _resolve_limit(risk_level)

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM employee_actions_log
            WHERE employee_id = %s
              AND intent_type  = %s
              AND created_at  > NOW() - INTERVAL '1 second' * %s
            """,
            (employee_id, intent_type, RATE_WINDOW_SECONDS),
        )
        row = cursor.fetchone()
        current = int(row[0]) if row else 0
    finally:
        cursor.close()

    return RateLimitResult(
        allowed=current < limit,
        current_count=current,
        limit=limit,
        risk_level=risk_level.value,
        employee_id=employee_id,
        intent_type=intent_type,
    )
