#!/usr/bin/env python3
"""
Replay CLI for RFQ Pipeline

Usage:
    python replay.py <trace_id>

Purpose:
    Replay failed RFQ tasks by trace_id.
    
MINIMAL OPERATIONAL SPINE — DO NOT EXTEND
- No complex retry logic
- No queue management
- No workflow orchestration
- Simple replay only
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "ru_worker"))

import psycopg2
from psycopg2.extras import RealDictCursor

from config import get_config
from ru_worker.ru_worker import execute_rfq_v1_from_ocr
from ru_worker.rfq_idempotency import (
    TRACE_ID_PAYLOAD_KEY,
    RFQ_ID_PAYLOAD_KEY,
    resolve_execution_mode,
)
from ru_worker.pii_dependency_registry import PII_STEP_CLASSIFICATIONS


TASK_TO_STEP = {
    "rfq_v1": "execute_rfq_v1_from_ocr",
}

# Static dependency graph for replay propagation.
STEP_DEPENDENCIES = {
    "execute_invoice_create": [],
    "execute_cdek_shipment": ["execute_invoice_create"],
    "execute_rfq_v1_from_ocr": [],
}


def _trace_has_pii_redaction(conn, trace_id: str) -> bool:
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT 1
            FROM control_decisions
            WHERE trace_id = %s::uuid
              AND gate_name = 'pii_redaction'
              AND verdict = 'APPLIED'
            LIMIT 1
            """,
            (trace_id,),
        )
        return cursor.fetchone() is not None
    except Exception:
        # Backward compatible for databases without control_decisions table.
        return False
    finally:
        cursor.close()


def _is_transitive_dependent(step_name: str, visited=None) -> bool:
    visited = visited or set()
    if step_name in visited:
        return False
    visited.add(step_name)
    classification = PII_STEP_CLASSIFICATIONS.get(step_name, "PII_INDEPENDENT")
    if classification == "PII_DEPENDENT":
        return True
    for dep in STEP_DEPENDENCIES.get(step_name, []):
        dep_class = PII_STEP_CLASSIFICATIONS.get(dep, "PII_INDEPENDENT")
        if dep_class == "PII_DEPENDENT":
            return True
        if _is_transitive_dependent(dep, visited=visited):
            return True
    return False


def _should_skip_for_pii_redaction(step_name: str, trace_is_redacted: bool) -> bool:
    if not trace_is_redacted:
        return False
    classification = PII_STEP_CLASSIFICATIONS.get(step_name, "PII_INDEPENDENT")
    if classification == "PII_DEPENDENT":
        return True
    if classification == "PII_TRANSITIVE":
        return True
    return _is_transitive_dependent(step_name)


