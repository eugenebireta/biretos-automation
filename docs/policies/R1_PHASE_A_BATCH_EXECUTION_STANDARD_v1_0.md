# R1 Phase A Batch Execution Standard v1.0

Status: ACTIVE  
Date: 2026-03-26

## 1. Scope

This standard applies by default to:

- `R1`
- `Phase A`
- `Tier-3`
- `SEMI-CRITICAL` revenue work

This standard does not override or dilute any stricter requirement for `CORE` work.  
`CORE` keeps its own approval, review, and execution constraints.

## 2. Authority And Hierarchy

This document is an execution standard, not a constitutional boundary document.

If this document conflicts with [`docs/PROJECT_DNA.md`](/d:/BIRETOS/projects/biretos-automation/docs/PROJECT_DNA.md), `PROJECT_DNA` wins.

If [`docs/MASTER_PLAN_v1_9_2.md`](/d:/BIRETOS/projects/biretos-automation/docs/MASTER_PLAN_v1_9_2.md) conflicts with [`docs/EXECUTION_ROADMAP_v2_3.md`](/d:/BIRETOS/projects/biretos-automation/docs/EXECUTION_ROADMAP_v2_3.md), `Master Plan` wins and the `Roadmap` must be updated.

This standard does not grant sovereignty to the agent. It governs execution packaging only.

## 3. Purpose

The goal is to reduce fragmented execution loops such as:

`implementation -> evidence request -> small fix -> new evidence -> more fixes`

and replace them with bounded, auditable vertical batches that preserve:

- `evidence-first`
- governance boundaries
- deterministic review
- controlled autonomy
- low owner `time-at-keyboard`

## 4. Core Rule

Work must proceed as bounded `vertical invariant batches`.

Default target:

- large enough to avoid micro-fragmentation
- small enough to preserve proof, auditability, and deterministic review

### 4.1 Scope Cap

Every batch must remain small, atomic, and isolated enough to keep `Gate 2`
and `Gate 3` lightweight.

Minimum required shape:

- one logical change-set
- one risk class
- one narrow outcome
- one policy surface maximum
- no hidden refactor
- no opportunistic architecture improvement outside the declared task
- no parallel touch of multiple subsystems unless explicitly opened as such

Practical rule:

- if owner review starts feeling like manual re-audit, the batch is too large
- any touched file outside the declared scope invalidates the batch unless a new gate re-opens it

## 5. Batch Header Minimum

Every batch must open with a header containing:

- `risk class`
- `vertical invariant`
- `policy surface`
- `sha`
- `entry criteria`
- `exit criteria`

Recommended header format:

```text
Batch: <A | B | C1 | C2>
Risk Class: <LOW | SEMI-CRITICAL | CORE>
Vertical Invariant: <single invariant name>
Policy Surface: <one policy surface or none>
Evidence SHA: <git sha or TBD>
Entry Criteria: <explicit gate>
Exit Criteria: <explicit gate>
```

## 6. Batch Model

### 6.1 Batch A

`implementation + tests + full evidence pack`

### 6.2 Batch B

maximum one `minor corrective pack` to reach `PR-ready`

### 6.3 Batch C1

`tooling freeze on explicit SHA`

### 6.4 Batch C2

`sanity run on frozen SHA + audit report`

### 6.5 Gate Model

The execution path keeps four gates:

- `Gate 1 — Batch Start`: go / no-go for one narrow package
- `Gate 2 — Change Package Review`: scope, changed files, semantic diff, core integrity assertions, out-of-scope list
- `Gate 3 — Runtime / Sanity Verification`: raw logs, verification command, sanity result, promised vs actual
- `Gate 4 — Live / Broader Run Approval`: wider sample, live side-effects, or explicit scope expansion

## 7. Required Constraints

- Every batch must have explicit `entry criteria` and `exit criteria`.
- Batch size is limited to `one vertical invariant`.
- Batch size is limited to `one policy-surface maximum`.
- It is forbidden to mix in one batch: `policy + tooling + run semantics`.
- Batch must stay inside its declared scope boundary.
- Any dependency on out-of-scope work must be declared explicitly.
- `Batch C2` must run on the exact frozen SHA declared in `Batch C1`.
- Any meaningful change after `Batch C1` automatically invalidates `Batch C2`.
- This standard does not authorize multi-agent runtime.

