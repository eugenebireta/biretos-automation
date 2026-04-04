# CORE Watchdog Reconsideration

## Context

- Branch: `feat/core-governance-watchdog`
- Rescued commit: `5551aea`
- Audit date: `2026-04-04`
- Ahead/behind vs `origin/master`: `1 ahead / 127 behind`
- Why this payload exists: the work was preserved from a previously verified non-junk stash as a rescue branch so the changes would not be lost.
- Why the branch is not merge-ready:
  - it was authored on a stale base
  - it includes an explicit Tier-1 freeze violation in `maintenance_sweeper.py`
  - it mixes Tier-1, governance execution semantics, replay behavior, idempotency behavior, and tests in one rescued commit
  - at least part of the runtime surface has drifted on `master` since the rescue branch base

## Final Verdict

- Payload class: mixed CORE payload
- Tier-1 freeze violation: present
- Stale-base drift: present
- Automatic handling status: prohibited
- Final decomposition verdict:

> `CORE payload is not meaningfully decomposable at current state`

## Hard Rule

- No auto-port from `feat/core-governance-watchdog`.
- No blind salvage.
- No rebase, merge, or cherry-pick from this branch outside a future CORE Strict Mode reconsideration.

## Review Buckets

### P1 Watchdog

- Files:
  - `.cursor/windmill-core-v1/maintenance_sweeper.py`
  - `.cursor/windmill-core-v1/tests/test_maintenance_sweeper.py`
- Intent:
  - detect governance cases stuck in `executing`
  - enqueue `governance_execute` retries from maintenance
- Runtime effect:
  - the maintenance cycle starts scanning `review_cases`
  - matching cases trigger new `governance_execute` jobs with `gov_watch:{case_id}:{hour}` idempotency keys
- Blast radius:
  - Tier-1 frozen file
  - maintenance loop behavior
  - governance retry traffic and queue pressure
  - `review_cases` recovery path
- Why not safe to auto-port:
  - `maintenance_sweeper.py` is explicitly frozen Tier-1 infrastructure
  - introducing queue-producing logic into Tier-1 requires CORE review, not salvage
- Future accept/reject questions:
  - should Tier-1 be allowed to originate governance recovery jobs at all?
  - should stuck-case recovery live in maintenance, governance executor, or a dedicated operator tool?
  - are hourly watchdog idempotency keys and batch limits operationally safe?

### P2 Replay/Execution Semantics

- Files:
  - `.cursor/windmill-core-v1/ru_worker/governance_executor.py`
  - `.cursor/windmill-core-v1/ru_worker/dispatch_action.py`
  - `.cursor/windmill-core-v1/tests/test_governance_executor.py`
- Intent:
  - widen replay-state classification
  - add exponential lock TTL growth for governance execution retries
  - cancel cases after retry exhaustion
  - suppress control-decision writes during `REPLAY`
- Runtime effect:
  - replay outcomes gain new statuses such as `replay_needs_finalization`, `incomplete_execution_no_lock`, and `cancelled_after_success`
  - governance execution retries move from a single retry to multiple attempts with TTL growth
  - exhausted retry paths now cancel cases
  - replay mode stops writing control decisions
- Blast radius:
  - governance case lifecycle
  - replay observability
  - action lock timing
  - control-decision persistence behavior
- Why not safe to auto-port:
  - this bucket changes live governance semantics rather than just tests or docs
  - `dispatch_action.py` and `governance_executor.py` both have stale-base drift on current `master`
  - replay and cancellation behavior must be reviewed as one semantic unit
- Future accept/reject questions:
  - are the new replay statuses part of the intended public/internal governance contract?
  - is auto-cancel on retry exhaustion correct, or should the system escalate instead?
  - should `REPLAY` suppress control-decision writes globally, or only in narrower cases?
  - are exponential TTLs `300/600/1200` the right recovery shape?

### P3 Correction-Source Key Rotation

- Files:
  - `.cursor/windmill-core-v1/ru_worker/governance_trigger.py`
  - `.cursor/windmill-core-v1/tests/test_governance_trigger.py`
- Intent:
  - support correction lineage by deriving a deterministic `external_idempotency_key` from an earlier source key
- Runtime effect:
  - when `correction_source` is provided, `handle_pending_approval()` no longer generates a fresh UUID and instead emits `{original_external_idempotency_key}-c{decision_seq}`
- Blast radius:
  - governance snapshot shape for correction flows
  - downstream deduplication semantics for corrected executions
- Why not safe to auto-port:
  - no current caller in the rescued payload actually supplies `correction_source`
  - the change looks isolated in code but is semantically tied to a broader correction/governance flow that is not part of this branch
  - shipping it alone would introduce an API extension without a verified caller path
- Future accept/reject questions:
  - is `correction_source` a real supported contract or an abandoned design stub?
  - where should lineage for corrected cases be sourced and validated?
  - should external idempotency keys remain derivable across correction chains?

### P4 Hash-Versioning

- Files:
  - `.cursor/windmill-core-v1/ru_worker/idempotency.py`
  - `.cursor/windmill-core-v1/tests/test_idempotency.py`
- Intent:
  - version `request_hash` values as `v1:<digest>`
  - preserve limited backward parsing for bare historical hashes
- Runtime effect:
  - all newly computed request hashes change format across action types
  - live idempotency rows would begin storing `v1:`-prefixed request hashes
- Blast radius:
  - `action_idempotency_log`
  - all action paths using `compute_request_hash()`
  - lock takeover/update behavior
  - governance execution request hashing
- Why not safe to auto-port:
  - this is a live data contract change, not a local refactor
  - the parser adds backward reading, but the writer changes system-wide behavior immediately
  - the rescued branch does not include a separate migration or rollout envelope
- Future accept/reject questions:
  - is hash versioning actually needed now, or was it preparatory work?
  - what database/backward-compat guarantees are required before changing writer behavior?
  - should version rollout be coordinated with observability and repair tooling first?

## False Split Risks

- `P1` is blocked by Tier-1 freeze:
  - the code path lives in frozen infrastructure and cannot be treated as an ordinary salvage candidate
- `P2` is stale-base sensitive:
  - `dispatch_action.py` and `governance_executor.py` have changed on `master` since the rescue branch base, so blind carry-over would review against the wrong context
- `P3` is a false candidate:
  - it appears small, but it introduces a contract extension that no verified caller in the rescued payload uses
- `P4` cannot be taken alone:
  - request-hash versioning changes live writer behavior across action paths and needs an explicit migration/review envelope

## Recommended Handling

- Keep `feat/core-governance-watchdog` as a reference artifact.
- Revisit it later under CORE Strict Mode only.
- If reconsidered in the future, do manual review by buckets `P1` through `P4`.
- Future handling, if any, must be bucket-by-bucket reconsideration rather than code transfer from the rescue branch.
