"""
Live test: debate protocol with real Gemini + Anthropic APIs.

Task: product lot obsolescence analyzer.
Proposal: deliberately includes some issues to trigger debate.

Usage:
    python -m auditor_system.tests.live_debate_test
"""
from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stdout,
)


def main():
    from auditor_system.runner_factory import create_review_runner
    from auditor_system.hard_shell.contracts import RiskLevel, TaskPack

    # --- Real task: product lot obsolescence analyzer ---
    task = TaskPack(
        title="Lot obsolescence analyzer: detect morally/physically obsolete products",
        description=(
            "Build a module that analyzes product lots from the catalog to detect:\n"
            "1. Morally obsolete items (superseded by newer revision/model)\n"
            "2. Physically obsolete items (shelf life expired or expiring)\n"
            "3. Price anomalies relative to current market\n"
            "\n"
            "The module reads evidence files, cross-references with DR results,\n"
            "and outputs a risk-scored report per SKU.\n"
            "\n"
            "Must handle: Honeywell sub-brands (PEHA, Esser, Notifier),\n"
            "revision suffixes (-R2, .10, -RU), and pack-price vs unit-price.\n"
        ),
        roadmap_stage="R1",
        why_now="Need to identify dead stock before next procurement cycle",
        risk=RiskLevel.SEMI,
        declared_surface=["idempotency_replay"],
        affected_files=[
            "scripts/lot_analyzer.py",
            "scripts/obsolescence_rules.py",
            "tests/test_lot_analyzer.py",
        ],
        keywords=["lot", "obsolescence", "price", "revision", "shelf_life"],
    )

    # --- Proposal with deliberate issues to provoke debate ---
    proposal = """
## Lot Obsolescence Analyzer — Implementation Proposal

### Architecture

```python
# scripts/lot_analyzer.py
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

def analyze_lot(evidence_dir: Path, output_path: Path, trace_id: str = "lot_analyze"):
    \"\"\"
    Scan evidence files and produce obsolescence risk report.

    Each SKU gets a risk score:
      - HIGH: morally obsolete (superseded) + price > market
      - MEDIUM: revision available or approaching shelf life
      - LOW: current and competitively priced
    \"\"\"
    results = []

    for efile in sorted(evidence_dir.glob("evidence_*.json")):
        evidence = json.loads(efile.read_text(encoding="utf-8"))
        sku = evidence.get("sku", "")
        pn = evidence.get("pn", "")

        # Check moral obsolescence via revision suffix
        is_superseded = _check_superseded(pn, evidence)

        # Check physical obsolescence
        shelf_risk = _check_shelf_life(evidence)

        # Price anomaly detection
        price_risk = _check_price_anomaly(evidence)

        # Composite risk score
        risk = "HIGH" if is_superseded and price_risk else (
            "MEDIUM" if is_superseded or shelf_risk else "LOW"
        )

        results.append({
            "sku": sku,
            "pn": pn,
            "risk": risk,
            "superseded": is_superseded,
            "shelf_risk": shelf_risk,
            "price_anomaly": price_risk,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "trace_id": trace_id,
        })

    # Write results atomically
    content = json.dumps(results, indent=2, ensure_ascii=False)
    output_path.write_text(content, encoding="utf-8")

    return {
        "total": len(results),
        "high": sum(1 for r in results if r["risk"] == "HIGH"),
        "medium": sum(1 for r in results if r["risk"] == "MEDIUM"),
        "low": sum(1 for r in results if r["risk"] == "LOW"),
    }


def _check_superseded(pn: str, evidence: dict) -> bool:
    \"\"\"Check if PN has been superseded by newer revision.\"\"\"
    # Known revision patterns: -R2, -R3, .20, .30
    import re
    rev_match = re.search(r'[-.]R?(\\d+)$', pn)
    if rev_match:
        rev_num = int(rev_match.group(1))
        # If current revision < known latest, it's superseded
        latest = evidence.get("latest_revision", rev_num)
        return rev_num < latest

    # Check if evidence explicitly marks as discontinued
    return evidence.get("discontinued", False)


def _check_shelf_life(evidence: dict) -> bool:
    \"\"\"Check if product is approaching end of shelf life.\"\"\"
    expiry = evidence.get("shelf_life_end")
    if not expiry:
        return False
    try:
        expiry_date = datetime.fromisoformat(expiry)
        days_left = (expiry_date - datetime.now(timezone.utc)).days
        return days_left < 90  # Warning if < 90 days
    except (ValueError, TypeError):
        return False


def _check_price_anomaly(evidence: dict) -> bool:
    \"\"\"Compare lot price vs market price from DR results.\"\"\"
    lot_price = evidence.get("price")
    market_price = evidence.get("dr_price")

    if not lot_price or not market_price:
        return False

    try:
        ratio = float(lot_price) / float(market_price)
        return ratio > 1.5  # 50% above market = anomaly
    except (ValueError, ZeroDivisionError):
        return False
```

### Missing items (known gaps)
- No idempotency_key yet (will add in next iteration)
- Tests not written yet
- No structured error logging (error_class/severity/retriable)
- Atomic write uses write_text, not temp+replace pattern
- hashlib imported but unused

### Test plan
- Unit test for each _check_* function with mock evidence
- Integration test with sample evidence directory
"""

    # --- Build runner with live APIs ---
    runner = create_review_runner(
        proposal_text=proposal,
        runs_dir="auditor_system/runs",
        experience_dir="shadow_log",
    )

    print("\n" + "=" * 60)
    print("LIVE DEBATE TEST — Lot Obsolescence Analyzer")
    print("=" * 60)
    print(f"Task: {task.title}")
    print(f"Risk: {task.risk.value}")
    print("Auditors: Gemini (CRITIC) + Anthropic (JUDGE)")
    print("Arbiter: Opus (if needed)")
    print("=" * 60 + "\n")

    run = asyncio.run(runner.execute(task))

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Run ID: {run.run_id}")
    print(f"Duration: {run.duration_minutes:.1f} min")
    print()

    # Round 1
    print("--- Round 1 (isolated critiques) ---")
    for v in run.critiques:
        print(f"  {v.auditor_id}: {v.verdict.value} | {v.summary[:80]}")
        for i in v.issues:
            print(f"    [{i.severity.value}] {i.area}: {i.description[:60]}")
    print()

    # Debate
    print(f"Debate triggered: {run.debate_triggered}")
    if run.debate_triggered:
        print("--- Round 2 (debate, cross-visible) ---")
        for v in run.debate_verdicts:
            print(f"  {v.auditor_id}: {v.verdict.value} | {v.summary[:80]}")
            for i in v.issues:
                print(f"    [{i.severity.value}] {i.area}: {i.description[:60]}")
        print()

    # Arbiter
    print(f"Arbiter used: {run.arbiter_used}")
    if run.arbiter_verdict:
        print("--- Round 3 (Opus arbiter) ---")
        v = run.arbiter_verdict
        print(f"  {v.auditor_id}: {v.verdict.value} | {v.summary[:80]}")
        for i in v.issues:
            print(f"    [{i.severity.value}] {i.area}: {i.description[:60]}")
        print()

    # Final
    print(f"Quality Gate: {'PASSED' if run.quality_gate.passed else 'FAILED'} ({run.quality_gate.reason})")
    print(f"Route: {run.approval_route.value}")
    print(f"Final verdicts: {[v.verdict.value for v in run.final_verdicts]}")
    print("=" * 60)


if __name__ == "__main__":
    main()
