"""
strojka.py — "ИИ-стройка" natural language entry point.

Usage:
    python orchestrator/strojka.py "спроектировать систему уведомлений"
    python orchestrator/strojka.py "следующая задача по роадмапу"
    python orchestrator/strojka.py "обсудить архитектуру нового модуля"

What happens:
    1. Claude API reads your text + Roadmap + Master Plan
    2. Determines: what to do, risk level, roadmap stage
    3. Creates manifest automatically
    4. Runs full orchestrator cycle (M1 → M2 → M3 → M4 if LOW)
    5. Reports result

Autonomy by risk:
    LOW  → does everything, you get notified when done
    SEMI → shows plan, waits for your OK, then builds
    CORE → full governance pipeline (Gemini critic + Opus judge)
"""
from __future__ import annotations

import json
import os
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"
MANIFEST_PATH = ORCH_DIR / "manifest.json"
ROADMAP_PATH = ROOT / "docs" / "EXECUTION_ROADMAP_v2_3.md"
MASTERPLAN_PATH = ROOT / "docs" / "MASTER_PLAN_v1_9_2.md"
STATE_PATH = ROOT / "docs" / "autopilot" / "STATE.md"

# How much of roadmap/masterplan to feed to NLU (chars)
CONTEXT_LIMIT = 6000

_NLU_SYSTEM_PROMPT = """\
You are the intake parser for the Biretos AI Construction Site ("ИИ-стройка").

Your job: take a human instruction in any language and produce a structured JSON task.

You receive:
- The user's instruction (natural language)
- Current project state (from STATE.md)
- Execution Roadmap (stages and current position)

Rules:
1. Output ONLY valid JSON, no prose.
2. Determine the task_id: short slug like "NOTIFY-DESIGN" or "ROADMAP-NEXT".
3. Determine sprint_goal: clear 1-2 sentence description of what to do.
4. Determine risk_class: LOW (only Tier-3, no Core touch), SEMI (Tier-2 body or financial), CORE (Tier-1 adjacent, schema, FSM).
5. Determine roadmap_stage: which stage from Roadmap this belongs to (e.g. "R1", "8.1", "Phase 7"). Use "NEW" if it's a new idea not in roadmap.
6. Determine task_type: "implement" (write code), "design" (architecture only), "research" (explore options), "roadmap_next" (pick next from roadmap).
7. If the user says "следующая задача" or "next task" or similar, read the Roadmap current position and pick the next incomplete stage.
8. CRITICAL: Only do EXACTLY what the user asked. Do NOT invent tasks from STATE.md context. STATE.md is for context only — the user's instruction is the sole source of what to do.
9. NEVER start enrichment, batch runs, or data processing unless the user EXPLICITLY asked for it.

Output schema:
{
  "task_id": "SHORT-SLUG",
  "sprint_goal": "Clear description of what to do",
  "risk_class": "LOW",
  "roadmap_stage": "R1",
  "task_type": "implement",
  "auto_execute": true
}

Set auto_execute=true for LOW implement tasks, false for everything else.
"""


def _load_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        try:
            from dotenv import dotenv_values
            env_path = ROOT / "auditor_system" / "config" / ".env.auditors"
            key = dotenv_values(env_path).get("ANTHROPIC_API_KEY", "")
        except Exception:
            pass
    return key


def _read_truncated(path: Path, limit: int = CONTEXT_LIMIT) -> str:
    if not path.exists():
        return "(file not found)"
    text = path.read_text(encoding="utf-8")
    if len(text) > limit:
        return text[:limit] + "\n[TRUNCATED]"
    return text


def _extract_json(text: str) -> dict:
    import re
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON in response")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("Unbalanced braces")


def parse_intent(user_text: str) -> dict:
    """Call Claude API to parse natural language into structured task."""
    import anthropic

    key = _load_api_key()
    if not key:
        print("ERROR: no ANTHROPIC_API_KEY")
        sys.exit(1)

    state = _read_truncated(STATE_PATH, 3000)
    roadmap = _read_truncated(ROADMAP_PATH, CONTEXT_LIMIT)

    # NLU parsing is always Sonnet — simple JSON extraction, no need for Opus
    client = anthropic.Anthropic(api_key=key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=_NLU_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"## User instruction\n{user_text}\n\n"
                f"## Current state (STATE.md)\n{state}\n\n"
                f"## Roadmap (truncated)\n{roadmap}"
            ),
        }],
    )
    raw = response.content[0].text
    return _extract_json(raw)


