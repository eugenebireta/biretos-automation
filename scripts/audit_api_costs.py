"""Baseline report for Anthropic API costs, from logs/api_costs.jsonl.

Run:
    python scripts/audit_api_costs.py                  # all time
    python scripts/audit_api_costs.py --days 7         # last 7 days
    python scripts/audit_api_costs.py --script phase1_recon  # filter by script

Shows: $/day totals, per-script breakdown, cache hit-rate per script (for
deciding whether caching would pay off - breakeven >=6 reads/TTL per
feedback_api_caching_math.md).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "logs" / "api_costs.jsonl"


def load_records(days: int | None, script_filter: str | None) -> list[dict]:
    if not LOG_PATH.exists():
        print(f"No log file at {LOG_PATH}. Nothing to report.", file=sys.stderr)
        return []
    cutoff = None
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    records = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if cutoff is not None:
            ts = datetime.fromisoformat(rec["ts"])
            if ts < cutoff:
                continue
        if script_filter and script_filter not in rec.get("script", ""):
            continue
        records.append(rec)
    return records


def report(records: list[dict]) -> None:
    if not records:
        print("No records match filter.")
        return

    # Daily totals
    by_day: dict[str, float] = defaultdict(float)
    by_script: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "cost": 0.0, "in": 0, "out": 0, "cache_r": 0, "cache_w": 0, "models": set()
    })
    by_model: dict[str, float] = defaultdict(float)

    for r in records:
        day = r["ts"][:10]
        by_day[day] += r["cost_usd"]
        s = by_script[r["script"]]
        s["calls"] += 1
        s["cost"] += r["cost_usd"]
        s["in"] += r.get("in_tokens", 0)
        s["out"] += r.get("out_tokens", 0)
        s["cache_r"] += r.get("cache_read_tokens", 0)
        s["cache_w"] += r.get("cache_write_tokens", 0)
        s["models"].add(r["model"])
        by_model[r["model"]] += r["cost_usd"]

    total_cost = sum(by_day.values())
    total_calls = len(records)

    print("=" * 70)
    print(f"API Cost Baseline Report - {total_calls} calls, ${total_cost:.4f} total")
    print("=" * 70)

    print("\n--- Daily totals ---")
    for day in sorted(by_day):
        print(f"  {day}   ${by_day[day]:7.4f}")

    print("\n--- By model ---")
    for m, c in sorted(by_model.items(), key=lambda x: -x[1]):
        print(f"  ${c:7.4f}   {m}")

    print("\n--- By script (top offenders first) ---")
    rows = sorted(by_script.items(), key=lambda x: -x[1]["cost"])
    for script, d in rows:
        cache_total = d["cache_r"] + d["cache_w"]
        cache_hit_rate = (d["cache_r"] / cache_total * 100) if cache_total else 0.0
        models = ",".join(sorted(d["models"]))
        print(
            f"  ${d['cost']:7.4f}  calls={d['calls']:4d}  "
            f"in={d['in']:>8d}  out={d['out']:>6d}  "
            f"cache_r={d['cache_r']:>7d}  cache_w={d['cache_w']:>6d}  "
            f"hit={cache_hit_rate:5.1f}%  {script}  [{models}]"
        )

    print("\n--- Caching assessment ---")
    print("  Breakeven needs >=6 cache reads per cache write within 5-min TTL")
    print("  (cache_write=1.25x input, cache_read=0.1x input, so 1.25 + N*0.1 < N+1 => N > 2.78)")
    for script, d in rows:
        if d["cache_w"] > 0:
            ratio = d["cache_r"] / d["cache_w"]
            verdict = "OK, paying off" if ratio >= 6 else "NET LOSS - disable caching here"
            print(f"  {script}: cache_r/cache_w = {ratio:5.2f}  -> {verdict}")
        elif d["cache_r"] == 0 and d["calls"] > 0:
            # No caching on this script
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None, help="Last N days only")
    ap.add_argument("--script", type=str, default=None, help="Filter by script name substring")
    args = ap.parse_args()
    records = load_records(args.days, args.script)
    report(records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
