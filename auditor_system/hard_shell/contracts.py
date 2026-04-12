"""
hard_shell/contracts.py — Pydantic-контракты для всех артефактов системы.

Эти модели — единственный источник правды о структуре данных.
Изменение полей = нарушение контракта → обновить все consumers.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    LOW = "low"
    SEMI = "semi"
    CORE = "core"


class ModelName(str, Enum):
    SONNET = "sonnet"
    OPUS = "opus"
    HAIKU = "haiku"


class EffortLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AuditVerdictValue(str, Enum):
    APPROVE = "approve"
    CONCERNS = "concerns"
    REJECT = "reject"


class ApprovalRoute(str, Enum):
    AUTO_PASS = "auto_pass"
    BATCH_APPROVAL = "batch_approval"
    INDIVIDUAL_REVIEW = "individual_review"
    BLOCKED = "blocked"


class ErrorClass(str, Enum):
    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"


# ---------------------------------------------------------------------------
# Defect Register enums (Consensus Pipeline Protocol v1)
# ---------------------------------------------------------------------------

class DefectSeverity(str, Enum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    NIT = "nit"


class DefectStatus(str, Enum):
    OPEN = "OPEN"
    FIXED_PENDING = "FIXED_PENDING"
    CLOSED = "CLOSED"
    WAIVED = "WAIVED"
    HALTED = "HALTED"


# ---------------------------------------------------------------------------
# Task input
# ---------------------------------------------------------------------------

class TaskPack(BaseModel):
    """Входная задача. Обязательные поля: stage + why_now (anti-drift §18.1)."""
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    title: str
    description: str = ""
    roadmap_stage: str                   # e.g. "5.5", "R1"
    why_now: str                         # обязательно — anti-drift guard
    risk: RiskLevel
    depends_on: list[str] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)
    declared_surface: list[str] = Field(default_factory=list)  # от owner/builder
    affected_files: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    # Consensus Pipeline Protocol v1 fields (optional — system works without them)
    frozen_validation_scripts: list[str] = Field(default_factory=list)
    """Scripts builder cannot modify during repair loop. Touching them = hard block."""
    test_commands: list[str] = Field(default_factory=list)
    """Commands to run for L2 gate (e.g. ['pytest', 'python scripts/export_pipeline.py --dry-run']).
    Empty list = skip L2 gate (backward compatible)."""
    golden_dataset_path: str | None = None
    """Path to golden dataset JSON for L3 gate. None = skip L3 gate."""

    @model_validator(mode="after")
    def require_why_now(self) -> "TaskPack":
        if not self.why_now.strip():
            raise ValueError("why_now is required — anti-drift guard (SPEC §18.1)")
        if not self.roadmap_stage.strip():
            raise ValueError("roadmap_stage is required — anti-drift guard (SPEC §18.1)")
        return self


# ---------------------------------------------------------------------------
# Audit artifacts
# ---------------------------------------------------------------------------

class AuditIssue(BaseModel):
    severity: IssueSeverity
    area: str                   # e.g. "architecture", "security", "test_coverage"
    description: str
    line_ref: str = ""          # опциональная ссылка на код


class AuditVerdict(BaseModel):
    """Ответ одного аудитора. Схема валидируется после каждого API-вызова (§19.3)."""
    auditor_id: str             # "openai" | "anthropic" | "mock_*"
    verdict: AuditVerdictValue
    summary: str
    issues: list[AuditIssue] = Field(default_factory=list)
    schema_valid: bool = True   # False = schema_violation error

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)


# ---------------------------------------------------------------------------
# Quality Gate
# ---------------------------------------------------------------------------

class QualityGateResult(BaseModel):
    passed: bool
    reason: str
    escalation_needed: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Consensus Pipeline Protocol v1 — Defect Register data models
# ---------------------------------------------------------------------------

class DefectEntry(BaseModel):
    """Single defect tracked across repair iterations."""
    defect_id: str
    source: str                     # "gemini" | "anthropic" | "l2_execution" | "l3_integration"
    severity: DefectSeverity
    scope: str                      # "correctness" | "architecture" | "invariants" | "tests" | "safety" | "style"
    description: str
    evidence: str = ""              # concrete line/file/traceback
    required_fix: str = ""
    status: DefectStatus = DefectStatus.OPEN
    validated_by: str | None = None # "l2_rerun" | auditor_id | "judge"
    iteration_opened: int = 0
    iteration_closed: int | None = None

    @classmethod
    def from_audit_issue(
        cls,
        issue: "AuditIssue",
        source: str,
        iteration: int,
        index: int,
    ) -> "DefectEntry":
        """Convert AuditIssue → DefectEntry. Maps severity enums."""
        severity_map = {
            IssueSeverity.CRITICAL: DefectSeverity.BLOCKER,
            IssueSeverity.WARNING: DefectSeverity.MAJOR,
            IssueSeverity.INFO: DefectSeverity.NIT,
        }
        return cls(
            defect_id=f"D-{iteration:02d}-{index:03d}",
            source=source,
            severity=severity_map[issue.severity],
            scope=issue.area,
            description=issue.description,
            evidence=issue.line_ref,
            required_fix=issue.description,
            iteration_opened=iteration,
        )

    def hash_key(self) -> str:
        """Deterministic hash for dedup: severity + scope + description prefix."""
        text = f"{self.severity.value}:{self.scope}:{self.description[:80]}"
        return hashlib.sha256(text.encode()).hexdigest()[:16]


class RepairEntry(BaseModel):
    """Builder's per-defect repair response."""
    defect_id: str
    action: str                     # "FIXED" | "CANNOT_FIX"
    changes: list[str] = Field(default_factory=list)  # ["file.py:42 — replaced X with Y"]
    reason: str | None = None       # mandatory for CANNOT_FIX
    test_evidence: str | None = None  # "pytest test_x::test_y PASSED"


