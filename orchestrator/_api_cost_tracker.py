"""Shared API cost tracker for all Anthropic API calls.

Usage (SDK pattern):
    from orchestrator._api_cost_tracker import log_api_call
    resp = client.messages.create(model="claude-haiku-4-5-20251001", ...)
    log_api_call(__file__, "claude-haiku-4-5-20251001", resp.usage)

Usage (HTTP pattern):
    r = requests.post("https://api.anthropic.com/v1/messages", json=body, ...)
    data = r.json()
    log_api_call(__file__, model, data.get("usage", {}))

Writes one JSONL line per call to logs/api_costs.jsonl. Failure to log never
raises — tracker is best-effort instrumentation.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

# Prices in USD per 1M tokens (Anthropic standard tier, 2026-04).
# Includes the models actually seen in usage CSV for this project.
PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-6":               {"in": 15.0,  "out": 75.0, "cache_w_5m": 18.75, "cache_r": 1.50},
    "claude-opus-4-5-20251101":      {"in": 15.0,  "out": 75.0, "cache_w_5m": 18.75, "cache_r": 1.50},
    "claude-sonnet-4-6":             {"in": 3.0,   "out": 15.0, "cache_w_5m": 3.75,  "cache_r": 0.30},
    "claude-sonnet-4-5-20250929":    {"in": 3.0,   "out": 15.0, "cache_w_5m": 3.75,  "cache_r": 0.30},
    "claude-sonnet-4-20250514":      {"in": 3.0,   "out": 15.0, "cache_w_5m": 3.75,  "cache_r": 0.30},
    "claude-haiku-4-5-20251001":     {"in": 1.0,   "out": 5.0,  "cache_w_5m": 1.25,  "cache_r": 0.10},
}

_ROOT = Path(__file__).resolve().parent.parent
_LOG_PATH = _ROOT / "logs" / "api_costs.jsonl"


def _coerce_usage(usage: Any) -> dict[str, int]:
    """Accept either Anthropic SDK Usage object or dict (HTTP response)."""
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    # SDK Usage object — extract fields via getattr, default 0
    out = {}
    for field in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        val = getattr(usage, field, None)
        if val is not None:
            out[field] = val
    return out


def _compute_cost(model: str, usage: dict[str, int]) -> float:
    p = PRICING.get(model)
    if p is None:
        return 0.0
    in_tok = usage.get("input_tokens", 0) or 0
    out_tok = usage.get("output_tokens", 0) or 0
    cache_r = usage.get("cache_read_input_tokens", 0) or 0
    cache_w = usage.get("cache_creation_input_tokens", 0) or 0
    return (
        in_tok * p["in"]
        + out_tok * p["out"]
        + cache_r * p["cache_r"]
        + cache_w * p["cache_w_5m"]
    ) / 1_000_000.0


def _script_tag(script_path: str) -> str:
    """Normalize __file__ into a stable short tag (e.g. 'scripts/pipeline_v2/phase1_recon.py')."""
    try:
        p = Path(script_path).resolve()
        return str(p.relative_to(_ROOT)).replace("\\", "/")
    except Exception:
        return os.path.basename(script_path)


def log_api_call(
    script: str,
    model: str,
    usage: Any,
    *,
    duration_ms: int | None = None,
    trace_id: str | None = None,
    extra: dict | None = None,
) -> None:
    """Append one JSONL line describing an Anthropic API call.

    Never raises — if logging fails, prints to stderr and returns.
    """
    try:
        u = _coerce_usage(usage)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "script": _script_tag(script),
            "model": model,
            "in_tokens": u.get("input_tokens", 0) or 0,
            "out_tokens": u.get("output_tokens", 0) or 0,
            "cache_read_tokens": u.get("cache_read_input_tokens", 0) or 0,
            "cache_write_tokens": u.get("cache_creation_input_tokens", 0) or 0,
            "cost_usd": round(_compute_cost(model, u), 6),
        }
        if duration_ms is not None:
            record["duration_ms"] = duration_ms
        if trace_id:
            record["trace_id"] = trace_id
        if extra:
            record["extra"] = extra
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[api_cost_tracker] log failed: {e}", file=sys.stderr)


class timed:
    """Context manager for measuring duration around an API call.

    Usage:
        with timed() as t:
            resp = client.messages.create(...)
        log_api_call(__file__, model, resp.usage, duration_ms=t.ms)
    """
    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *_):
        self.ms = int((time.perf_counter() - self._t0) * 1000)