def create_manifest(task: dict) -> None:
    """Write parsed task into orchestrator manifest.

    Also clears stale execution artifacts from previous tasks
    so the classifier doesn't inherit old changed_files.
    """
    # Clean stale artifacts from previous task
    for stale in ("last_execution_packet.json", "last_advisor_verdict.json",
                   "last_escalation.json", "orchestrator_directive.md"):
        p = ORCH_DIR / stale
        if p.exists():
            p.unlink()

    manifest = {
        "schema_version": "v1",
        "fsm_state": "ready",
        "current_sprint_goal": task["sprint_goal"],
        "current_task_id": task["task_id"],
        "trace_id": "",
        "attempt_count": 0,
        "last_verdict": None,
        "last_directive_hash": None,
        "pending_packet_id": None,
        "deadline_at": None,
        "default_option_id": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_audit_result": None,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_orchestrator(auto_execute: bool) -> int:
    """Run one orchestrator cycle."""
    import yaml

    # Temporarily set auto_execute in config if needed
    cfg_path = ORCH_DIR / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    original_auto = cfg.get("auto_execute", False)

    if auto_execute and not original_auto:
        cfg["auto_execute"] = True
        cfg_path.write_text(
            yaml.dump(cfg, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

    # Run orchestrator
    env = os.environ.copy()
    key = _load_api_key()
    if key:
        env["ANTHROPIC_API_KEY"] = key
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, str(ORCH_DIR / "main.py")],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
        cwd=str(ROOT),
    )

    # Restore config
    if auto_execute and not original_auto:
        cfg["auto_execute"] = original_auto
        cfg_path.write_text(
            yaml.dump(cfg, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

    # Print output
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        for line in result.stderr.strip().splitlines():
            if line.strip():
                print(f"  {line}", file=sys.stderr)

    return result.returncode


def main():
    if len(sys.argv) < 2:
        print("Usage: python orchestrator/strojka.py \"описание задачи\"")
        print()
        print("Examples:")
        print("  python orchestrator/strojka.py \"следующая задача по роадмапу\"")
        print("  python orchestrator/strojka.py \"спроектировать систему уведомлений\"")
        print("  python orchestrator/strojka.py \"добавить тест для price_pipeline\"")
        sys.exit(0)

    user_text = " ".join(sys.argv[1:])

    print(f"[strojka] Task: {user_text}")
    print(f"[strojka] Parsing intent via Claude API...")

    # Step 1: NLU parse
    task = parse_intent(user_text)
    print(f"[strojka] Parsed:")
    print(f"  task_id:       {task['task_id']}")
    print(f"  sprint_goal:   {task['sprint_goal']}")
    print(f"  risk_class:    {task['risk_class']}")
    print(f"  roadmap_stage: {task['roadmap_stage']}")
    print(f"  task_type:     {task['task_type']}")
    print(f"  auto_execute:  {task.get('auto_execute', False)}")

    # Step 2: Create manifest
    create_manifest(task)
    print(f"[strojka] Manifest created.")

    # Step 3: Autonomy decision
    risk = task["risk_class"].upper()
    auto = task.get("auto_execute", False)

    if risk == "CORE":
        print()
        print("=" * 60)
        print("CORE TASK — full governance pipeline required.")
        print("Orchestrator will run SPEC v3.4 review (Gemini + Opus).")
        print("You will be notified for approval.")
        print("=" * 60)
        auto = False

    if risk == "SEMI" and task["task_type"] != "implement":
        print()
        print("=" * 60)
        print(f"SEMI TASK ({task['task_type']}) — will show plan first.")
        print("Review the directive, then run:")
        print("  python orchestrator/main.py")
        print("=" * 60)
        auto = False

    # Step 4: Run orchestrator
    print()
    print(f"[strojka] Running orchestrator (auto_execute={auto})...")
    print("=" * 60)
    code = run_orchestrator(auto_execute=auto)
    print("=" * 60)

    if code == 0:
        print(f"[strojka] Done. Check results:")
        print(f"  Directive: orchestrator/orchestrator_directive.md")
        print(f"  Manifest:  orchestrator/manifest.json")
        if auto:
            print(f"  Packet:    orchestrator/last_execution_packet.json")
    else:
        print(f"[strojka] Orchestrator exited with code {code}")

    return code


if __name__ == "__main__":
    sys.exit(main())
