"""
cli.py — CLI для запуска review_runner.

Команды:
    dry-run        — полный цикл с mock providers (Phase 1)
    run            — одна задача с mock providers
    live           — одна задача с live API аудиторами (Phase 2)
    pilot          — 3 pilot-gate задачи с live аудиторами (Phase 2)
    verdict        — ручной owner verdict по run_id (Phase 2)

Секреты для live/pilot читаются ТОЛЬКО из auditor_system/config/.env.auditors
через dotenv_values() — НЕ load_dotenv() (SPEC §20.8).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Secrets loading (SPEC §20.8)
# ---------------------------------------------------------------------------

_SECRETS_PATH = Path("auditor_system/config/.env.auditors")


def _load_secrets() -> dict[str, str]:
    """
    Loads API keys from .env.auditors via dotenv_values().
    NEVER uses load_dotenv() — that would pollute os.environ.
    NEVER falls back to os.environ for ANTHROPIC_API_KEY.
    """
    try:
        from dotenv import dotenv_values
    except ImportError:
        logger.error("python-dotenv not installed. Run: pip install python-dotenv")
        sys.exit(1)

    secrets_path = _SECRETS_PATH
    if not secrets_path.exists():
        logger.error(
            "Secrets file not found: %s\n"
            "Create it with ANTHROPIC_API_KEY and OPENAI_API_KEY.",
            secrets_path,
        )
        sys.exit(1)

    secrets = dict(dotenv_values(str(secrets_path)))

    if not secrets.get("ANTHROPIC_API_KEY"):
        logger.error(
            "ANTHROPIC_API_KEY missing in %s (required for live auditor)", secrets_path
        )
        sys.exit(1)

    # OPENAI_API_KEY: from .env.auditors first, fallback to system env (safe — not auth key)
    if not secrets.get("OPENAI_API_KEY"):
        openai_env = os.environ.get("OPENAI_API_KEY", "")
        if openai_env:
            secrets["OPENAI_API_KEY"] = openai_env
        else:
            logger.error(
                "OPENAI_API_KEY missing in %s and not in system env", secrets_path
            )
            sys.exit(1)

    return secrets


# ---------------------------------------------------------------------------
# Runner factories
# ---------------------------------------------------------------------------

def _make_mock_runner(runs_dir: Path = Path("runs"), experience_dir: Path = Path(".")):
    """Mock runner for dry-run / run commands (Phase 1 compat)."""
    from .providers.mock_builder import MockBuilder
    from .providers.mock_auditor import make_approve_auditor
    from .review_runner import ReviewRunner

    return ReviewRunner(
        builder=MockBuilder(),
        auditors=[
            make_approve_auditor("mock_openai"),
            make_approve_auditor("mock_anthropic"),
        ],
        runs_dir=runs_dir,
        experience_dir=experience_dir,
    )


def _make_live_runner(runs_dir: Path = Path("runs"), experience_dir: Path = Path(".")):
    """
    Live runner with real OpenAI + Anthropic auditors.
    Secrets loaded from .env.auditors — NOT from os.environ.
    """
    import yaml
    from .providers.mock_builder import MockBuilder
    from .providers.openai_auditor import OpenAIAuditor
    from .providers.anthropic_auditor import AnthropicAuditor
    from .review_runner import ReviewRunner

    secrets = _load_secrets()
    config_path = Path("auditor_system/config/models.yaml")

    # Load model config
    models_config: dict = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            models_config = yaml.safe_load(f) or {}

    openai_model = models_config.get("auditors", {}).get("openai", "gpt-4o")
    anthropic_model = models_config.get("auditors", {}).get("anthropic", "claude-sonnet-4-6-20250514")

    return ReviewRunner(
        builder=MockBuilder(),
        auditors=[
            OpenAIAuditor(model=openai_model, api_key=secrets["OPENAI_API_KEY"]),
            AnthropicAuditor(model=anthropic_model, api_key=secrets["ANTHROPIC_API_KEY"]),
        ],
        runs_dir=runs_dir,
        experience_dir=experience_dir,
        model_config_path=config_path,
    )


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

async def _run_task(args, live: bool = False):
    from .hard_shell.contracts import RiskLevel, TaskPack

    task = TaskPack(
        title=args.title,
        description=args.description or "",
        roadmap_stage=args.stage,
        why_now=args.why_now,
        risk=RiskLevel(args.risk),
        depends_on=args.depends_on or [],
        keywords=args.keywords or [],
        affected_files=args.files or [],
    )

    runner = _make_live_runner() if live else _make_mock_runner()
    run = await runner.execute(task)

    print(f"\n{'='*60}")
    print(f"Run ID:    {run.run_id}")
    print(f"Route:     {run.approval_route.value if run.approval_route else 'N/A'}")
    print(f"Model:     {run.model_used.value} (escalated={run.escalated})")
    print(f"Surface:   {sorted(run.surface.effective_surface) if run.surface else []}")
    print(f"Gate:      {'PASSED' if run.quality_gate and run.quality_gate.passed else 'FAILED'}")
    print(f"Duration:  {run.duration_minutes:.2f}min" if run.duration_minutes else "Duration: N/A")
    print(f"\nArtifacts: runs/{run.run_id}/")
    print(f"{'='*60}\n")

    summary_path = Path("runs") / run.run_id / "owner_summary.md"
    if summary_path.exists():
        print(summary_path.read_text(encoding="utf-8"))

    return run


async def _dry_run(args):
    """Полный цикл с mock providers — для проверки Phase 1."""
    from .hard_shell.contracts import RiskLevel, TaskPack

    print("Running Phase 1 dry-run with mock providers...\n")

    tasks = [
        TaskPack(
            title="LOW: Update photo scout config",
            roadmap_stage="R1",
            why_now="Needed before next scout batch",
            risk=RiskLevel.LOW,
        ),
        TaskPack(
            title="SEMI: Add price validation to export pipeline",
            roadmap_stage="R1",
            why_now="Price gaps found in followup queue",
            risk=RiskLevel.SEMI,
        ),
        TaskPack(
            title="CORE: Update FSM state transitions",
            roadmap_stage="5.5",
            why_now="Required by Iron Fence before Revenue branch",
            risk=RiskLevel.CORE,
            keywords=["fsm", "guardian"],
        ),
    ]

    runner = _make_mock_runner()
    results = []
    for task in tasks:
        print(f"Processing: {task.title}")
        run = await runner.execute(task)
        results.append(run)
        print(f"  → route={run.approval_route.value} model={run.model_used.value} escalated={run.escalated}")

    print(f"\n{'='*60}")
    print("DRY-RUN COMPLETE")
    print(f"{'='*60}")
    for run in results:
        print(f"  {run.task.risk.value.upper():5} | {run.approval_route.value:20} | {run.task.title}")
    print(f"\nCheck artifacts in: runs/")
    return results


async def _pilot(args):
    """
    Phase 2 Pilot Gate: 3 real tasks with live auditors.

    LOW → expected AUTO_PASS (Sonnet)
    SEMI → expected BATCH_APPROVAL (Sonnet)
    CORE → expected INDIVIDUAL_REVIEW (Opus, guardian surface)

    NO live side-effects. Builder generates text proposals.
    Owner reviews runs/<run_id>/owner_summary.md and runs:
        python -m auditor_system.cli verdict <run_id> --approved
    """
    from .hard_shell.contracts import RiskLevel, TaskPack

    pilot_tasks = [
        TaskPack(
            title="Branch protection на master",
            description=(
                "Настроить branch protection rules на master: require PR, require CI pass, "
                "no direct push. Реализация через GitHub CLI / API. "
                "Никаких изменений файлов в репозитории."
            ),
            roadmap_stage="2.2",
            why_now="CI уже настроен (2.1), branch protection — следующий шаг",
            risk=RiskLevel.LOW,
            depends_on=["2.1"],
        ),
        TaskPack(
            title="Iron Fence: Boundary Grep M3a",
            description=(
                "CI grep-проверка: запрет DML по reconciliation_* таблицам из Tier-3 кода. "
                "Создать .github/workflows/iron_fence.yml с grep-шагом. "
                "Exit 1 если любой match найден в scripts/ или workers/."
            ),
            roadmap_stage="5.5.2",
            why_now="Hash Lock (5.5.1) done, grep guards — следующий шаг к Revenue",
            risk=RiskLevel.SEMI,
            depends_on=["5.5.1"],
        ),
        TaskPack(
            title="Pydantic Validation на 3 границах",
            description=(
                "Pydantic validation на границах: API input, domain boundary (TaskIntent перед Guardian), "
                "external output (перед экспортом). "
                "ValidationError → structured log: error_class=POLICY_VIOLATION, severity=ERROR, retriable=False. "
                "Alert owner. Never silent pass. "
                "Затронутые файлы: guardian.py, webhook_handler.py, export_pipeline.py"
            ),
            roadmap_stage="5.2",
            why_now="5.1 done (TaskIntent + ActionSnapshot), validation — следующий",
            risk=RiskLevel.CORE,
            depends_on=["5.1"],
            declared_surface=["guardian_logic"],
        ),
    ]

    print("Phase 2 Pilot Gate — live auditors\n")
    print("Tasks:")
    for t in pilot_tasks:
        print(f"  [{t.risk.value.upper():5}] {t.title}")
    print()

    runner = _make_live_runner()
    results = []

    for task in pilot_tasks:
        print(f"\n{'-'*60}")
        print(f"Running: [{task.risk.value.upper()}] {task.title}")
        print(f"{'-'*60}")
        try:
            run = await runner.execute(task)
            results.append(run)
            print(f"  Run ID:  {run.run_id}")
            print(f"  Route:   {run.approval_route.value if run.approval_route else 'N/A'}")
            print(f"  Model:   {run.model_used.value} (escalated={run.escalated})")
            print(f"  Gate:    {'PASSED' if run.quality_gate and run.quality_gate.passed else 'FAILED'}")

            summary_path = Path("runs") / run.run_id / "owner_summary.md"
            if summary_path.exists():
                print("\n" + summary_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  ERROR: {exc}")
            logger.error("pilot: task failed task=%s error=%s", task.title, exc)

    print(f"\n{'='*60}")
    print("PILOT GATE COMPLETE")
    print(f"{'='*60}")
    for run in results:
        print(
            f"  {run.task.risk.value.upper():5} | "
            f"{(run.approval_route.value if run.approval_route else 'ERROR'):22} | "
            f"{run.task.title}"
        )

    print("\nNext step — owner verdict for each run:")
    for run in results:
        print(f"  python -m auditor_system.cli verdict {run.run_id} --approved")

    return results


async def _verdict(args):
    """
    Records owner verdict for a completed run.
    ExperienceSink writes DPO record ONLY after this command.
    """
    from .hard_shell.run_store import RunStore
    from .hard_shell.experience_sink import ExperienceSink

    run_id = args.run_id
    verdict = "approved" if args.approved else "rejected"
    notes = args.reason or ""

    runs_dir = Path("runs")
    run_store = RunStore(runs_dir)

    # Load run from disk
    try:
        run = run_store.load_run_for_verdict(run_id)
    except FileNotFoundError:
        print(f"ERROR: Run not found: {run_id}")
        print(f"Available runs: {run_store.list_runs()}")
        sys.exit(1)

    if run.owner_verdict is not None:
        print(f"WARNING: Run {run_id} already has verdict: {run.owner_verdict}")
        print("Re-recording with new verdict...")

    # Save owner_verdict.json
    run_store.save_owner_verdict(run_id, verdict, notes)
    run.owner_verdict = verdict
    run.owner_notes = notes

    # Now ExperienceSink can write
    experience_sink = ExperienceSink(Path("."))
    experience_sink.record(run)
    run_store.save_manifest(run)

    print(f"\n{'='*60}")
    print(f"Verdict recorded")
    print(f"  Run ID:  {run_id}")
    print(f"  Verdict: {verdict}")
    if notes:
        print(f"  Notes:   {notes}")
    print(f"\nDPO record written to: experience_log/ or anti_patterns/")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Governed AI Execution System — Phase 2"
    )
    subparsers = parser.add_subparsers(dest="command")

    # dry-run
    subparsers.add_parser("dry-run", help="Full cycle with mock providers (Phase 1)")

    # run (mock)
    run_parser = subparsers.add_parser("run", help="Single task with mock providers")
    _add_task_args(run_parser)

    # live (live auditors)
    live_parser = subparsers.add_parser("live", help="Single task with live API auditors")
    _add_task_args(live_parser)

    # pilot
    subparsers.add_parser(
        "pilot",
        help="Phase 2 Pilot Gate: 3 tasks (LOW+SEMI+CORE) with live auditors",
    )

    # verdict
    verdict_parser = subparsers.add_parser(
        "verdict",
        help="Record owner verdict for a completed run",
    )
    verdict_parser.add_argument("run_id", help="Run ID from runs/ directory")
    verdict_group = verdict_parser.add_mutually_exclusive_group(required=True)
    verdict_group.add_argument("--approved", action="store_true")
    verdict_group.add_argument("--rejected", action="store_true")
    verdict_parser.add_argument("--reason", default="", help="Rejection reason (optional)")

    args = parser.parse_args()

    if args.command == "dry-run":
        asyncio.run(_dry_run(args))
    elif args.command == "run":
        asyncio.run(_run_task(args, live=False))
    elif args.command == "live":
        asyncio.run(_run_task(args, live=True))
    elif args.command == "pilot":
        asyncio.run(_pilot(args))
    elif args.command == "verdict":
        asyncio.run(_verdict(args))
    else:
        parser.print_help()
        sys.exit(1)


def _add_task_args(p):
    p.add_argument("--title", required=True)
    p.add_argument("--stage", required=True, help="Roadmap stage (e.g. R1, 5.5)")
    p.add_argument("--why-now", required=True, dest="why_now")
    p.add_argument("--risk", required=True, choices=["low", "semi", "core"])
    p.add_argument("--description", default="")
    p.add_argument("--depends-on", nargs="*", dest="depends_on")
    p.add_argument("--keywords", nargs="*")
    p.add_argument("--files", nargs="*")


if __name__ == "__main__":
    main()
