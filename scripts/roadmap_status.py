#!/usr/bin/env python3
"""roadmap_status.py — compute Roadmap stage status from code artifacts.

Reads no documentation. Checks files, tests, CI config, migrations.
Outputs: terminal table + docs/ROADMAP_LIVE_STATUS.json.

Usage:
    python scripts/roadmap_status.py           # table + JSON
    python scripts/roadmap_status.py --json    # JSON only
"""
from __future__ import annotations

import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / ".cursor" / "windmill-core-v1"
SCRIPTS = ROOT / "scripts"
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"
OUTPUT_JSON = ROOT / "docs" / "ROADMAP_LIVE_STATUS.json"

# ---------------------------------------------------------------------------
# Check primitives
# ---------------------------------------------------------------------------


def _file_exists(path: Path) -> tuple[bool, str]:
    if path.exists():
        return True, str(path.relative_to(ROOT))
    return False, f"MISSING: {path.name}"


def _dir_file_count(path: Path, glob: str = "*.py") -> tuple[int, str]:
    if not path.exists():
        return 0, f"MISSING: {path.name}/"
    files = list(path.glob(glob))
    return len(files), f"{len(files)} files in {path.relative_to(ROOT)}/"


def _ci_has_step(name_fragment: str) -> tuple[bool, str]:
    if not CI_YML.exists():
        return False, "MISSING: ci.yml"
    text = CI_YML.read_text(encoding="utf-8")
    if name_fragment.lower() in text.lower():
        return True, f"ci.yml contains '{name_fragment}'"
    return False, f"ci.yml missing '{name_fragment}'"


def _file_contains(path: Path, pattern: str) -> tuple[bool, str]:
    if not path.exists():
        return False, f"MISSING: {path.name}"
    text = path.read_text(encoding="utf-8", errors="replace")
    if re.search(pattern, text):
        return True, f"{path.name} matches /{pattern}/"
    return False, f"{path.name} missing /{pattern}/"


# ---------------------------------------------------------------------------
# Check runner
# ---------------------------------------------------------------------------


def _run_checks(checks: list[tuple[str, Any]]) -> list[dict]:
    """Run a list of (label, check_fn_or_tuple) and return results."""
    results = []
    for label, check in checks:
        if callable(check):
            ok, evidence = check()
        else:
            ok, evidence = check
        results.append({"label": label, "ok": ok, "evidence": evidence})
    return results


def _stage_status(check_results: list[dict]) -> str:
    total = len(check_results)
    passed = sum(1 for c in check_results if c["ok"])
    if passed == total:
        return "DONE"
    if passed > 0:
        return "PARTIAL"
    return "NOT_STARTED"


# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

# Helper: deferred check (lazy evaluation)
def _f(path: Path):
    return lambda: _file_exists(path)


def _ci(fragment: str):
    return lambda: _ci_has_step(fragment)


def _fc(path: Path, pattern: str):
    return lambda: _file_contains(path, pattern)


def _dfc(path: Path, glob: str, min_count: int):
    def _check():
        count, evidence = _dir_file_count(path, glob)
        return count >= min_count, evidence
    return _check


