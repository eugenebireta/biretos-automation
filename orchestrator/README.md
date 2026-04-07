# orchestrator/

Autonomous sprint orchestrator. Reads state, classifies risk, advises next step,
synthesizes decision, then executes or gates.

## How to run

```
python orchestrator/main.py
```

## What it reads

- `orchestrator/manifest.json` — FSM state + sprint goal
- `orchestrator/last_execution_packet.json` — executor output
- `orchestrator/last_advisor_verdict.json` — advisor recommendation
- `shadow_log/experience_unified_*.jsonl` — past lessons (injected as context)

## What it writes

- `orchestrator/orchestrator_directive.md` — next instruction for executor
- `orchestrator/last_audit_result.json` — CORE_GATE audit outcome

## FSM states

`ready` → `awaiting_execution` → `audit_in_progress` → `audit_passed` / `blocked` / `needs_owner_review`
