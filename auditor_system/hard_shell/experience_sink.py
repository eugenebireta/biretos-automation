"""
hard_shell/experience_sink.py — DPO-ready JSONL после owner verdict.

Триггер записи: строго ПОСЛЕ owner verdict или post-audit (SPEC §6.3).
Запись ДО approve загрязняет датасет.

Approved → experience_log/*.jsonl
Rejected/failed → anti_patterns/*.jsonl

Schema version history:
  v1 — hash-only proposals (proposal_hash, no inline text)
  v2 — inline text: proposal_text, revised_proposal_text, critiques_text,
        files_changed, error_detail.  Hashes kept for dedup.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .contracts import ProtocolRun

logger = logging.getLogger(__name__)

EXPERIENCE_SINK_SCHEMA_VERSION = "experience_sink_v2"
_MAX_PROPOSAL_CHARS = 8000
_MAX_CRITIQUES_CHARS = 4000


class ExperienceSink:
    """
    Записывает DPO-ready JSONL после owner verdict.

    Структура (SPEC §6.4):
        experience_log/YYYY-MM.jsonl   ← approved + clean post-audit
        anti_patterns/YYYY-MM.jsonl    ← rejected/failed (negative examples)
    """

    def __init__(self, base_dir: str | Path = "."):
        self.base_dir = Path(base_dir)
        self.exp_dir = self.base_dir / "experience_log"
        self.anti_dir = self.base_dir / "anti_patterns"
        self.exp_dir.mkdir(parents=True, exist_ok=True)
        self.anti_dir.mkdir(parents=True, exist_ok=True)

    def _current_month_file(self, directory: Path) -> Path:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        return directory / f"{month}.jsonl"

    def _proposal_hash(self, text: str) -> str:
        return "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:16]

    @staticmethod
    def _cap(text: str | None, limit: int) -> str | None:
        if text is None:
            return None
        return text[:limit] if len(text) > limit else text

    @staticmethod
    def _format_critiques(verdicts: list) -> str:
        """Compact inline summary of audit verdicts for training data."""
        parts: list[str] = []
        for v in verdicts:
            header = f"[{v.auditor_id}] {v.verdict.value}: {v.summary}"
            issues = "; ".join(
                f"{i.severity.value}/{i.area}: {i.description}"
                for i in v.issues
            )
            parts.append(f"{header}\n  {issues}" if issues else header)
        return "\n".join(parts)

    def _build_record(self, run: ProtocolRun) -> dict:
        """Строит DPO-ready запись (SPEC §6.3 формат) with inline text."""
        cap = self._cap
        # Определяем rejected/chosen solution для DPO
        rejected_solution = None
        chosen_solution = None

        if run.escalated and run.proposal and run.revised_proposal:
            # Sonnet proposal → rejected (провалил Quality Gate)
            # Opus revised → chosen
            rejected_solution = {
                "model": "sonnet",
                "effort": "medium",
                "proposal_hash": self._proposal_hash(run.proposal),
                "proposal_text": cap(run.proposal, _MAX_PROPOSAL_CHARS),
                "issues_found": [
                    {"severity": i.severity.value, "area": i.area, "desc": i.description}
                    for v in run.critiques
                    for i in v.issues
                ],
            }
            chosen_solution = {
                "model": "opus",
                "effort": "high",
                "proposal_hash": self._proposal_hash(run.revised_proposal),
                "proposal_text": cap(run.revised_proposal, _MAX_PROPOSAL_CHARS),
                "issues_found": [
                    {"severity": i.severity.value, "area": i.area, "desc": i.description}
                    for v in run.final_verdicts
                    for i in v.issues
                ],
            }
        else:
            # Один раунд — только chosen
            text = run.revised_proposal or run.proposal
            chosen_solution = {
                "model": run.model_used.value,
                "effort": run.effort.value,
                "proposal_hash": self._proposal_hash(text),
                "proposal_text": cap(text, _MAX_PROPOSAL_CHARS),
                "issues_found": [
                    {"severity": i.severity.value, "area": i.area, "desc": i.description}
                    for v in run.final_verdicts
                    for i in v.issues
                ],
            }

        # Inline critiques for training (compact text)
        critiques_text = cap(
            self._format_critiques(run.critiques),
            _MAX_CRITIQUES_CHARS,
        ) if run.critiques else None
        final_audit_text = cap(
            self._format_critiques(run.final_verdicts),
            _MAX_CRITIQUES_CHARS,
        ) if run.final_verdicts else None

        # Files changed from task declaration (best available at record time)
        files_changed = run.task.affected_files[:30] if run.task.affected_files else []

        return {
            "schema_version": EXPERIENCE_SINK_SCHEMA_VERSION,
            "trace_id": run.trace_id,
            "run_id": run.run_id,
            "task": {
                "stage": run.task.roadmap_stage,
                "risk": run.task.risk.value,
                "type": run.task.title,
                "mutation_surface": sorted(run.surface.effective_surface) if run.surface else [],
            },
            "context_summary": run.task.description or run.task.title,
            "rejected_solution": rejected_solution,
            "chosen_solution": chosen_solution,
            "critiques_text": critiques_text,
            "final_audit_text": final_audit_text,
            "files_changed": files_changed,
            "escalation": run.escalated,
            "escalation_reason": run.escalation_reason or None,
            "escalation_helped": run.escalated and run.owner_verdict == "approved",
            "owner_override": False,
            "owner_verdict": run.owner_verdict,
            "owner_notes": run.owner_notes or None,
            "owner_role": "judge" if run.task.risk.value == "core" else "batch_approver",
            "post_audit_clean": run.post_audit_clean,
            "cost_usd": run.cost_usd,
            "duration_minutes": run.duration_minutes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "surface_mismatch": run.surface.mismatch if run.surface else False,
            "error_detail": run.error_message or None,
        }

    def record(self, run: ProtocolRun) -> None:
        """
        Записывает прогон в experience_log или anti_patterns.
        Вызывать ТОЛЬКО после owner verdict.
        """
        if run.owner_verdict is None:
            raise RuntimeError(
                f"ExperienceSink.record called before owner_verdict is set "
                f"(run_id={run.run_id}). "
                "Record strictly AFTER owner verdict (SPEC §6.3)."
            )

        record = self._build_record(run)
        is_positive = (
            run.owner_verdict == "approved"
            and run.post_audit_clean is not False
        )

        target_dir = self.exp_dir if is_positive else self.anti_dir
        target_file = self._current_month_file(target_dir)

        with open(target_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(
            "experience_sink: recorded run_id=%s verdict=%s positive=%s file=%s",
            run.run_id, run.owner_verdict, is_positive, target_file,
        )
