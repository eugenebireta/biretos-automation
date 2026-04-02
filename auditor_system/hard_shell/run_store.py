"""
hard_shell/run_store.py — хранение артефактов прогона в runs/<run_id>/.

Каждый шаг пишет файл сразу. Если процесс упал — артефакты на диске.
Redactor применяется ко всем данным перед записью (§18.6).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from .contracts import AuditVerdict, ProtocolRun, QualityGateResult, ApprovalRoute

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redactor — убирает секреты перед записью (DNA §7, SPEC §18.6)
# ---------------------------------------------------------------------------

_REDACT_PATTERNS = [
    (re.compile(r'(sk-[A-Za-z0-9\-_]{20,})', re.IGNORECASE), "[REDACTED_KEY]"),
    (re.compile(r'(Bearer\s+[A-Za-z0-9\-_\.]{20,})', re.IGNORECASE), "Bearer [REDACTED_KEY]"),
    (re.compile(r'(password["\s:=]+)[^\s,"\'}{]+', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(api[_-]?key["\s:=]+)[^\s,"\'}{]+', re.IGNORECASE), r'\1[REDACTED_KEY]'),
]
_MAX_PAYLOAD_BYTES = 10 * 1024  # 10KB


def _redact(text: str) -> str:
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _redact_obj(obj: Any) -> Any:
    """Рекурсивно редактирует строки в объекте."""
    if isinstance(obj, str):
        if len(obj.encode()) > _MAX_PAYLOAD_BYTES:
            h = hashlib.sha256(obj.encode()).hexdigest()[:16]
            return f"[TRUNCATED:{h}]"
        return _redact(obj)
    if isinstance(obj, dict):
        return {k: _redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_obj(i) for i in obj]
    return obj


# ---------------------------------------------------------------------------
# RunStore
# ---------------------------------------------------------------------------

class RunStore:
    """
    Пишет и читает артефакты в runs/<run_id>/.

    Файловая структура (§4 SPEC):
        runs/<run_id>/
            task_pack.json
            policy_context.json
            builder_proposal.md
            auditor_1_critique.json
            auditor_2_critique.json
            revised_proposal.md
            auditor_1_final.json
            auditor_2_final.json
            quality_gate_result.json
            approval_routing.json
            owner_summary.md
            run_manifest.json  ← финальный манифест прогона
    """

    def __init__(self, base_dir: str | Path = "runs"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        d = self.base_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def _write_json(self, run_id: str, filename: str, data: Any) -> Path:
        path = self.run_dir(run_id) / filename
        redacted = _redact_obj(data)
        path.write_text(json.dumps(redacted, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("RunStore.write run_id=%s file=%s", run_id, filename)
        return path

    def _write_text(self, run_id: str, filename: str, text: str) -> Path:
        path = self.run_dir(run_id) / filename
        path.write_text(_redact(text), encoding="utf-8")
        logger.debug("RunStore.write run_id=%s file=%s", run_id, filename)
        return path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_task(self, run: ProtocolRun) -> None:
        self._write_json(run.run_id, "task_pack.json", run.task.model_dump())

    def save_policy_context(self, run: ProtocolRun, context: dict) -> None:
        self._write_json(run.run_id, "policy_context.json", context)

    def save_proposal(self, run: ProtocolRun) -> None:
        self._write_text(run.run_id, "builder_proposal.md", run.proposal)

    def save_critique(self, run: ProtocolRun, verdict: AuditVerdict, index: int) -> None:
        self._write_json(
            run.run_id,
            f"auditor_{index}_critique.json",
            verdict.model_dump(),
        )

    def save_revised_proposal(self, run: ProtocolRun) -> None:
        self._write_text(run.run_id, "revised_proposal.md", run.revised_proposal)

    def save_final_verdict(self, run: ProtocolRun, verdict: AuditVerdict, index: int) -> None:
        self._write_json(
            run.run_id,
            f"auditor_{index}_final.json",
            verdict.model_dump(),
        )

    def save_quality_gate(self, run: ProtocolRun) -> None:
        if run.quality_gate:
            self._write_json(
                run.run_id,
                "quality_gate_result.json",
                run.quality_gate.model_dump(),
            )

    def save_approval_routing(self, run: ProtocolRun) -> None:
        data = {
            "approval_route": run.approval_route.value if run.approval_route else None,
            "model_used": run.model_used.value,
            "effort": run.effort.value,
            "escalated": run.escalated,
            "escalation_reason": run.escalation_reason,
        }
        self._write_json(run.run_id, "approval_routing.json", data)

    def save_owner_summary(self, run: ProtocolRun, summary_text: str) -> None:
        self._write_text(run.run_id, "owner_summary.md", summary_text)

    def save_manifest(self, run: ProtocolRun) -> None:
        """Финальный манифест прогона — сохраняется при завершении."""
        manifest = {
            "run_id": run.run_id,
            "trace_id": run.trace_id,
            "task_id": run.task.task_id,
            "task_title": run.task.title,
            "roadmap_stage": run.task.roadmap_stage,
            "risk": run.task.risk.value,
            "model_used": run.model_used.value,
            "effort": run.effort.value,
            "escalated": run.escalated,
            "approval_route": run.approval_route.value if run.approval_route else None,
            "owner_verdict": run.owner_verdict,
            "post_audit_clean": run.post_audit_clean,
            "cost_usd": run.cost_usd,
            "duration_minutes": run.duration_minutes,
            "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "surface_mismatch": run.surface.mismatch if run.surface else False,
            "effective_surface": sorted(run.surface.effective_surface) if run.surface else [],
        }
        self._write_json(run.run_id, "run_manifest.json", manifest)

    def list_runs(self) -> list[str]:
        return sorted(p.name for p in self.base_dir.iterdir() if p.is_dir())
