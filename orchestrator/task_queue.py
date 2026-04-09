"""
task_queue.py — P2: Persistent task queue for the Meta Orchestrator.

Allows enqueueing multiple tasks so the orchestrator auto-advances to the
next task when the current one completes cleanly (fsm_state=ready, last_verdict=None).

Queue file: orchestrator/task_queue.json
Each entry: {"task_id": str, "sprint_goal": str, "risk_class": str,
             "added_at": ISO8601, "priority": int}

Auto-advance policy:
  - Only when auto_execute=true AND risk_class=LOW (SEMI/CORE pause for owner)
  - Picks highest-priority item, then FIFO within same priority
  - Resets attempt_count=0, retry_count=0 on advance

CLI usage:
  python orchestrator/task_queue.py add <task_id> <sprint_goal> [--risk LOW|SEMI|CORE]
  python orchestrator/task_queue.py list
  python orchestrator/task_queue.py pop               # show + remove next task
  python orchestrator/task_queue.py clear
  python orchestrator/task_queue.py next              # show without removing
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_ORCH_DIR = Path(__file__).resolve().parent
QUEUE_PATH = _ORCH_DIR / "task_queue.json"
MANIFEST_PATH = _ORCH_DIR / "manifest.json"

VALID_RISK = {"LOW", "SEMI", "CORE"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Queue I/O
# ---------------------------------------------------------------------------

def load_queue() -> list[dict]:
    """Load queue from disk. Returns empty list if file missing or corrupt."""
    if not QUEUE_PATH.exists():
        return []
    try:
        data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.error("task_queue.json is not a list — resetting")
            return []
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load task_queue.json: %s", exc)
        return []


def save_queue(queue: list[dict]) -> None:
    """Save queue to disk atomically."""
    tmp = QUEUE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(QUEUE_PATH)


def _sort_key(entry: dict) -> tuple:
    """Sort by priority DESC, then added_at ASC (FIFO within same priority)."""
    return (-int(entry.get("priority", 0)), entry.get("added_at", ""))


# ---------------------------------------------------------------------------
# Core queue operations
# ---------------------------------------------------------------------------

def enqueue(
    task_id: str,
    sprint_goal: str,
    risk_class: str = "LOW",
    priority: int = 0,
) -> dict:
    """Add a task to the queue. Returns the new entry.

    Args:
        task_id: Unique identifier for the task
        sprint_goal: Human-readable description of what to do
        risk_class: LOW | SEMI | CORE
        priority: Higher = picked first (default 0)

    Raises:
        ValueError: if task_id empty or risk_class invalid
    """
    if not task_id or not task_id.strip():
        raise ValueError("task_id must not be empty")
    if risk_class.upper() not in VALID_RISK:
        raise ValueError(f"risk_class must be one of {VALID_RISK}, got: {risk_class!r}")

    entry = {
        "task_id": task_id.strip(),
        "sprint_goal": sprint_goal.strip(),
        "risk_class": risk_class.upper(),
        "priority": int(priority),
        "added_at": _now(),
    }
    queue = load_queue()
    queue.append(entry)
    save_queue(sorted(queue, key=_sort_key))
    logger.info(
        json.dumps({"event": "task_enqueued", "task_id": task_id,
                    "risk": risk_class, "queue_depth": len(queue)}, ensure_ascii=False)
    )
    return entry


def peek_next() -> dict | None:
    """Return the next task to run without removing it. None if queue empty."""
    queue = load_queue()
    if not queue:
        return None
    return sorted(queue, key=_sort_key)[0]


def dequeue() -> dict | None:
    """Remove and return the next task. None if queue empty."""
    queue = load_queue()
    if not queue:
        return None
    sorted_queue = sorted(queue, key=_sort_key)
    next_task = sorted_queue[0]
    queue.remove(next_task)
    save_queue(queue)
    logger.info(
        json.dumps({"event": "task_dequeued", "task_id": next_task.get("task_id"),
                    "remaining": len(queue)}, ensure_ascii=False)
    )
    return next_task


def remove_by_id(task_id: str) -> bool:
    """Remove a specific task by task_id. Returns True if removed."""
    queue = load_queue()
    new_queue = [t for t in queue if t.get("task_id") != task_id]
    if len(new_queue) == len(queue):
        return False
    save_queue(new_queue)
    return True


def clear_queue() -> int:
    """Clear all queued tasks. Returns number of tasks removed."""
    queue = load_queue()
    count = len(queue)
    save_queue([])
    logger.info(json.dumps({"event": "queue_cleared", "removed": count}, ensure_ascii=False))
    return count


def queue_depth() -> int:
    """Return current queue depth."""
    return len(load_queue())


# ---------------------------------------------------------------------------
# Auto-advance: called from main.py after clean task completion
# ---------------------------------------------------------------------------

def try_auto_advance(manifest: dict, auto_execute: bool = False) -> dict | None:
    """Attempt to advance to the next queued task.

    Called when:
    - fsm_state == "ready"
    - last_verdict == None  (clean completion, no error/failure)
    - auto_execute is True

    Policy:
    - SEMI/CORE tasks: enqueue but do NOT auto-advance (owner must review first)
    - LOW tasks: auto-advance immediately
    - Returns the new task entry if advanced, None if not advanced

    Args:
        manifest: current manifest dict (MUTATED in place)
        auto_execute: from config.yaml auto_execute

    Returns:
        Next task entry if advanced, None otherwise
    """
    if not auto_execute:
        return None

    if manifest.get("fsm_state") != "ready" or manifest.get("last_verdict") is not None:
        return None

    next_task = peek_next()
    if next_task is None:
        return None

    risk = next_task.get("risk_class", "LOW")
    if risk in ("SEMI", "CORE"):
        logger.info(
            json.dumps({
                "event": "auto_advance_skipped",
                "task_id": next_task.get("task_id"),
                "risk": risk,
                "reason": "SEMI/CORE requires owner review before auto-advance",
            }, ensure_ascii=False)
        )
        return None  # Owner must manually confirm SEMI/CORE

    # Consume from queue
    task = dequeue()
    if task is None:
        return None  # Race condition guard

    # Update manifest for new task
    manifest["current_task_id"] = task["task_id"]
    manifest["current_sprint_goal"] = task["sprint_goal"]
    manifest["_last_risk_class"] = task["risk_class"]
    manifest["attempt_count"] = 0
    manifest["retry_count"] = 0
    manifest.pop("_retry_reason", None)
    manifest.pop("_semi_audit_critique", None)
    manifest["last_verdict"] = None
    manifest["last_audit_result"] = None
    manifest["updated_at"] = _now()
    # fsm_state stays "ready" — next main.py cycle will pick it up

    logger.info(
        json.dumps({
            "event": "auto_advanced",
            "task_id": task["task_id"],
            "sprint_goal": task["sprint_goal"][:80],
            "risk": task["risk_class"],
            "queue_remaining": queue_depth(),
        }, ensure_ascii=False)
    )
    return task


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_add(args: list[str]) -> None:
    if len(args) < 2:
        print("Usage: task_queue.py add <task_id> <sprint_goal> [--risk LOW|SEMI|CORE] [--priority N]")
        sys.exit(1)
    task_id = args[0]
    # Sprint goal may be multi-word — collect until next flag
    goal_parts = []
    risk = "LOW"
    priority = 0
    i = 1
    while i < len(args):
        if args[i] == "--risk" and i + 1 < len(args):
            risk = args[i + 1]
            i += 2
        elif args[i] == "--priority" and i + 1 < len(args):
            priority = int(args[i + 1])
            i += 2
        else:
            goal_parts.append(args[i])
            i += 1
    sprint_goal = " ".join(goal_parts) if goal_parts else task_id
    entry = enqueue(task_id, sprint_goal, risk_class=risk, priority=priority)
    print(f"Enqueued: {entry['task_id']} ({entry['risk_class']}, priority={entry['priority']})")
    print(f"Queue depth: {queue_depth()}")


def _cmd_list() -> None:
    queue = sorted(load_queue(), key=_sort_key)
    if not queue:
        print("Queue is empty.")
        return
    print(f"{'#':<3} {'TASK_ID':<30} {'RISK':<6} {'PRI':<4} {'ADDED_AT':<26} SPRINT_GOAL")
    print("-" * 100)
    for i, t in enumerate(queue, 1):
        goal_preview = t.get("sprint_goal", "")[:40]
        print(f"{i:<3} {t.get('task_id', ''):<30} {t.get('risk_class', ''):<6} "
              f"{t.get('priority', 0):<4} {t.get('added_at', ''):<26} {goal_preview}")


def _cmd_pop() -> None:
    task = dequeue()
    if task is None:
        print("Queue is empty — nothing to pop.")
        return
    print(f"Dequeued: {task['task_id']}")
    print(json.dumps(task, indent=2, ensure_ascii=False))
    print(f"Remaining: {queue_depth()}")


def _cmd_next() -> None:
    task = peek_next()
    if task is None:
        print("Queue is empty.")
        return
    print(f"Next task: {task['task_id']} ({task['risk_class']}, priority={task.get('priority', 0)})")
    print(f"Sprint goal: {task.get('sprint_goal', '')}")


def _cmd_clear() -> None:
    removed = clear_queue()
    print(f"Cleared {removed} task(s) from queue.")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        _cmd_list()
        return
    cmd = args[0]
    rest = args[1:]
    if cmd == "add":
        _cmd_add(rest)
    elif cmd == "list":
        _cmd_list()
    elif cmd == "pop":
        _cmd_pop()
    elif cmd == "next":
        _cmd_next()
    elif cmd == "clear":
        _cmd_clear()
    elif cmd == "depth":
        print(queue_depth())
    else:
        print(f"Unknown command: {cmd}")
        print("Commands: add, list, pop, next, clear, depth")
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    main()
