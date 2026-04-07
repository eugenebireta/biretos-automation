"""
budget_tracker.py — Daily cost tracking and pre-call gate for Anthropic API.

Reads config from config/budget_guardrails.json.
Persists daily state to shadow_log/budget_tracking.json (atomic write).

Standalone usage:
    python scripts/budget_tracker.py
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = ROOT / "config" / "budget_guardrails.json"
_DEFAULT_STATE_PATH  = ROOT / "shadow_log" / "budget_tracking.json"

_DEFAULT_CONFIG = {
    "hard_stop_usd": 10.0,
    "warning_threshold_usd": 5.0,
    "per_batch_warning_usd": 2.0,
}


class BudgetStatus(str, Enum):
    OK        = "OK"
    WARNING   = "WARNING"
    HARD_STOP = "HARD_STOP"

    @property
    def is_ok(self) -> bool:
        return self in (BudgetStatus.OK, BudgetStatus.WARNING)


class BudgetExceeded(RuntimeError):
    """Raised when daily budget hard-stop is reached."""


@dataclass
class _RunEntry:
    provider:  str
    model:     str
    cost_usd:  float
    timestamp: str


@dataclass
class _DailyState:
    date:           str
    runs:           list[dict] = field(default_factory=list)
    daily_total_usd: float = 0.0


class BudgetTracker:
    """
    Persistent daily budget tracker.

    Thread-safety: atomic write (temp + os.rename) — safe for single-process
    sequential calls. Not safe for concurrent multi-process writes.
    """

    def __init__(
        self,
        config_path: str | Path = _DEFAULT_CONFIG_PATH,
        state_path:  str | Path = _DEFAULT_STATE_PATH,
    ) -> None:
        self._config_path = Path(config_path)
        self._state_path  = Path(state_path)
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._config = self._load_config()

    # ── Config ────────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        if self._config_path.exists():
            try:
                loaded = json.loads(self._config_path.read_text(encoding="utf-8"))
                merged = dict(_DEFAULT_CONFIG)
                merged.update(loaded)
                return merged
            except Exception as exc:
                log.warning(
                    f"budget config load failed ({exc}), using defaults",
                    extra={"error_class": "TRANSIENT", "severity": "WARNING", "retriable": False},
                )
        return dict(_DEFAULT_CONFIG)

    # ── State persistence ─────────────────────────────────────────────────────

    def _load_state(self) -> _DailyState:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not self._state_path.exists():
            return _DailyState(date=today)
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            if raw.get("date") != today:
                # New day — archive previous state alongside, start fresh
                _archive = self._state_path.with_name(
                    f"budget_tracking_{raw.get('date', 'unknown')}.json"
                )
                try:
                    _archive.write_text(
                        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
                    )
                except Exception:
                    pass
                return _DailyState(date=today)
            return _DailyState(
                date=raw["date"],
                runs=raw.get("runs", []),
                daily_total_usd=float(raw.get("daily_total_usd", 0.0)),
            )
        except Exception as exc:
            log.warning(
                f"budget state load failed ({exc}), starting fresh",
                extra={"error_class": "TRANSIENT", "severity": "WARNING", "retriable": False},
            )
            return _DailyState(date=today)

    def _save_state(self, state: _DailyState) -> None:
        payload = {
            "date": state.date,
            "runs": state.runs,
            "daily_total_usd": state.daily_total_usd,
        }
        try:
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self._state_path)
        except Exception as exc:
            log.error(
                json.dumps({
                    "trace_id": "budget_tracker_save",
                    "error_class": "PERMANENT",
                    "severity": "ERROR",
                    "retriable": False,
                    "error": str(exc),
                }, ensure_ascii=False)
            )

    # ── Public API ────────────────────────────────────────────────────────────

    def record_cost(self, provider: str, model: str, cost_usd: float) -> None:
        """Append a cost entry and persist atomically."""
        state = self._load_state()
        entry = {
            "provider":  provider,
            "model":     model,
            "cost_usd":  cost_usd,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        state.runs.append(entry)
        state.daily_total_usd = round(state.daily_total_usd + cost_usd, 6)
        log.info(
            json.dumps({
                "trace_id":       "budget_tracker_record",
                "provider":       provider,
                "model":          model,
                "cost_usd":       cost_usd,
                "daily_total_usd": state.daily_total_usd,
                "outcome":        "recorded",
            }, ensure_ascii=False)
        )
        self._save_state(state)

    def check_budget(self) -> BudgetStatus:
        """Return current budget status without modifying state."""
        total = self.get_daily_total()
        hard_stop = self._config["hard_stop_usd"]
        warning   = self._config["warning_threshold_usd"]

        if total >= hard_stop:
            log.warning(
                json.dumps({
                    "trace_id":  "budget_tracker_check",
                    "daily_total_usd": total,
                    "hard_stop_usd":   hard_stop,
                    "outcome":   "HARD_STOP",
                }, ensure_ascii=False)
            )
            return BudgetStatus.HARD_STOP
        if total >= warning:
            log.warning(
                json.dumps({
                    "trace_id":  "budget_tracker_check",
                    "daily_total_usd": total,
                    "warning_threshold_usd": warning,
                    "outcome":   "WARNING",
                }, ensure_ascii=False)
            )
            return BudgetStatus.WARNING
        return BudgetStatus.OK

    def get_daily_total(self) -> float:
        """Return today's total cost in USD."""
        return self._load_state().daily_total_usd


# Module-level singleton used by providers.py
_default_tracker: Optional[BudgetTracker] = None


def get_default_tracker() -> BudgetTracker:
    """Return (or lazily create) the module-level BudgetTracker."""
    global _default_tracker
    if _default_tracker is None:
        _default_tracker = BudgetTracker()
    return _default_tracker


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.WARNING, stream=sys.stdout)
    tracker = BudgetTracker()
    print(f"Daily total: ${tracker.get_daily_total():.4f}")
    print(f"Status:      {tracker.check_budget()}")