class AssertionResult(BaseModel):
    """Single machine-assertion result from L2 gate."""
    name: str
    expected: str
    actual: str
    status: str                     # "PASS" | "FAIL"


class L2Report(BaseModel):
    """L2 execution gate output. Generated automatically, not by LLM. Max 8KB."""
    exit_code: int = 0
    duration_seconds: float = 0.0
    assertions: list[AssertionResult] = Field(default_factory=list)
    diff_stat: str = ""
    traceback_tail: str | None = None  # last 50 lines stderr if exit_code != 0
    output_sample: str = ""            # first 2KB stdout
    command_run: str = ""

    @property
    def all_pass(self) -> bool:
        return (
            self.exit_code == 0
            and all(a.status == "PASS" for a in self.assertions)
            and self.traceback_tail is None
        )

    @property
    def failure_summary(self) -> str:
        parts = []
        if self.exit_code != 0:
            parts.append(f"exit_code={self.exit_code}")
        failed = [a.name for a in self.assertions if a.status == "FAIL"]
        if failed:
            parts.append(f"failed_assertions={failed}")
        return "; ".join(parts) if parts else "ok"


class DefectRegister(BaseModel):
    """Central defect tracking artifact for the repair loop."""
    run_id: str = ""
    entries: list[DefectEntry] = Field(default_factory=list)

    def add_from_verdicts(
        self,
        verdicts: list["AuditVerdict"],
        iteration: int,
    ) -> None:
        """Add defects from audit verdicts with deduplication."""
        seen: set[str] = {e.hash_key() for e in self.entries}
        idx = len(self.entries)
        for verdict in verdicts:
            for issue in verdict.issues:
                entry = DefectEntry.from_audit_issue(
                    issue, verdict.auditor_id, iteration, idx
                )
                h = entry.hash_key()
                if h not in seen:
                    self.entries.append(entry)
                    seen.add(h)
                    idx += 1

    def add_from_l2_report(self, report: "L2Report", iteration: int) -> None:
        """Convert L2 failures into BLOCKER defects."""
        for assertion in report.assertions:
            if assertion.status == "FAIL":
                entry = DefectEntry(
                    defect_id=f"D-L2-{iteration:02d}-{assertion.name}",
                    source="l2_execution",
                    severity=DefectSeverity.BLOCKER,
                    scope="correctness",
                    description=f"L2 assertion failed: {assertion.name}",
                    evidence=f"expected={assertion.expected}, actual={assertion.actual}",
                    required_fix="Fix the code so the assertion passes",
                    iteration_opened=iteration,
                )
                self.entries.append(entry)
        if report.exit_code != 0 and report.traceback_tail:
            entry = DefectEntry(
                defect_id=f"D-L2-{iteration:02d}-exit_code",
                source="l2_execution",
                severity=DefectSeverity.BLOCKER,
                scope="correctness",
                description=f"L2 execution failed: exit_code={report.exit_code}",
                evidence=(report.traceback_tail or "")[-500:],
                required_fix="Fix the runtime error shown in the traceback",
                iteration_opened=iteration,
            )
            self.entries.append(entry)

    @property
    def open_blockers(self) -> list[DefectEntry]:
        return [
            e for e in self.entries
            if e.status == DefectStatus.OPEN
            and e.severity in (DefectSeverity.BLOCKER, DefectSeverity.MAJOR)
        ]

    @property
    def is_clean(self) -> bool:
        return len(self.open_blockers) == 0

    def mark_fixed_pending(self, defect_id: str) -> None:
        for e in self.entries:
            if e.defect_id == defect_id:
                e.status = DefectStatus.FIXED_PENDING
                return

    def close(self, defect_id: str, validated_by: str, iteration: int) -> None:
        for e in self.entries:
            if e.defect_id == defect_id:
                e.status = DefectStatus.CLOSED
                e.validated_by = validated_by
                e.iteration_closed = iteration
                return

    def waive(self, defect_id: str, validated_by: str) -> None:
        for e in self.entries:
            if e.defect_id == defect_id:
                if e.severity in (DefectSeverity.BLOCKER, DefectSeverity.MAJOR):
                    raise ValueError(
                        f"Cannot waive {e.severity.value} defect {defect_id} — "
                        "only minor/nit can be waived"
                    )
                e.status = DefectStatus.WAIVED
                e.validated_by = validated_by
                return

    def apply_repair_manifest(
        self,
        manifest: list["RepairEntry"],
    ) -> None:
        """Mark defects as FIXED_PENDING based on builder's repair manifest."""
        manifest_map = {r.defect_id: r for r in manifest}
        for e in self.entries:
            if e.status == DefectStatus.OPEN and e.defect_id in manifest_map:
                r = manifest_map[e.defect_id]
                if r.action == "FIXED":
                    e.status = DefectStatus.FIXED_PENDING
                # CANNOT_FIX stays OPEN for critics to handle