def _load_recorded_outcome(conn, trace_id: str) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT result
            FROM job_queue
            WHERE trace_id = %s::uuid
              AND status = 'completed'
              AND result IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (trace_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        result = row.get("result")
        if isinstance(result, str):
            return json.loads(result)
        if isinstance(result, dict):
            return result
        return None
    except Exception:
        return None
    finally:
        cursor.close()


def replay_task(trace_id: str, price_only: bool = False, force: bool = False) -> None:
    """
    Replay a failed task by trace_id.
    
    Args:
        trace_id: UUID of the task to replay
    
    Logic:
        1. SELECT latest task FROM tasks WHERE trace_id = ?
        2. Resolve mode via rfq_idempotency.resolve_execution_mode()
        3. Run full replay or price-only re-enrich
    """
    # Validate trace_id format
    try:
        UUID(trace_id)
    except ValueError:
        print(f"ERROR: Invalid trace_id format: {trace_id}")
        print("Expected: UUID format (e.g., 123e4567-e89b-12d3-a456-426614174000)")
        sys.exit(1)
    
    # Load config
    config = get_config()
    
    # Connect to database
    conn = psycopg2.connect(
        host=config.postgres_host or "localhost",
        port=config.postgres_port or 5432,
        database=config.postgres_db or "biretos_automation",
        user=config.postgres_user or "biretos_user",
        password=config.postgres_password
    )
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Fetch task by trace_id
        cursor.execute(
            """
            SELECT id, trace_id, task_type, status, payload, error, created_at
            FROM tasks
            WHERE trace_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (trace_id,)
        )
        
        task = cursor.fetchone()
        
        if not task:
            print(f"ERROR: No task found with trace_id: {trace_id}")
            sys.exit(1)
        
        print(f"Found task:")
        print(f"  Task ID: {task['id']}")
        print(f"  Trace ID: {task['trace_id']}")
        print(f"  Type: {task['task_type']}")
        print(f"  Status: {task['status']}")
        print(f"  Created: {task['created_at']}")
        
        if task['status'] != 'failed' and not force:
            print(f"\nERROR: Task status is '{task['status']}', not 'failed'")
            print("Use --force to replay non-failed tasks.")
            sys.exit(1)
        
        if task['error']:
            print(f"  Error: {task['error'][:200]}")

        step_name = TASK_TO_STEP.get(task["task_type"], task["task_type"])
        trace_is_redacted = _trace_has_pii_redaction(conn, trace_id)
        if _should_skip_for_pii_redaction(step_name, trace_is_redacted):
            recorded_outcome = _load_recorded_outcome(conn, trace_id)
            print("\nReplay outcome: REPLAY_SKIPPED_MATCH")
            print(f"  Step: {step_name}")
            print("  Reason: pii_redaction")
            print("  partial_replay: true")
            if recorded_outcome is not None:
                print(f"  mock_result_available: true")
            else:
                print(f"  mock_result_available: false")
            return
        
        # Parse payload and inject infra key
        payload = dict(task['payload']) if isinstance(task['payload'], dict) else task['payload']
        if isinstance(payload, str):
            payload = json.loads(payload)
        payload[TRACE_ID_PAYLOAD_KEY] = trace_id

        mode = resolve_execution_mode(conn, payload)

        if price_only:
            if not mode.existing_rfq_id:
                print("ERROR: --price-only requires existing RFQ for this trace_id.")
                print("Run full replay first.")
                sys.exit(1)
            payload[RFQ_ID_PAYLOAD_KEY] = str(mode.existing_rfq_id)
            print(f"Replay mode: price-only (rfq_id={mode.existing_rfq_id})")
        else:
            if mode.existing_rfq_id:
                payload[RFQ_ID_PAYLOAD_KEY] = str(mode.existing_rfq_id)
                print(f"Replay mode: re-enrich existing rfq_id={mode.existing_rfq_id}")
            else:
                print("Replay mode: full pipeline")
        
        print(f"\nReplaying task...")
        print(f"  Payload: {json.dumps(payload, indent=2)[:200]}...")
        
        # Replay task
        if task['task_type'] == 'rfq_v1':
            result = execute_rfq_v1_from_ocr(payload, conn)
            
            print(f"\n✓ Replay successful!")
            print(f"  RFQ ID: {result.get('rfq_id')}")
            print(f"  Items count: {result.get('items_count')}")
            print(f"  Trace ID: {result.get('trace_id')}")
            print(f"  Price status: {result.get('price_status')}")
            print(f"  Price items found: {result.get('price_items_found')}")
        else:
            print(f"ERROR: Unknown task type: {task['task_type']}")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n✗ Replay failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        conn.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Replay RFQ task by trace_id")
    parser.add_argument("trace_id", help="Task trace_id (UUID)")
    parser.add_argument(
        "--price-only",
        action="store_true",
        help="Run only price re-enrichment for existing rfq_id",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replay even if task status is not failed",
    )
    args = parser.parse_args()

    replay_task(args.trace_id, price_only=args.price_only, force=args.force)


if __name__ == "__main__":
    main()
