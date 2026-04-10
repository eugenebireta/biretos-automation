"""
fix_card_status_mismatch.py — Tier-3 bounded cleanup of policy card status mismatches.

Finds evidence bundles where refresh_trace.policy_card_status_mismatch=true,
reconciles top-level card_status and policy_decision_v2.card_status to match
verifier_shadow.packet.card_status (ground truth), and clears the mismatch flag.

Tier-3 module requirements:
  - trace_id from caller
  - idempotency_key per file mutation
  - no DB operations
  - structured error logging
  - deterministic, runnable in isolation
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / "downloads" / "evidence"


@dataclass
class MismatchFixResult:
    trace_id: str
    fixed: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    total_scanned: int = 0


def find_mismatches(evidence_dir: Path | None = None) -> list[Path]:
    """Find evidence files with policy_card_status_mismatch=true."""
    edir = evidence_dir or EVIDENCE_DIR
    results = []
    for f in sorted(edir.glob("evidence_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            rt = data.get("refresh_trace", {})
            if rt.get("policy_card_status_mismatch"):
                results.append(f)
        except Exception as exc:
            logger.warning("find_mismatches: failed to read %s: %s", f, exc)
    return results


def fix_single(filepath: Path, trace_id: str, dry_run: bool = False) -> dict:
    """Fix a single evidence file.

    Returns dict with pn, old_card_status, new_card_status, action.
    """
    data = json.loads(filepath.read_text(encoding="utf-8"))
    pn = data.get("pn", "unknown")
    idempotency_key = f"{trace_id}::{pn}::card_status_fix"

    old_top = data.get("card_status")
    pd_v2_cs = (data.get("policy_decision_v2") or {}).get("card_status")
    verifier_cs = (data.get("verifier_shadow", {})
                   .get("packet", {})
                   .get("card_status"))

    # Ground truth: verifier_shadow > refresh_trace.historical > policy_decision_v2
    ground_truth = verifier_cs
    if not ground_truth:
        rt = data.get("refresh_trace", {})
        ground_truth = rt.get("policy_card_status_historical")
    if not ground_truth:
        return {
            "pn": pn,
            "idempotency_key": idempotency_key,
            "action": "skipped",
            "reason": "no ground truth source found",
        }

    changes = []

    # 1. Fix top-level card_status
    if old_top != ground_truth:
        data["card_status"] = ground_truth
        changes.append(f"card_status: {old_top} -> {ground_truth}")

    # 2. Fix policy_decision_v2.card_status
    if pd_v2_cs and pd_v2_cs != ground_truth:
        data["policy_decision_v2"]["card_status"] = ground_truth
        changes.append(f"policy_decision_v2.card_status: {pd_v2_cs} -> {ground_truth}")

    # 3. Clear LEGACY_AUTO_PUBLISH_HOLDOUT from review_reasons
    rr = data.get("review_reasons", [])
    if "LEGACY_AUTO_PUBLISH_HOLDOUT" in rr:
        rr.remove("LEGACY_AUTO_PUBLISH_HOLDOUT")
        data["review_reasons"] = rr
        changes.append("removed LEGACY_AUTO_PUBLISH_HOLDOUT from review_reasons")

    # 4. Clear mismatch flag
    rt = data.get("refresh_trace", {})
    if rt.get("policy_card_status_mismatch"):
        rt["policy_card_status_mismatch"] = False
        rt["policy_card_status_fix_trace_id"] = trace_id
        rt["policy_card_status_fix_ts"] = datetime.now(timezone.utc).isoformat()
        data["refresh_trace"] = rt
        changes.append("policy_card_status_mismatch -> false")

    if not changes:
        return {
            "pn": pn,
            "idempotency_key": idempotency_key,
            "action": "already_clean",
            "old_card_status": old_top,
            "new_card_status": old_top,
        }

    if not dry_run:
        filepath.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return {
        "pn": pn,
        "idempotency_key": idempotency_key,
        "action": "fixed",
        "old_card_status": old_top,
        "new_card_status": ground_truth,
        "changes": changes,
    }


def run(trace_id: str, evidence_dir: Path | None = None,
        dry_run: bool = False) -> MismatchFixResult:
    """Fix all policy card status mismatches in evidence directory."""
    if not trace_id:
        raise ValueError("trace_id is required")

    edir = evidence_dir or EVIDENCE_DIR
    result = MismatchFixResult(trace_id=trace_id)

    all_files = list(edir.glob("evidence_*.json"))
    result.total_scanned = len(all_files)

    mismatch_files = find_mismatches(edir)
    logger.info(
        "fix_card_status_mismatch: found %d mismatches in %d files",
        len(mismatch_files), result.total_scanned,
        extra={"error_class": None, "severity": "INFO", "retriable": False},
    )

    for fpath in mismatch_files:
        try:
            fix = fix_single(fpath, trace_id, dry_run=dry_run)
            if fix["action"] == "fixed":
                result.fixed.append(fix)
            elif fix["action"] == "skipped":
                result.skipped.append(fix)
            else:
                result.skipped.append(fix)
        except Exception as exc:
            pn = fpath.stem.replace("evidence_", "")
            logger.error(
                "fix_card_status_mismatch: error fixing %s: %s",
                pn, exc,
                extra={"error_class": "TRANSIENT", "severity": "ERROR",
                       "retriable": True},
            )
            result.errors.append({"pn": pn, "error": str(exc)})

    logger.info(
        "fix_card_status_mismatch: done fixed=%d skipped=%d errors=%d",
        len(result.fixed), len(result.skipped), len(result.errors),
        extra={"error_class": None, "severity": "INFO", "retriable": False},
    )
    return result


if __name__ == "__main__":
    import sys
    tid = sys.argv[1] if len(sys.argv) > 1 else "manual_fix_card_status"
    dry = "--dry-run" in sys.argv
    res = run(trace_id=tid, dry_run=dry)
    print(f"Scanned: {res.total_scanned}")
    print(f"Fixed: {len(res.fixed)}")
    for f in res.fixed:
        print(f"  {f['pn']}: {f['old_card_status']} -> {f['new_card_status']}")
        for c in f.get("changes", []):
            print(f"    - {c}")
    if res.skipped:
        print(f"Skipped: {len(res.skipped)}")
    if res.errors:
        print(f"Errors: {len(res.errors)}")
        for e in res.errors:
            print(f"  {e['pn']}: {e['error']}")
