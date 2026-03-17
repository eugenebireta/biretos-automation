"""
Tier-2. NOT Tier-1 frozen.
Pure models only — no DB, no side-effects, no imports from Tier-1 modules.

CDM v2 domain contracts for the Core Layer mutation pipeline.

TaskIntent  — represents a mutation request entering dispatch_action().
              payload is intentionally Dict[str, Any] in v1;
              per-action payload schemas are Task 5.2 scope.

ActionSnapshot — represents the governance-approved action snapshot
                 persisted in review_cases.action_snapshot.
                 Enforces schema_version=1 and the current supported
                 leaf worker set at the model boundary (Fail Loud).
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class TaskIntent(BaseModel):
    """
    Canonical mutation request entering the dispatch pipeline.

    Maps to the ``action: Dict[str, Any]`` currently passed to
    ``dispatch_action()`` in ru_worker/dispatch_action.py.

    trace_id must be non-empty (min_length=1) — empty trace IDs are
    rejected at the model boundary per Fail Loud.

    payload and metadata are untyped Dict[str, Any] in v1.
    Per-action payload schemas are Task 5.2 scope.
    """

    trace_id: str = Field(..., min_length=1)
    action_type: str
    payload: Dict[str, Any]
    source: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None


class ActionSnapshot(BaseModel):
    """
    Governance-approved action snapshot stored in review_cases.action_snapshot.

    Maps to the dict manually validated in governance_executor._execute_live()
    (schema_version check, leaf_worker_type check, leaf_payload presence check,
    external_idempotency_key presence check).

    schema_version is enforced as Literal[1] — a wrong version is rejected at
    the model boundary rather than at a downstream manual check (Fail Loud).

    leaf_worker_type is enforced as Literal["cdek_shipment"] — the only
    supported leaf worker as of v1. When a new leaf worker is added, update
    this Literal and SUPPORTED_LEAF_WORKERS in governance_executor.py together.
    """

    schema_version: Literal[1]
    leaf_worker_type: Literal["cdek_shipment"]
    leaf_payload: Dict[str, Any]
    external_idempotency_key: str
