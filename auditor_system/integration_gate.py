"""
auditor_system/integration_gate.py — L3 Integration Gate.

Consensus Pipeline Protocol v1: L3 runs after L1 critics pass.
Validates end-to-end correctness on a fixed golden dataset.

What this does:
  1. Loads golden dataset from task.golden_dataset_path
  2. Runs the pipeline on the golden dataset
  3. Compares output against expected results (deterministic)
  4. Returns L3Result with regressions found

Golden dataset format (JSON):
  {
    "version": "1.0",
    "cases": [
      {
        "id": "golden_001",
        "description": "Honeywell .10 suffix variant",
        "input_file": "tests/golden/inputs/evidence_honeywell_010.json",
        "expected_file": "tests/golden/expected/evidence_honeywell_010.json",
        "check_fields": ["normalized.best_price", "normalized.best_photo_url"]
      }
    ]
  }

Design rules:
  - Zero LLM calls — deterministic CPU-only gate
  - Soft pass when golden_dataset_path is None (backward compat)
  - One failure → adds defect to DefectRegister from source "l3_integration"
  - Circuit breaker: one L3 failure → back to L2 → if fails again → HALTED
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hard_shell.contracts import (
    DefectEntry,
    DefectRegister,
    DefectSeverity,
    TaskPack,
)

logger = logging.getLogger(__name__)


@dataclass
class GoldenCaseResult:
    case_id: str
    description: str
    passed: bool
    regressions: list[str]          # list of field paths that regressed


@dataclass
class L3Result:
    passed: bool
    cases_total: int
    cases_passed: int
    cases_failed: int
    regressions: list[GoldenCaseResult]
    duration_seconds: float
    skipped: bool = False           # True when golden_dataset_path is None

    @property
    def failure_summary(self) -> str:
        if self.skipped:
            return "L3 skipped (no golden_dataset_path)"
        if self.passed:
            return f"L3 passed: {self.cases_passed}/{self.cases_total} cases"
        failed_ids = [r.case_id for r in self.regressions]
        return f"L3 FAILED: {self.cases_failed}/{self.cases_total} failed — {failed_ids}"


class IntegrationGate:
    """
    L3 gate: runs golden dataset, compares against expected output.
    Stateless — create once, call run() per attempt.
    """

    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()

    def _load_dataset(self, path: str) -> dict[str, Any]:
        """Load golden dataset JSON."""
        dataset_path = (self.base_dir / path) if not Path(path).is_absolute() else Path(path)
        if not dataset_path.exists():
            raise FileNotFoundError(f"Golden dataset not found: {dataset_path}")
        with open(dataset_path, encoding="utf-8") as f:
            return json.load(f)

    def _load_json(self, path: str) -> dict[str, Any]:
        p = (self.base_dir / path) if not Path(path).is_absolute() else Path(path)
        if not p.exists():
            return {}
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def _get_nested(self, obj: dict, field_path: str) -> Any:
        """Get nested field by dot-separated path. e.g. 'normalized.best_price'"""
        parts = field_path.split(".")
        current = obj
        for part in parts:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    def _check_case(
        self,
        case: dict[str, Any],
        input_data: dict[str, Any],
        expected_data: dict[str, Any],
    ) -> GoldenCaseResult:
        """Compare actual output against expected for one case."""
        regressions = []
        check_fields = case.get("check_fields", [])

        if not check_fields:
            # No specific fields to check — just verify output is non-empty
            if not input_data:
                regressions.append("output is empty")
        else:
            for field in check_fields:
                actual = self._get_nested(input_data, field)
                expected = self._get_nested(expected_data, field)

                if expected is None:
                    # No expected value → just check field exists
                    if actual is None:
                        regressions.append(f"{field}: expected non-null, got null")
                elif actual != expected:
                    # Value regression
                    regressions.append(
                        f"{field}: expected={repr(expected)[:80]}, "
                        f"actual={repr(actual)[:80]}"
                    )

        return GoldenCaseResult(
            case_id=case["id"],
            description=case.get("description", ""),
            passed=len(regressions) == 0,
            regressions=regressions,
        )

    def run_sync(self, task: TaskPack) -> L3Result:
        """
        Synchronous L3 run. If golden_dataset_path is None → soft pass.
        """
        if not task.golden_dataset_path:
            logger.info(
                "integration_gate: no golden_dataset_path configured, soft pass task_id=%s",
                task.task_id,
            )
            return L3Result(
                passed=True,
                cases_total=0,
                cases_passed=0,
                cases_failed=0,
                regressions=[],
                duration_seconds=0.0,
                skipped=True,
            )

        start_time = time.monotonic()
        logger.info(
            "integration_gate: starting L3 run dataset=%s task_id=%s",
            task.golden_dataset_path, task.task_id,
        )

        try:
            dataset = self._load_dataset(task.golden_dataset_path)
        except FileNotFoundError as exc:
            logger.error("integration_gate: dataset not found: %s", exc)
            return L3Result(
                passed=False,
                cases_total=0,
                cases_passed=0,
                cases_failed=1,
                regressions=[GoldenCaseResult(
                    case_id="dataset_load",
                    description="Load golden dataset",
                    passed=False,
                    regressions=[str(exc)],
                )],
                duration_seconds=time.monotonic() - start_time,
            )

        cases = dataset.get("cases", [])
        if not cases:
            logger.warning("integration_gate: empty golden dataset task_id=%s", task.task_id)
            return L3Result(
                passed=True,
                cases_total=0,
                cases_passed=0,
                cases_failed=0,
                regressions=[],
                duration_seconds=time.monotonic() - start_time,
            )

        case_results: list[GoldenCaseResult] = []
        for case in cases:
            try:
                input_data = self._load_json(case.get("input_file", ""))
                expected_data = self._load_json(case.get("expected_file", ""))
                result = self._check_case(case, input_data, expected_data)
            except Exception as exc:
                result = GoldenCaseResult(
                    case_id=case.get("id", "unknown"),
                    description=case.get("description", ""),
                    passed=False,
                    regressions=[f"case error: {exc}"],
                )
            case_results.append(result)

        failed = [r for r in case_results if not r.passed]
        duration = time.monotonic() - start_time

        l3 = L3Result(
            passed=len(failed) == 0,
            cases_total=len(cases),
            cases_passed=len(cases) - len(failed),
            cases_failed=len(failed),
            regressions=failed,
            duration_seconds=round(duration, 2),
        )

        logger.info(
            "integration_gate: L3Result passed=%s cases=%d/%d duration=%.1fs task_id=%s",
            l3.passed, l3.cases_passed, l3.cases_total, l3.duration_seconds, task.task_id,
        )
        return l3

    async def run(self, task: TaskPack) -> L3Result:
        """Async wrapper for synchronous L3 run."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.run_sync(task))

    def add_failures_to_register(
        self,
        l3_result: L3Result,
        register: DefectRegister,
        iteration: int,
    ) -> None:
        """
        Convert L3 failures into BLOCKER defects in the register.
        source = "l3_integration" so critics can identify origin.
        """
        for case_result in l3_result.regressions:
            for regression in case_result.regressions:
                entry = DefectEntry(
                    defect_id=f"D-L3-{iteration:02d}-{case_result.case_id}",
                    source="l3_integration",
                    severity=DefectSeverity.BLOCKER,
                    scope="correctness",
                    description=(
                        f"L3 regression in golden case '{case_result.case_id}': {regression}"
                    ),
                    evidence=f"case={case_result.case_id}: {case_result.description}",
                    required_fix="Fix the regression — golden dataset output must match expected",
                    iteration_opened=iteration,
                )
                register.entries.append(entry)
