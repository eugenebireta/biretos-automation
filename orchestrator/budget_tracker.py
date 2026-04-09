"""
budget_tracker.py — P7: Track API costs per orchestrator trace.

Records every LLM API call with provider, model, token counts, cost.
Persists to shadow_log/budget_YYYY-MM.jsonl (one line per API call).
Provides:
  - record_call(): append a single API call record
  - get_trace_cost(): total cost for a given trace_id
  - get_daily_summary(): cost/call breakdown for a given date
  - check_budget(): returns whether daily/per-run budget limits exceeded

DNA compliance:
- trace_id: required, links cost to orchestrator run
- idempotency: call_id (trace_id + seq) prevents duplicate records
- no DB, no domain imports
- structured log at decision boundary
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
SHADOW_LOG_DIR = ROOT / "shadow_log"

SCHEMA_VERSION = "budget_record_v1"

# Default pricing per 1M tokens (USD) — conservative estimates
MODEL_PRICING = {
    # Anthropic
    "claude-opus-4-6":       {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6":     {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    # Google
    "gemini-2.5-pro":        {"input": 1.25, "output": 10.0},
    "gemini-2.0-flash":      {"input": 0.10, "output": 0.40},
    # OpenAI
    "gpt-4o":                {"input": 2.50, "output": 10.0},
    "gpt-4o-mini":           {"input": 0.15, "output": 0.60},
}

# Default budget limits
DEFAULT_DAILY_BUDGET_USD = 10.0
DEFAULT_PER_RUN_BUDGET_USD = 2.0


def _log_path(dt: Optional[datetime] = None) -> Path:
    """Return path for current month's budget log."""
    dt = dt or datetime.now(timezone.utc)
    return SHADOW_LOG_DIR / f"budget_{dt.strftime('%Y-%m')}.jsonl"


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Estimate cost in USD for a given model and token counts.

    Returns 0.0 for unknown models (conservative: don't block on unknown pricing).
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        # Try partial match (e.g., "claude-sonnet-4-6" in "claude-sonnet-4-6-20260301")
        for known_model, p in MODEL_PRICING.items():
            if known_model in model or model in known_model:
                pricing = p
                break
    if pricing is None:
        return 0.0

    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)


def record_call(
    trace_id: str,
    provider: str,
    model: str,
    stage: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: Optional[float] = None,
    call_seq: int = 0,
    metadata: Optional[dict] = None,
) -> dict:
    """Record a single API call to the budget log.

    Args:
        trace_id: Orchestrator trace ID.
        provider: API provider (anthropic, google, openai).
        model: Model identifier.
        stage: Pipeline stage (advisor, executor, auditor, experience).
        input_tokens: Input token count.
        output_tokens: Output token count.
        cost_usd: Explicit cost override. If None, estimated from model pricing.
        call_seq: Sequence number within trace (for idempotency).
        metadata: Optional extra fields.

    Returns:
        The record dict that was written.
    """
    if not trace_id:
        raise ValueError("trace_id is required for budget tracking")

    if cost_usd is None:
        cost_usd = estimate_cost(model, input_tokens, output_tokens)

    now = datetime.now(timezone.utc)
    record = {
        "schema_version": SCHEMA_VERSION,
        "ts": now.isoformat(),
        "trace_id": trace_id,
        "idempotency_key": f"budget_{trace_id}_{call_seq}",
        "provider": provider,
        "model": model,
        "stage": stage,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
    }
    if metadata:
        record["metadata"] = metadata

    log_file = _log_path(now)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def _load_records(
    months: int = 1,
    target_date: Optional[date] = None,
) -> list[dict]:
    """Load budget records from JSONL files.

    Args:
        months: How many months of logs to load.
        target_date: If set, filter to records from this date only.
    """
    records = []
    now = datetime.now(timezone.utc)

    for month_offset in range(months):
        month = now.month - month_offset
        year = now.year
        while month <= 0:
            month += 12
            year -= 1
        dt = datetime(year, month, 1, tzinfo=timezone.utc)
        log_file = _log_path(dt)
        if not log_file.exists():
            continue
        for line in log_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("schema_version") != SCHEMA_VERSION:
                continue
            if target_date:
                ts = rec.get("ts", "")
                if not ts.startswith(target_date.isoformat()):
                    continue
            records.append(rec)
    return records


def get_trace_cost(trace_id: str, records: Optional[list[dict]] = None) -> float:
    """Get total cost for a specific trace_id."""
    if records is None:
        records = _load_records()
    return sum(
        r.get("cost_usd", 0.0)
        for r in records
        if r.get("trace_id") == trace_id
    )


def get_daily_summary(
    target_date: Optional[date] = None,
    records: Optional[list[dict]] = None,
) -> dict:
    """Get cost summary for a specific date.

    Returns:
        {
            "date": "2026-04-09",
            "total_cost_usd": 1.23,
            "call_count": 15,
            "by_stage": {"advisor": 0.5, "executor": 0.7, ...},
            "by_model": {"claude-sonnet-4-6": 0.8, ...},
            "by_provider": {"anthropic": 1.0, ...},
        }
    """
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()
    if records is None:
        records = _load_records(months=1, target_date=target_date)

    by_stage: dict[str, float] = {}
    by_model: dict[str, float] = {}
    by_provider: dict[str, float] = {}
    total = 0.0

    for r in records:
        cost = r.get("cost_usd", 0.0)
        total += cost
        stage = r.get("stage", "unknown")
        by_stage[stage] = by_stage.get(stage, 0.0) + cost
        model = r.get("model", "unknown")
        by_model[model] = by_model.get(model, 0.0) + cost
        provider = r.get("provider", "unknown")
        by_provider[provider] = by_provider.get(provider, 0.0) + cost

    return {
        "date": target_date.isoformat(),
        "total_cost_usd": round(total, 6),
        "call_count": len(records),
        "by_stage": {k: round(v, 6) for k, v in by_stage.items()},
        "by_model": {k: round(v, 6) for k, v in by_model.items()},
        "by_provider": {k: round(v, 6) for k, v in by_provider.items()},
    }


def check_budget(
    trace_id: str,
    daily_limit: Optional[float] = None,
    per_run_limit: Optional[float] = None,
    records: Optional[list[dict]] = None,
) -> dict:
    """Check if budget limits are exceeded.

    Returns:
        {
            "within_budget": True/False,
            "daily_cost": 1.23,
            "daily_limit": 10.0,
            "daily_exceeded": False,
            "trace_cost": 0.45,
            "per_run_limit": 2.0,
            "run_exceeded": False,
        }
    """
    if daily_limit is None:
        daily_limit = DEFAULT_DAILY_BUDGET_USD
    if per_run_limit is None:
        per_run_limit = DEFAULT_PER_RUN_BUDGET_USD

    if records is None:
        records = _load_records(months=1)

    today = datetime.now(timezone.utc).date()
    today_records = [
        r for r in records
        if r.get("ts", "").startswith(today.isoformat())
    ]

    daily_cost = sum(r.get("cost_usd", 0.0) for r in today_records)
    trace_cost = sum(
        r.get("cost_usd", 0.0) for r in records
        if r.get("trace_id") == trace_id
    )

    daily_exceeded = daily_cost > daily_limit
    run_exceeded = trace_cost > per_run_limit

    return {
        "within_budget": not (daily_exceeded or run_exceeded),
        "daily_cost": round(daily_cost, 6),
        "daily_limit": daily_limit,
        "daily_exceeded": daily_exceeded,
        "trace_cost": round(trace_cost, 6),
        "per_run_limit": per_run_limit,
        "run_exceeded": run_exceeded,
    }
