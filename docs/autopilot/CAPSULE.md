# Task Capsule

Task_ID: meta-orchestrator-m4-executor-bridge
Risk: SEMI
Date: 2026-04-07
Branch: feat/rev-r1-catalog
PR: https://github.com/eugenebireta/biretos-automation/pull/38
Status: COMPLETED — committed e3c5b77, pushed to feat/rev-r1-catalog

## What was built

M4 Executor Bridge closes the automation loop for the Meta Orchestrator.
When `auto_execute: true` in config.yaml, `python orchestrator/main.py` now
runs end-to-end: intake → classify → advisor → synthesizer → directive → claude --print → collect_packet.

New modules:
- `orchestrator/executor_bridge.py` — `run()` + `run_with_collect()`:
  - calls `claude --print --permission-mode bypassPermissions --no-session-persistence`
  - stdin = directive file; stdout/stderr captured
  - structured error taxonomy:
    - PERMANENT (retriable=False): FileNotFoundError, PermissionError, UnicodeDecodeError
    - TRANSIENT (retriable=True): subprocess failure, timeout, generic Exception
  - structured logging on all paths (logger.error/logger.info/logger.warning)
  - `run_with_collect()`: auto-calls `collect_packet.collect()` on success; collect failure non-fatal
- `tests/orchestrator/test_executor_bridge.py` — 43 deterministic tests; subprocess.run + collect_packet mocked

Updated:
- `orchestrator/main.py` — `_run_executor_bridge` helper; in cmd_cycle: if auto_execute → run bridge,
  advance FSM to ready on success; keep awaiting_execution + print manual fallback on failure
- `orchestrator/config.yaml` — `auto_execute: false`, `auto_pytest: false`, `executor_timeout_seconds: 600`

## Governance

SEMI risk. Two-round audit via auditor_system API (Gemini 3.1 Pro CRITIC + Opus 4.6 JUDGE).
Result: **BATCH_APPROVAL** (quality gate passed).
Key issues addressed vs round 1: removed sys.path.insert inside function, added structured
logging, distinguished PERMANENT error classes (PermissionError, UnicodeDecodeError).

## Coverage

308/308 orchestrator tests PASS (zero regression).
43/43 executor_bridge tests PASS.

## Next

Revenue R1 track (B): price scout, photo recovery, export pipeline on feat/rev-r1-catalog.