STAGES: list[dict[str, Any]] = [
    # ── PART I: CORE FOUNDATION ──────────────────────────────────────────
    {
        "id": "1",
        "name": "Governance Executor",
        "risk": "CORE",
        "roadmap_claimed": "IN_PROGRESS",
        "checks": [
            ("1.1 dispatch_action.py", _f(CORE / "ru_worker" / "dispatch_action.py")),
            ("1.1 governance_executor.py", _f(CORE / "ru_worker" / "governance_executor.py")),
            ("1.3 idempotency module", _f(CORE / "ru_worker" / "idempotency.py")),
            ("1.5 replay verify", _f(CORE / "cli" / "replay.py")),
            ("test_governance_executor", _f(CORE / "tests" / "test_governance_executor.py")),
            ("test_governance_workflow", _f(CORE / "tests" / "test_governance_workflow.py")),
            ("test_governance_trigger", _f(CORE / "tests" / "test_governance_trigger.py")),
            ("test_idempotency", _f(CORE / "tests" / "test_idempotency.py")),
        ],
    },
    {
        "id": "2",
        "name": "CI + Branch Protection",
        "risk": "SEMI",
        "roadmap_claimed": "IN_PROGRESS",
        "checks": [
            ("2.1 ci.yml exists", _f(CI_YML)),
            ("2.1 ci.yml runs pytest", _ci("pytest")),
            ("2.2 branch protection (CI required)", _ci("Run tests")),
            ("2.3 governance tests collected", _f(
                CORE / "tests" / "test_governance_executor.py")),
        ],
    },
    {
        "id": "2.5",
        "name": "Context Cortex",
        "risk": "SEMI",
        "roadmap_claimed": "DONE",
        "checks": [
            ("PROJECT_DNA.md", _f(ROOT / "docs" / "PROJECT_DNA.md")),
            ("CLAUDE.md", _f(ROOT / "CLAUDE.md")),
        ],
    },
    {
        "id": "3",
        "name": "Reconciliation RC-2..RC-7",
        "risk": "CORE",
        "roadmap_claimed": "NOT_STARTED",
        "checks": [
            ("reconciliation_service.py", _f(CORE / "domain" / "reconciliation_service.py")),
            ("RC-2 test", _f(CORE / "tests" / "validation" / "test_phase3_rc2_shipment_cache.py")),
            ("RC-3 test", _f(CORE / "tests" / "validation" / "test_phase3_rc3_stock_snapshot.py")),
            ("RC-5 test", _f(CORE / "tests" / "validation" / "test_phase3_rc5_document_key.py")),
            ("RC-6 test", _f(CORE / "tests" / "validation" / "test_phase3_rc6_pending_payment.py")),
            ("RC-7 test", _f(CORE / "tests" / "validation" / "test_phase3_rc7_shipment_sync.py")),
            ("CI runs RC tests", _ci("test_phase3_rc2")),
        ],
    },
    {
        "id": "4",
        "name": "Alerting",
        "risk": "SEMI",
        "roadmap_claimed": "NOT_STARTED",
        "checks": [
            ("alert_dispatcher.py", _f(CORE / "side_effects" / "alert_dispatcher.py")),
            ("test_alert_dispatcher.py", _f(CORE / "tests" / "test_alert_dispatcher.py")),
            ("severity routing", _fc(
                CORE / "side_effects" / "alert_dispatcher.py", r"CRITICAL.*HIGH")),
            ("TELEGRAM_ALERT_CHAT_ID config", _fc(
                CORE / "config" / "schema.py", r"telegram_alert_chat_id")),
        ],
    },
    {
        "id": "4.5",
        "name": "Observability Strategy",
        "risk": "SEMI",
        "roadmap_claimed": "NOT_STARTED",
        "checks": [
            ("observability_service.py", _f(CORE / "domain" / "observability_service.py")),
            ("structured logging standard", _fc(
                CORE / "domain" / "observability_service.py", r"def check_")),
        ],
    },
    {
        "id": "5",
        "name": "CDM Runtime Validation (Pydantic)",
        "risk": "CORE",
        "roadmap_claimed": "PARTIAL",
        "checks": [
            ("5.1 cdm_models.py (TaskIntent)", _f(CORE / "domain" / "cdm_models.py")),
            ("5.1 test_cdm_models.py", _f(CORE / "tests" / "test_cdm_models.py")),
            ("5.2 test_cdm_validation_boundaries", _f(
                CORE / "tests" / "test_cdm_validation_boundaries.py")),
            ("5.4 guardian.py", _f(CORE / "domain" / "guardian.py")),
            ("5.4 guard_task_intent", _fc(
                CORE / "domain" / "guardian.py", r"def guard_task_intent")),
            ("5.4 guard_action_snapshot", _fc(
                CORE / "domain" / "guardian.py", r"def guard_action_snapshot")),
        ],
    },
    {
        "id": "5.5",
        "name": "Iron Fence (Core Freeze Guards)",
        "risk": "SEMI",
        "roadmap_claimed": "PARTIAL",
        "checks": [
            ("5.5.1 .tier1-hashes.sha256", _f(CORE / ".tier1-hashes.sha256")),
            ("5.5.1 CI Hash Lock step", _ci("Tier-1 Hash Lock")),
            ("5.5.2 CI Boundary Grep", _ci("Boundary Grep Guards")),
            ("5.5.3 CI Migration DDL Guard", _ci("Migration DDL Guard")),
            ("5.5.6 CI Ruff", _ci("Ruff")),
        ],
    },
    {
        "id": "6",
        "name": "Backoffice Task Engine",
        "risk": "CORE",
        "roadmap_claimed": "DONE",
        "checks": [
            ("6.1 backoffice_router.py", _f(CORE / "ru_worker" / "backoffice_router.py")),
            ("6.1 backoffice_models.py", _f(CORE / "domain" / "backoffice_models.py")),
            ("6.2 backoffice_permission.py", _f(CORE / "domain" / "backoffice_permission.py")),
            ("6.3 migration 028", _f(CORE / "migrations" / "028_backoffice_task_engine.sql")),
            ("6.3 backoffice_action_logger.py", _f(
                CORE / "ru_worker" / "backoffice_action_logger.py")),
            ("6.4 backoffice_risk_registry.py", _f(
                CORE / "domain" / "backoffice_risk_registry.py")),
            ("6.7 backoffice_snapshot_store.py", _f(
                CORE / "ru_worker" / "backoffice_snapshot_store.py")),
            ("6.9 backoffice_shadow_logger.py", _f(
                CORE / "ru_worker" / "backoffice_shadow_logger.py")),
            ("6.10 backoffice_rate_limiter.py", _f(
                CORE / "domain" / "backoffice_rate_limiter.py")),
            ("test_backoffice_router", _f(CORE / "tests" / "test_backoffice_router.py")),
            ("test_backoffice_permission", _f(CORE / "tests" / "test_backoffice_permission.py")),
            ("test_backoffice_rate_limiter", _f(
                CORE / "tests" / "test_backoffice_rate_limiter.py")),
        ],
    },
    {
        "id": "7",
        "name": "AI Executive Assistant (NLU)",
        "risk": "CORE",
        "roadmap_claimed": "DONE",
        "checks": [
            ("7.1 intent_parser.py", _f(CORE / "domain" / "intent_parser.py")),
            ("7.1 nlu_models.py", _f(CORE / "domain" / "nlu_models.py")),
            ("7.2 assistant_router.py", _f(CORE / "ru_worker" / "assistant_router.py")),
            ("7.3 nlu_confirmation_store.py", _f(
                CORE / "ru_worker" / "nlu_confirmation_store.py")),
            ("7.6 prompt_injection_guard.py", _f(
                CORE / "domain" / "prompt_injection_guard.py")),
            ("7.7 nlu_shadow_log.py", _f(CORE / "ru_worker" / "nlu_shadow_log.py")),
            ("7.8 nlu_sla_tracker.py", _f(CORE / "ru_worker" / "nlu_sla_tracker.py")),
            ("migration 029", _f(CORE / "migrations" / "029_assistant_nlu.sql")),
            ("test_intent_parser", _f(CORE / "tests" / "test_intent_parser.py")),
            ("test_assistant_router", _f(CORE / "tests" / "test_assistant_router.py")),
            ("test_nlu_confirmation", _f(CORE / "tests" / "test_nlu_confirmation_store.py")),
            ("test_prompt_injection", _f(CORE / "tests" / "test_prompt_injection_guard.py")),
        ],
    },
    {
        "id": "8",
        "name": "Stability Gate",
        "risk": "CORE",
        "roadmap_claimed": "MONITOR",
        "checks": [
            ("maintenance_sweeper.py", _f(CORE / "maintenance_sweeper.py")),
            ("retention_policy.py", _f(CORE / "retention_policy.py")),
            ("telegram_router.py", _f(CORE / "ru_worker" / "telegram_router.py")),
        ],
    },

    # ── REVENUE TRACKS ────────────────────────────────────────────────────
    {
        "id": "R1",
        "name": "Mass Catalog Pipeline",
        "risk": "SEMI",
        "roadmap_claimed": "ACTIVE",
        "checks": [
            ("catalog_worker.py", _f(CORE / "workers" / "catalog_worker.py")),
            ("catalog_models.py", _f(CORE / "domain" / "catalog_models.py")),
            ("migration 020 (stg_catalog_jobs)", _f(
                CORE / "migrations" / "020_create_stg_catalog_jobs.sql")),
            ("migration 021 (stg_catalog_imports)", _f(
                CORE / "migrations" / "021_create_stg_catalog_imports.sql")),
            ("shopware_api_client.py", _f(CORE / "ru_worker" / "shopware_api_client.py")),
            ("test_r1_catalog_pipeline", _f(
                CORE / "tests" / "validation" / "test_r1_catalog_pipeline.py")),
            ("export_pipeline.py", _f(SCRIPTS / "export_pipeline.py")),
            ("photo_pipeline.py", _f(SCRIPTS / "photo_pipeline.py")),
            ("local_catalog_refresh.py", _f(SCRIPTS / "local_catalog_refresh.py")),
            ("enrichment tests (>=20)", _dfc(
                ROOT / "tests" / "enrichment", "test_*.py", 20)),
        ],
    },
    {
        "id": "R2",
        "name": "Telegram Export",
        "risk": "LOW",
        "roadmap_claimed": "SCAFFOLD",
        "checks": [
            ("migration 027 (rev_export_logs)", _f(
                CORE / "migrations" / "027_create_rev_export_logs.sql")),
            ("test_rev_export_logs_schema", _f(
                CORE / "tests" / "test_rev_export_logs_schema.py")),
            ("telegram_router /export handler", _fc(
                CORE / "ru_worker" / "telegram_router.py", r"export")),
        ],
    },
    {
        "id": "R3",
        "name": "Lot Analyzer Engine",
        "risk": "SEMI",
        "roadmap_claimed": "NOT_STARTED",
        "checks": [
            ("run_lot_analysis.py", _f(SCRIPTS / "lot_scoring" / "run_lot_analysis.py")),
            ("scoring module", _f(SCRIPTS / "lot_scoring" / "pipeline" / "score.py")),
            ("filter engine", _f(SCRIPTS / "lot_scoring" / "filters" / "engine.py")),
            ("capital_map.py", _f(SCRIPTS / "lot_scoring" / "capital_map.py")),
            ("lot_scoring files (>=15)", _dfc(SCRIPTS / "lot_scoring", "*.py", 15)),
        ],
    },

    # ── META ORCHESTRATOR ─────────────────────────────────────────────────
    {
        "id": "META",
        "name": "Meta Orchestrator",
        "risk": "SEMI",
        "roadmap_claimed": "NOT_IN_ROADMAP",
        "checks": [
            ("M0 main.py", _f(ROOT / "orchestrator" / "main.py")),
            ("M1 classifier.py", _f(ROOT / "orchestrator" / "classifier.py")),
            ("M1 intake.py", _f(ROOT / "orchestrator" / "intake.py")),
            ("M2 advisor.py", _f(ROOT / "orchestrator" / "advisor.py")),
            ("M3 synthesizer.py", _f(ROOT / "orchestrator" / "synthesizer.py")),
            ("M4 executor_bridge.py", _f(ROOT / "orchestrator" / "executor_bridge.py")),
            ("M0.5 schemas.py", _f(ROOT / "orchestrator" / "schemas.py")),
            ("orchestrator tests (>=30)", _dfc(
                ROOT / "tests" / "orchestrator", "test_*.py", 3)),
        ],
    },

    # ── AUDITOR SYSTEM ────────────────────────────────────────────────────
    {
        "id": "AUDITOR",
        "name": "Governed AI Execution (auditor_system)",
        "risk": "SEMI",
        "roadmap_claimed": "NOT_IN_ROADMAP",
        "checks": [
            ("review_runner.py", _f(ROOT / "auditor_system" / "review_runner.py")),
            ("cli.py", _f(ROOT / "auditor_system" / "cli.py")),
            ("quality_gate.py", _f(
                ROOT / "auditor_system" / "hard_shell" / "quality_gate.py")),
            ("fallback_handler.py", _f(
                ROOT / "auditor_system" / "hard_shell" / "fallback_handler.py")),
            ("gemini_auditor.py", _f(
                ROOT / "auditor_system" / "providers" / "gemini_auditor.py")),
            ("auditor tests (>=10)", _dfc(
                ROOT / "auditor_system" / "tests", "test_*.py", 2)),
        ],
    },
]


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------


