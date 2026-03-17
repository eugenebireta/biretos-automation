# Autopilot FSM v2 (Reference)

Autopilot v2 uses the same architectural pattern as business FSM in `domain/fsm_guards.py`:
explicit states, allowed transitions, guard validation, and caller-applied persistence.

## PHASES

`SCOUT`, `ARCHITECT`, `CRITIC`, `ARCHITECT_V2`, `JUDGE_WAIT`, `PLANNER`, `BUILDER`, `AUDITOR`, `POST_AUDIT_LOGGER`

## STATUSES

`PENDING`, `ACTIVE`, `WAITING_APPROVAL`, `WAITING_JUDGE`, `WAITING_USER_RUN`, `BLOCKED`, `ERROR`

## ALLOWED_TRANSITIONS (core semantic map)

- `(SCOUT, PENDING) -> (SCOUT, ACTIVE)`
- `(SCOUT, ACTIVE) -> (SCOUT, WAITING_APPROVAL)`
- `(SCOUT, WAITING_APPROVAL) -> (ARCHITECT, PENDING)`
- `(ARCHITECT, WAITING_APPROVAL) -> (CRITIC, PENDING)`
- `(CRITIC, WAITING_APPROVAL) -> (PLANNER, PENDING)` or `(ARCHITECT_V2, PENDING)`
- `(ARCHITECT_V2, WAITING_APPROVAL) -> (JUDGE_WAIT, WAITING_JUDGE)` when external audit is required
- `(JUDGE_WAIT, WAITING_JUDGE) -> (PLANNER, PENDING)` on `VERDICT: PASS|PASS_WITH_FIXES`
- `(JUDGE_WAIT, WAITING_JUDGE) -> (ARCHITECT_V2, PENDING)` on `VERDICT: BLOCK`
- `(PLANNER, WAITING_APPROVAL) -> (BUILDER, PENDING)`
- `(BUILDER, ACTIVE) -> (BUILDER, WAITING_USER_RUN)` on sandbox/test-run block
- `(BUILDER, WAITING_USER_RUN) -> (BUILDER, ACTIVE)` after user test output
- `(BUILDER, WAITING_APPROVAL) -> (AUDITOR, PENDING)`
- `(AUDITOR, WAITING_APPROVAL) -> (POST_AUDIT_LOGGER, PENDING)`
- `(POST_AUDIT_LOGGER, ACTIVE) -> (SCOUT, PENDING)` for next task

## validate_autopilot_transition (pseudocode)

```text
if from_state == to_state:
  return True
allowed = ALLOWED_TRANSITIONS[from_state]
return to_state in allowed
```

Where state tuple is `(phase, status)`.

## integrity_hash formula

`integrity_hash = sha256("{task_id}|{phase}|{status}|{transition_seq}|{phase_owner}")`

The hash is recalculated whenever `transition_seq` or any state field in the formula changes.

## Guard Checklist (mandatory before advancing)

1. `schema_version == 2`
2. `integrity_hash` matches current state fields
3. `phase_owner` matches active mode/model
4. transition exists in `ALLOWED_TRANSITIONS`
5. on failure: emit `SYNC_FAILURE` and halt (fail loud)