## 8. Evidence Stale Rule

The `evidence stale rule` is always active.

Any `meaningful change` after an evidence pack makes that evidence stale.

For this standard, `meaningful change` includes any change to:

- `policy`
- `schema`
- `decision semantics`
- `identity contract`
- tooling behavior used for sanity validation
- accepted sanity sample set
- sanity thresholds or pass/fail criteria

If evidence becomes stale, the response must say so explicitly and declare rerun scope.

## 9. Corrective Loop Rule

A corrective loop is allowed only once, only inside `Batch B`, and only if the change is `minor`.

A change is `minor` only if all conditions below remain true:

- policy does not change
- schema does not change
- decision semantics do not change
- identity contract does not change
- tooling behavior for sanity validation does not change
- accepted sample set and thresholds do not change
- no rerun wider than a targeted retest is required

If any condition above is false, the work is not a corrective loop and must be opened as a `new batch`.

## 10. Definitions

### 10.1 PR-ready

`PR-ready` means:

- intended scope is complete
- tests for that scope are green
- evidence pack exists and is tied to one explicit SHA
- out-of-scope items are explicit
- no unresolved dependency on out-of-scope work remains hidden
- no unresolved blocker remains inside the declared batch boundary
- no auto-reject condition is active

`PR-ready` does not mean `merge-approved`.

### 10.2 Merge-approved

`Merge-approved` means the work has passed the review and approval path required by its current risk mode, governance path, and owner decision model.

This status may require owner approval and may require additional review gates outside this SOP.

### 10.3 Tooling freeze

`Tooling freeze` means:

- tooling and code used for sanity validation are frozen on an explicit SHA
- no further meaningful edits are allowed before the sanity run
- if such edits occur, `C2` is reset and must be rerun on a new frozen SHA

## 11. Agent Response Standard

Every substantial delivery from the agent must include:

- `evidence valid for SHA: <sha>`
- `evidence stale: yes/no`
- `rerun scope required: none / targeted / full sanity`

### 11.1 Mandatory Evidence Pack

Every substantial `R1` delivery must include:

1. `Scope Boundary Check`
2. `Changed Files`
3. `Diff/Stat`
4. `Semantic Diff`
5. `Key Hunks / Key Fragments`
6. `Core Integrity Assertions`
7. `Tests / Checks Executed`
8. `Raw Test Logs`
9. `Copy-paste Verification Command`
10. `Out-of-Scope / Deferred List`
11. `Dependency on Out-of-Scope Items? Yes/No`
12. `Explicit Verdict`
13. `Next Gate Recommendation`

Omitting a mandatory field makes the evidence pack invalid.

### 11.2 Auto-Reject Rules

A batch is automatically rejected if any condition below is true:

- touched file outside declared scope
- Tier-1 file modified
- pinned signature changed
- silent refactor outside task intent
- unresolved dependency on out-of-scope bug / fix
- missing raw logs
- missing verification command
- missing core integrity assertions
- missing honest deferred / out-of-scope list

### 11.3 Core Integrity Assertions

For `R1` / Revenue batches, the evidence pack must explicitly confirm:

- `trace_id` is preserved or not impacted
- `idempotency_key` is preserved or not impacted
- `job_state` remains linear and does not grow into a second FSM
- auditability / traceability did not degrade
- no hidden mutation was introduced
- the Revenue adapter did not drift into a second Core

If relevant, the response should also state that `PR-ready` is not the same as `merge-approved`.

## 12. Operational Intent

This standard exists to speed up `R1 / Phase A` execution without weakening control.

The operating principle is:

`vertical invariant batches + mandatory evidence template + max one minor corrective loop + frozen-SHA sanity run separate from tooling changes`

Owner escalation should be exception-driven and happen at explicit gates, not as
continuous micro-supervision.

This standard is deliberately narrower than `PROJECT_DNA` and must be applied inside DNA, not above it.
