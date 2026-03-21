"""
Backoffice External Read Snapshot Store. Phase 6.7 + 6.8 — INV-ERS.

Every external read in the backoffice router MUST be snapshotted here
before the result is returned to the employee.

Idempotent via UNIQUE(trace_id, snapshot_key).
No commit here — caller owns transaction boundary.
"""

from __future__ import annotations

import json
from typing import Any, Dict


def snapshot_external_read(
    db_conn: Any,
    *,
    trace_id: str,
    provider: str,
    entity_type: str,
    entity_id: str,
    snapshot_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Persist one external read result to external_read_snapshots.

    snapshot_key = "{provider}:{entity_type}:{entity_id}"

    Returns:
        {"action": "created", "snapshot_key": ...}
        {"action": "duplicate", "snapshot_key": ...}
    """
    snapshot_key = f"{provider}:{entity_type}:{entity_id}"
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO external_read_snapshots (
                trace_id,
                snapshot_key,
                provider,
                entity_type,
                entity_id,
                snapshot_data
            )
            VALUES (
                %s::uuid,
                %s,
                %s,
                %s,
                %s,
                %s::jsonb
            )
            ON CONFLICT (trace_id, snapshot_key) DO NOTHING
            RETURNING id
            """,
            (
                str(trace_id),
                snapshot_key,
                str(provider),
                str(entity_type),
                str(entity_id),
                json.dumps(snapshot_data, ensure_ascii=False),
            ),
        )
        row = cursor.fetchone()
        if row:
            return {"action": "created", "snapshot_key": snapshot_key}
        return {"action": "duplicate", "snapshot_key": snapshot_key}
    finally:
        cursor.close()
