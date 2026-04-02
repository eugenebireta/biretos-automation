"""
hard_shell/context_assembler.py — rule-based mutation_surface classifier.

ContextAssembler определяет classified_surface независимо от Builder.
Это предотвращает занижение риска (SPEC §11.2, §19.2).

OPUS_SURFACES загружены из PROJECT_DNA.md §3 и §4.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .contracts import RiskLevel, SurfaceClassification, TaskPack

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OPUS_SURFACES — из PROJECT_DNA.md §3, §4, §5
# Правило: если задача касается любого из этих surface → Opus high
# ---------------------------------------------------------------------------

# Tier-1 frozen files (PROJECT_DNA §3)
_TIER1_FILES = frozenset({
    ".cursor/windmill-core-v1/maintenance_sweeper.py",
    ".cursor/windmill-core-v1/retention_policy.py",
    ".cursor/windmill-core-v1/domain/reconciliation_service.py",
    ".cursor/windmill-core-v1/domain/reconciliation_verify.py",
    ".cursor/windmill-core-v1/domain/reconciliation_alerts.py",
    ".cursor/windmill-core-v1/domain/structural_checks.py",
    ".cursor/windmill-core-v1/domain/observability_service.py",
    ".cursor/windmill-core-v1/migrations/016_create_reconciliation_audit_log.sql",
    ".cursor/windmill-core-v1/migrations/017_create_reconciliation_suppressions.sql",
    ".cursor/windmill-core-v1/migrations/018_create_reconciliation_alerts.sql",
    ".cursor/windmill-core-v1/migrations/019_add_retention_indexes.sql",
    ".cursor/windmill-core-v1/docs/RETENTION_INVARIANT.md",
    ".cursor/windmill-core-v1/tests/validation/test_phase3_alert_emission.py",
    ".cursor/windmill-core-v1/tests/validation/test_phase3_cache_read_model_contract.py",
    ".cursor/windmill-core-v1/tests/validation/test_phase3_l3_structural_checks.py",
    ".cursor/windmill-core-v1/tests/validation/test_phase3_replay_verify.py",
    ".cursor/windmill-core-v1/tests/validation/test_phase3_structural_safety_contract.py",
    ".cursor/windmill-core-v1/tests/validation/test_phase25_contract_guards.py",
    ".cursor/windmill-core-v1/tests/validation/test_phase25_replay_gate.py",
})

# Pinned API function names (PROJECT_DNA §4)
_PINNED_API_NAMES = frozenset({
    "_derive_payment_status",
    "_extract_order_total_minor",
    "recompute_order_cdek_cache_atomic",
    "update_shipment_status_atomic",
    "_ensure_snapshot_row",
    "InvoiceStatusRequest",
    "ShipmentTrackingStatusRequest",
})

# Keywords → surface mapping
_KEYWORD_SURFACES: dict[str, str] = {
    # Reconciliation
    "reconciliation": "reconciliation",
    "reconciliation_service": "reconciliation",
    "reconciliation_verify": "reconciliation",
    # Guardian
    "guardian": "guardian_logic",
    "invariant": "guardian_logic",
    "taskintent": "guardian_logic",
    "governance": "guardian_logic",
    # Ledger / money
    "ledger": "ledger_money",
    "order_ledger": "ledger_money",
    "payment": "ledger_money",
    "payment_transaction": "ledger_money",
    "tbank": "ledger_money",
    "invoice": "ledger_money",
    # Procurement / SAGA
    "saga": "procurement_saga",
    "procurement": "procurement_saga",
    "reservation": "procurement_saga",
    "irreversible": "procurement_saga",
    # FSM core
    "fsm": "fsm_core_states",
    "state_machine": "fsm_core_states",
    "shipment_status": "fsm_core_states",
    "cdek": "fsm_core_states",
    # Idempotency / replay
    "idempotency": "idempotency_replay",
    "idempotency_key": "idempotency_replay",
    "replay": "idempotency_replay",
    "dedup": "idempotency_replay",
    # Policy packs
    "policy_pack": "policy_packs",
    "policy_rule": "policy_packs",
    "decision_rule": "policy_packs",
}

# Все OPUS_SURFACES (SPEC §11.2)
OPUS_SURFACES = frozenset({
    "tier1_files",
    "tier2_pinned_api",
    "guardian_logic",
    "ledger_money",
    "procurement_saga",
    "reconciliation",
    "fsm_core_states",
    "policy_packs",
    "idempotency_replay",
})


# ---------------------------------------------------------------------------
# ContextAssembler
# ---------------------------------------------------------------------------

class ContextAssembler:
    """
    Rule-based классификация mutation_surface.

    Логика:
    1. Проверяет затронутые файлы → tier1_files, tier2_pinned_api
    2. Проверяет ключевые слова в title/description/keywords → surface map
    3. При неуверенности → safe shift up (Opus)
    4. Dual classification с declared_surface от builder
    """

    def classify(self, task: TaskPack) -> SurfaceClassification:
        """Определяет classified_surface по правилам из DNA."""
        surfaces: set[str] = set()

        # --- Шаг 1: проверка затронутых файлов ---
        for f in task.affected_files:
            normalized = f.replace("\\", "/").lstrip("/")
            if normalized in _TIER1_FILES:
                surfaces.add("tier1_files")
                logger.warning(
                    "context_assembler: tier1_file detected task_id=%s file=%s",
                    task.task_id, f,
                )
            # Проверяем имя файла на pinned API
            for api_name in _PINNED_API_NAMES:
                if api_name.lower() in normalized.lower():
                    surfaces.add("tier2_pinned_api")

        # --- Шаг 2: ключевые слова в тексте задачи ---
        text = " ".join([
            task.title.lower(),
            task.description.lower(),
            " ".join(k.lower() for k in task.keywords),
        ])
        for keyword, surface in _KEYWORD_SURFACES.items():
            if keyword.lower() in text:
                surfaces.add(surface)

        # --- Шаг 3: проверка declared_surface на pinned API имена ---
        for s in task.declared_surface:
            if s.lower() in {a.lower() for a in _PINNED_API_NAMES}:
                surfaces.add("tier2_pinned_api")
            if s in OPUS_SURFACES:
                surfaces.add(s)

        # --- Шаг 4: CORE risk → всегда требует внимания ---
        if task.risk == RiskLevel.CORE:
            # CORE задача без явных поверхностей → safe shift, добавляем guardian_logic
            if not surfaces:
                surfaces.add("guardian_logic")
                logger.info(
                    "context_assembler: CORE task with no explicit surface → safe shift up task_id=%s",
                    task.task_id,
                )

        declared = set(task.declared_surface)
        classification = SurfaceClassification(
            classified_surface=surfaces,
            declared_surface=declared,
        )

        if classification.mismatch:
            logger.warning(
                "context_assembler: surface mismatch task_id=%s classified=%s declared=%s effective=%s",
                task.task_id,
                sorted(classification.classified_surface),
                sorted(classification.declared_surface),
                sorted(classification.effective_surface),
            )

        return classification

    def build_policy_context(
        self,
        task: TaskPack,
        surface: SurfaceClassification,
        docs_base: str | Path = "docs",
    ) -> dict[str, Any]:
        """
        Собирает policy_context для аудиторов.
        Динамически из актуальных документов (SPEC §19.4).
        """
        context: dict[str, Any] = {
            "task_id": task.task_id,
            "roadmap_stage": task.roadmap_stage,
            "risk": task.risk.value,
            "why_now": task.why_now,
            "effective_surface": sorted(surface.effective_surface),
            "surface_mismatch": surface.mismatch,
            "opus_surface_hit": bool(surface.effective_surface & OPUS_SURFACES),
            "tier1_files": sorted(_TIER1_FILES),
            "pinned_api": sorted(_PINNED_API_NAMES),
            "absolute_prohibitions": [
                "No INSERT/UPDATE/DELETE on reconciliation_audit_log, reconciliation_alerts, reconciliation_suppressions",
                "No raw DML on order_ledger, shipments, payment_transactions, reservations, stock_ledger_entries",
                "No import from domain.reconciliation_service, domain.reconciliation_alerts, domain.reconciliation_verify",
                "No ALTER/DROP on reconciliation_* tables in migrations/020+",
                "Tier-3 CANNOT call Tier-2 atomics without Guardian",
            ],
            "revenue_table_rules": [
                "Always prefix: rev_* / stg_* / lot_*",
                "No direct JOIN with Core tables",
                "Read Core only through read-only views",
                "Linear FSM only, max 5 states",
            ],
        }

        # Добавляем предупреждение если surface mismatch
        if surface.mismatch:
            context["surface_mismatch_warning"] = (
                f"Surface mismatch detected! "
                f"Classified: {sorted(surface.classified_surface)}, "
                f"Declared: {sorted(surface.declared_surface)}. "
                f"Using UNION (strictest). Verify task scope."
            )

        return context
