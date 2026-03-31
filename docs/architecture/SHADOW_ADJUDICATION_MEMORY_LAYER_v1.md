# Shadow Adjudication + Development Memory Layer v1

Status: ACTIVE  
Scope: `R1 / Phase A / Tier-3 / shadow mode`

## Purpose

This layer sits above the existing bounded shadow verifier run and below any future
decision-influence pilot.

It exists to make shadow learning durable and reviewable:

- disagreements stop being ephemeral runtime observations
- contradictions become explicit artifacts
- blockers accumulate deterministically
- future Codex/owner sessions can start from structured memory instead of chat recall

## Layers

### 1. Runtime evidence

Runtime evidence remains the source layer:

- evidence bundles
- sanity audit report
- candidate sidecar
- verifier shadow records
- run stdout / resume stdout

These artifacts are factual run outputs and remain replayable.

### 2. Shadow adjudication

Adjudication consumes one existing bounded shadow run and emits:

- `shadow_adjudication_queue.json`
- `shadow_blocker_register.json`
- `shadow_usefulness_summary.json`
- `shadow_reviewer_packets.json`

Adjudication records:

- classify deterministic vs verifier disagreements
- classify contradiction themes
- classify blocker categories
- assign deterministic review priority
- recommend the next action without changing final card decisions

Adjudication does not change deterministic authority.

### 3. Development memory

Development memory is a repo-level structured snapshot.

It stores:

- proven facts
- not-proven / rejected conclusions
- current blockers
- active constraints
- next approved work item
- artifact references
- active policy/schema versions

Development memory is updated from adjudicated evidence, not from chat.

## Boundaries

Enters adjudication:

- routed verifier cases
- budget-skipped verifier cases
- contradiction-bearing responses
- broader-run blockers from the audit report

Enters development memory:

- only durable conclusions backed by one explicit run artifact
- only one recommended next work item
- only explicit policy/schema versions

Remains runtime-only:

- raw page fetch traces
- verbose stdout noise
- transient cache details

## Determinism

This layer is deterministic because it uses:

- fixed category lists from `shadow_adjudication_policy_v1`
- fixed priority scoring
- fixed artifact references
- existing run artifacts only

No live API call is required to regenerate it.

