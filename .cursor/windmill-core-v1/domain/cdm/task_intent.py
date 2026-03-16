"""
TaskIntent — Pydantic model for task engine (Stage 6).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel


class TaskIntent(BaseModel):
    """Validated task intent for job queue / task engine."""

    task_type: str
    payload: Dict[str, Any] = {}
    trace_id: Optional[str] = None
    idempotency_key: Optional[str] = None
