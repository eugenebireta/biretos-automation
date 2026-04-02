"""
cli.py — CLI для запуска review_runner.

Использование:
    python -m auditor_system.cli run --title "..." --stage "5.5" --risk semi --why-now "..."
    python -m auditor_system.cli dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def _make_runner(mock: bool = True):
    from .providers.mock_builder import MockBuilder
    from .providers.mock_auditor import make_approve_auditor
    from .review_runner import ReviewRunner

    return ReviewRunner(
        builder=MockBuilder(),
        auditors=[
            make_approve_auditor("mock_openai"),
            make_approve_auditor("mock_anthropic"),
        ],
        runs_dir=Path("runs"),
        experience_dir=Path("."),
    )


async def _run_task(args):
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

    runner = _make_runner(mock=True)
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

    # Print owner summary
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

    runner = _make_runner(mock=True)
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


def main():
    parser = argparse.ArgumentParser(description="Governed AI Execution System — Phase 1")
    subparsers = parser.add_subparsers(dest="command")

    # dry-run
    subparsers.add_parser("dry-run", help="Run full cycle with mock providers")

    # run
    run_parser = subparsers.add_parser("run", help="Run a single task")
    run_parser.add_argument("--title", required=True)
    run_parser.add_argument("--stage", required=True, help="Roadmap stage (e.g. R1, 5.5)")
    run_parser.add_argument("--why-now", required=True, dest="why_now")
    run_parser.add_argument("--risk", required=True, choices=["low", "semi", "core"])
    run_parser.add_argument("--description", default="")
    run_parser.add_argument("--depends-on", nargs="*", dest="depends_on")
    run_parser.add_argument("--keywords", nargs="*")
    run_parser.add_argument("--files", nargs="*")

    args = parser.parse_args()

    if args.command == "dry-run":
        asyncio.run(_dry_run(args))
    elif args.command == "run":
        asyncio.run(_run_task(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