def evaluate_all() -> list[dict]:
    results = []
    for stage in STAGES:
        check_results = _run_checks(stage["checks"])
        actual = _stage_status(check_results)
        passed = sum(1 for c in check_results if c["ok"])
        total = len(check_results)
        results.append({
            "id": stage["id"],
            "name": stage["name"],
            "risk": stage["risk"],
            "roadmap_claimed": stage["roadmap_claimed"],
            "actual_status": actual,
            "passed": passed,
            "total": total,
            "checks": check_results,
        })
    return results


# ---------------------------------------------------------------------------
# Output: terminal table
# ---------------------------------------------------------------------------

# ANSI colors (disabled on Windows without colorama)
_USE_COLOR = sys.stdout.isatty() and sys.platform != "win32"


def _c(text: str, code: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


_STATUS_DISPLAY = {
    "DONE": ("DONE", "32"),        # green
    "PARTIAL": ("PARTIAL", "33"),  # yellow
    "NOT_STARTED": ("NOT STARTED", "31"),  # red
}


def _match_indicator(claimed: str, actual: str) -> str:
    """Show whether roadmap claim matches reality."""
    if actual == "DONE" and claimed in ("NOT_STARTED", "NOT_IN_ROADMAP"):
        return " << ROADMAP STALE"
    if actual == "PARTIAL" and claimed == "NOT_STARTED":
        return " << ROADMAP STALE"
    if actual == "NOT_STARTED" and claimed in ("DONE", "ACTIVE"):
        return " << MISSING CODE"
    return ""


def print_table(results: list[dict]) -> None:
    print()
    print("=" * 78)
    print("  ROADMAP LIVE STATUS")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"  Generated: {ts}")
    print("=" * 78)
    print()
    print(f"  {'Stage':<8} {'Name':<40} {'Checks':>6}  {'Actual':<12} {'Claimed':<15}")
    print(f"  {'-' * 8} {'-' * 40} {'-' * 6}  {'-' * 12} {'-' * 15}")

    for r in results:
        actual = r["actual_status"]
        disp, color = _STATUS_DISPLAY.get(actual, (actual, "0"))
        indicator = _match_indicator(r["roadmap_claimed"], actual)
        checks_str = f"{r['passed']}/{r['total']}"
        line = (
            f"  {r['id']:<8} {r['name']:<40} {checks_str:>6}  "
            f"{_c(disp, color):<12} {r['roadmap_claimed']:<15}{indicator}"
        )
        print(line)

    print()

    # Show stale entries
    stale = [r for r in results if "STALE" in _match_indicator(
        r["roadmap_claimed"], r["actual_status"])]
    if stale:
        print("  STALE ENTRIES (Roadmap behind reality):")
        for r in stale:
            print(f"    {r['id']} {r['name']}: "
                  f"claimed={r['roadmap_claimed']}, actual={r['actual_status']}")
            for c in r["checks"]:
                mark = "+" if c["ok"] else "-"
                print(f"      [{mark}] {c['label']}: {c['evidence']}")
        print()


# ---------------------------------------------------------------------------
# Output: JSON
# ---------------------------------------------------------------------------


def write_json(results: list[dict]) -> Path:
    payload = {
        "schema_version": "roadmap_live_status_v1",
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
        "stages": results,
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return OUTPUT_JSON


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    json_only = "--json" in sys.argv

    results = evaluate_all()

    if not json_only:
        print_table(results)

    out_path = write_json(results)

    if not json_only:
        print(f"  JSON written to: {out_path.relative_to(ROOT)}")
        print()

        # Summary
        done = sum(1 for r in results if r["actual_status"] == "DONE")
        partial = sum(1 for r in results if r["actual_status"] == "PARTIAL")
        not_started = sum(1 for r in results if r["actual_status"] == "NOT_STARTED")
        print(f"  Summary: {done} DONE, {partial} PARTIAL, {not_started} NOT STARTED "
              f"(out of {len(results)} stages)")
        print()


if __name__ == "__main__":
    main()
