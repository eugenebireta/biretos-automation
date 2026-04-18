"""Snapshot-deprecation monitor for pinned AI-Audit models (Patch 9, v0.5.1).

Checks pinned Anthropic/Google snapshots against provider deprecation
policies. Alerts owner when any pinned model_id approaches end-of-life,
so migration + golden-set regression can run BEFORE the snapshot dies.

Run:
    python ai_audit/snapshot_monitor.py                   # check all pinned
    python ai_audit/snapshot_monitor.py --check-only      # exit 0/1, no stdout

Data sources (manually curated — no scraping; provider pages change layout):
    Anthropic: docs.claude.com/en/docs/about-claude/model-deprecations
    Google:    ai.google.dev/gemini-api/docs/deprecations

Exits 0 = all pinned models current, 1 = at least one alert.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent

# Curated deprecation table. Update manually when provider announces.
# Format: {model_id: {"retirement_date": ISO | "unknown", "notes": str}}
PROVIDER_SNAPSHOTS: dict[str, dict] = {
    # Anthropic — 60-day minimum notice per policy, Sonnet 3.5 survived ~16mo.
    "claude-sonnet-4-5-20250929": {
        "provider": "anthropic",
        "retirement_date": "unknown",  # not yet announced as of 2026-04-18
        "ga_date": "2025-09-29",
        "estimated_lifespan_days": 450,  # 15 months, empirical floor
        "notes": "Sonnet 4 deprecated 2026-04-14; Sonnet 4.5 likely next 6-12mo",
    },
    "claude-haiku-4-5-20251001": {
        "provider": "anthropic",
        "retirement_date": "unknown",
        "ga_date": "2025-10-01",
        "estimated_lifespan_days": 450,
        "notes": "In active use as SECOND_OPINION / PRECEDENT_SCANNER / PREMORTEM",
    },
    "claude-opus-4-6": {
        "provider": "anthropic",
        "retirement_date": "unknown",
        "ga_date": "2025-10-01",
        "estimated_lifespan_days": 450,
        "notes": "Arbiter + Tier-3 escalation",
    },
    # Google Gemini — GA typically 12 months, earliest shutdown announced.
    "gemini-2.5-flash": {
        "provider": "google",
        "retirement_date": "2026-06-17",  # announced; earliest
        "ga_date": "2025-06-17",
        "estimated_lifespan_days": 365,
        "notes": "CHALLENGER default; migration urgent — ~2 months window",
    },
    "gemini-2.5-pro": {
        "provider": "google",
        "retirement_date": "2026-06-17",
        "ga_date": "2025-06-17",
        "estimated_lifespan_days": 365,
        "notes": "CHALLENGER escalation; same window as Flash",
    },
}


def check(today: date | None = None) -> dict:
    """Return alert status for all pinned models."""
    today = today or date.today()
    alerts: list[dict] = []

    for model_id, meta in PROVIDER_SNAPSHOTS.items():
        retire_str = meta["retirement_date"]
        ga_str = meta.get("ga_date")
        lifespan = meta.get("estimated_lifespan_days", 365)

        if retire_str == "unknown":
            if ga_str:
                ga = date.fromisoformat(ga_str)
                projected = ga + timedelta(days=lifespan)
                days_to_projected = (projected - today).days
                if days_to_projected <= 90:
                    alerts.append({
                        "model": model_id,
                        "provider": meta["provider"],
                        "urgency": "HIGH" if days_to_projected <= 30 else "MEDIUM",
                        "days_to_retirement": days_to_projected,
                        "retirement_date": projected.isoformat(),
                        "source": "projected_from_ga",
                        "note": meta["notes"],
                    })
        else:
            retire = date.fromisoformat(retire_str)
            days_to = (retire - today).days
            if days_to <= 90:
                alerts.append({
                    "model": model_id,
                    "provider": meta["provider"],
                    "urgency": "CRITICAL" if days_to <= 30 else "HIGH" if days_to <= 60 else "MEDIUM",
                    "days_to_retirement": days_to,
                    "retirement_date": retire.isoformat(),
                    "source": "announced",
                    "note": meta["notes"],
                })

    return {
        "checked_at": today.isoformat(),
        "models_checked": len(PROVIDER_SNAPSHOTS),
        "alerts": alerts,
        "migration_required": len(alerts) > 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true", help="Exit code only, no stdout")
    args = ap.parse_args()

    result = check()
    if not args.check_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["alerts"]:
            print("\n=== ACTION ITEMS ===", file=sys.stderr)
            for alert in result["alerts"]:
                print(
                    f"[{alert['urgency']}] {alert['model']} → retires "
                    f"{alert['retirement_date']} ({alert['days_to_retirement']}d). "
                    f"Run golden-set regression on replacement model.",
                    file=sys.stderr,
                )
    return 1 if result["alerts"] else 0


if __name__ == "__main__":
    sys.exit(main())