# ---------------------------------------------------------------------------
# Surface classification
# ---------------------------------------------------------------------------

class SurfaceClassification(BaseModel):
    classified_surface: set[str] = Field(default_factory=set)  # ContextAssembler (rule-based)
    declared_surface: set[str] = Field(default_factory=set)     # Builder/owner
    mismatch: bool = False
    effective_surface: set[str] = Field(default_factory=set)    # UNION при mismatch

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def compute_effective(self) -> "SurfaceClassification":
        if self.classified_surface != self.declared_surface:
            self.mismatch = True
            # При mismatch берём НАИБОЛЕЕ СТРОГОЕ (union) — §19.2
            self.effective_surface = self.classified_surface | self.declared_surface
        else:
            self.effective_surface = self.classified_surface
        return self


# ---------------------------------------------------------------------------
# Protocol Run — полный прогон
# ---------------------------------------------------------------------------

class ProtocolRun(BaseModel):
    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    trace_id: str = Field(default_factory=lambda: f"trace_{uuid.uuid4().hex[:16]}")
    task: TaskPack
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    # Model selection
    model_used: ModelName = ModelName.SONNET
    effort: EffortLevel = EffortLevel.MEDIUM
    escalated: bool = False
    escalation_reason: str = ""

    # Surface
    surface: SurfaceClassification | None = None

    # Artifacts (сохраняются в RunStore)
    proposal: str = ""
    critiques: list[AuditVerdict] = Field(default_factory=list)
    revised_proposal: str = ""
    final_verdicts: list[AuditVerdict] = Field(default_factory=list)

    # Gate + routing
    quality_gate: QualityGateResult | None = None
    approval_route: ApprovalRoute | None = None

    # Owner
    owner_verdict: str | None = None     # "approved" | "rejected" | "rework"
    owner_notes: str = ""

    # Debate (Phase 3 — shared context + debate layer)
    debate_triggered: bool = False
    debate_verdicts: list[AuditVerdict] = Field(default_factory=list)   # Round 2
    arbiter_verdict: AuditVerdict | None = None                         # Round 3
    arbiter_used: bool = False

    # Post-audit
    post_audit_clean: bool | None = None

    # Cost tracking
    cost_usd: float = 0.0

    # Error tracking
    error_class: ErrorClass | None = None
    error_message: str = ""

    # Consensus Pipeline Protocol v1 — Repair loop state
    defect_register: DefectRegister | None = None
    l2_reports: list[L2Report] = Field(default_factory=list)
    repair_history: list[str] = Field(default_factory=list)  # proposals per repair iteration
    l1_iteration: int = 0          # current L1 (critic) loop iteration
    l2_iteration: int = 0          # current L2 (execution) loop iteration
    halted: bool = False
    halt_reason: str = ""

    def mark_finished(self) -> None:
        self.finished_at = datetime.now(timezone.utc)

    @property
    def duration_minutes(self) -> float | None:
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds() / 60
        return None
