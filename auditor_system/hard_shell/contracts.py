"""
hard_shell/contracts.py — Pydantic-контракты для всех артефактов системы.

Эти модели — единственный источник правды о структуре данных.
Изменение полей = нарушение контракта → обновить все consumers.
"""
from __future__ import annotations

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

    def mark_finished(self) -> None:
        self.finished_at = datetime.now(timezone.utc)

    @property
    def duration_minutes(self) -> float | None:
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds() / 60
        return None
