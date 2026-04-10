# M0 Spike Findings
## 2026-04-06

---

## 1. PHYSICAL INTERFACE — RESOLVED

### Question
How does `orchestrator_directive.md` get fed into Claude Code?
(Was flagged as technically incorrect in v1.1: `cat directive.md | claude` broken)

### Answer

```
cat orchestrator/orchestrator_directive.md | claude -p
```

**Why this works:**
- `claude -p` (alias `--print`) enables non-interactive mode
- `--input-format text` (default) reads from stdin when piped
- No TTY issues, no escape sequences, no interactive prompts
- No argument length limit (stdin vs shell argument)
- Supports directives of any size

**Verified from `claude --help`:**
```
--input-format <format>   Input format (only works with --print):
                          "text" (default), or "stream-json"
```

### For structured advisor output (M2)
```
cat directive.md | claude -p --output-format json \
  --json-schema '{"type":"object","properties":{...}}'
```
This enables `ADVISOR_VERDICT_SCHEMA_v1` enforcement at the CLI level — free validation without custom parsing.

### For automation (post-MVP)
```
bash orchestrator/run_cycle.sh
# which does:
#   python orchestrator/main.py          # writes directive
#   cat orchestrator/orchestrator_directive.md | claude -p
#   python orchestrator/collect_packet.py --trace-id <id> --run-pytest
#   python orchestrator/main.py          # next cycle
```

---

## 2. EXECUTION PACKET OWNERSHIP — RESOLVED

### Decision
`collect_packet.py` is source of truth. Claude Code output is optional supplementary input.

### What collect_packet.py does
1. `git diff --name-only <base_commit> HEAD` → `changed_files`
2. `git diff <base_commit> HEAD -- *.py *.json *.yaml *.md` → `diff_summary` (truncated to 15K chars)
3. `git merge-base HEAD origin/master` → `base_commit` (auto-resolved if not provided)
4. Optional: `pytest --tb=no -q` → `test_results`
5. Path-based tier classification → `affected_tiers`
6. Writes valid `EXECUTION_PACKET_SCHEMA_v1` JSON

### Error handling
- `git` fails → fallback to `git diff HEAD` (uncommitted changes)
- `pytest` timeout (120s) → `test_results: {error: -1, _note: "timeout"}`
- Any collection error → `status: collection_failed` (never crashes)

### collect_packet.py does NOT
- Run Claude Code
- Write code or tests
- Make decisions about what to do next
- Require network or external API

---

## 3. FSM TRANSITION TABLE — DEFINED

| current_state       | event               | next_state          |
|---------------------|---------------------|---------------------|
| ready               | directive_written   | awaiting_execution  |
| ready               | task_completed      | completed           |
| ready               | error_detected      | error               |
| ready               | cycle_start         | ready               |
| awaiting_execution  | packet_received     | ready               |
| awaiting_execution  | error_detected      | error               |
| awaiting_execution  | cycle_start         | awaiting_execution  |
| awaiting_owner_reply| owner_replied       | ready               |
| awaiting_owner_reply| cycle_start         | awaiting_owner_reply|
| error               | owner_replied       | ready               |
| error               | cycle_start         | error               |
| completed           | cycle_start         | completed           |

**Terminal states:** `completed` (reset via manifest edit for next task)
**Error recovery:** owner sets `fsm_state: ready` in manifest.json after resolving issue

---

## 4. ROUND-TRIP PROTOTYPE — VERIFIED

```
python orchestrator/main.py init            # creates manifest.json
python orchestrator/main.py                 # writes directive, state → awaiting_execution
  → output: trace_id=orch_20260406T205755Z_9512c6
  → file: orchestrator/orchestrator_directive.md

# [owner feeds directive to Claude Code]
cat orchestrator/orchestrator_directive.md | claude -p

# [post-processor collects result]
python orchestrator/collect_packet.py \
  --trace-id orch_20260406T205755Z_9512c6 \
  --run-pytest

python orchestrator/main.py                 # reads packet, state → ready
```

One complete roundtrip prototype verified locally.

---

## 5. BASE_COMMIT STRATEGY

Auto-resolution chain (in `collect_packet._resolve_base_commit`):
1. `git merge-base HEAD origin/master` (preferred)
2. `git merge-base HEAD origin/main`
3. `git merge-base HEAD master`
4. `git merge-base HEAD main`
5. `HEAD~1` (fallback)

Owner can override via `--base-commit <sha>` or `config.yaml: base_commit`.
Directive schema includes `base_commit` field for explicit tracking.

---

## 6. WHAT M0 DID NOT BUILD (→ M1-M4)

| Component | Status |
|-----------|--------|
| Claude Advisor (API call) | M2 |
| Decision Synthesizer (rule engine) | M3 |
| Task Classifier | M1 |
| Context Pruner | M1 |
| Executor Bridge (full intent generation) | M4 |
| Orchestrator Inbox | M5 |

`main.py` currently writes a stub directive. Real task-specific intent comes from Claude Advisor in M2.

---

## 7. DELIVERABLES

| File | Purpose |
|------|---------|
| `orchestrator/__init__.py` | Package marker |
| `orchestrator/main.py` | One-cycle runner + FSM skeleton |
| `orchestrator/collect_packet.py` | Deterministic post-processor |
| `orchestrator/config.yaml` | Thresholds and limits |
| `orchestrator/schemas/directive_v1.json` | JSON Schema (draft-07) |
| `orchestrator/schemas/execution_packet_v1.json` | JSON Schema (draft-07) |
| `orchestrator/spike_findings.md` | This document |
| `tests/orchestrator/test_collect_packet.py` | 30 mocked tests |

Tests: **30/30 PASS** (zero live API, zero live git, zero live pytest)
Existing suite: **509/509 PASS** (no regression)

---

END OF M0 SPIKE
