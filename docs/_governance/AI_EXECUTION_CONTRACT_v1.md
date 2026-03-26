# AI Execution Contract v1

## Purpose

Define a minimal, tool-neutral execution contract for switching work between Claude Code and Codex without changing project governance.

## Scope

This contract applies to AI-assisted execution in this repository.

It does not replace:
- canonical governance documents
- external review roles
- existing risk controls
- project execution governance

## Canon-Safe Truth Model

This contract does not change the project's canonical document hierarchy.

Canonical rules and boundaries remain in the project's canonical sources, including:
- `docs/PROJECT_DNA.md`
- canonical boundary / governance documents referenced by DNA
- `docs/MASTER_PLAN_v1_9_2.md`
- `docs/EXECUTION_ROADMAP_v2_3.md`

Use the following for execution-state resolution only:
- local workspace state = `git`
- operational execution state = `docs/autopilot/STATE.md` + GitHub
- roadmap = target map unless fresher execution state contradicts it

Execution-state sources are not rules truth.
They never override DNA, canonical boundaries, or Master Plan rules.

## Provisional Dual-Tool Extension

Dual-tool mode is an owner-approved provisional extension.
It is not a historical repo fact and does not replace the existing governance canon.

## Role Boundaries

Claude Code and Codex may swap only the BUILDER role.

By default:
- Codex is not ARCHITECT
- Codex is not CRITIC
- Codex is not JUDGE
- Codex is not AUDITOR
- Claude Code must not silently replace JUDGE
- Claude Code must not silently replace AUDITOR

Tool swap never downgrades governance.
If a required role is external, it remains external regardless of which builder tool is active.

## Risk Rules

### LOW

- narrow execution package only
- builder may execute within the approved task scope
- builder must stop at the package stop-point

### SEMI

- builder-only after external framing already exists
- no self-start from ambiguous architecture
- builder must stop at the agreed review point

### CORE

- full external pipeline remains required
- Codex is read-only / proposal-only until that pipeline is complete
- Codex must not implement code, mutate repo state, or judge CORE readiness
- Claude Code must not be treated as an implicit waiver of external CORE governance
- tool swap never converts CORE into SEMI or LOW

## Package Ownership and Branch Discipline

- one owner per package
- one bounded package at a time
- no concurrent AI ownership of the same unresolved package
- no two AI tools in the same file-worker
- one major branch at a time
- tool switching must not create a parallel major track

## Handoff Authority Status

`docs/autopilot/HANDOFF_STATE.json` is a non-authoritative coordination cache and summary only.

Authoritative sources remain:
- canonical project documents
- local `git` state
- `docs/autopilot/STATE.md`
- GitHub remote state

If handoff state is stale, incomplete, or contradictory:
- ignore it
- discard it as authority
- reconstruct it from authoritative sources

Handoff state never overrides canonical documents, `git`, `STATE.md`, or GitHub.

## Valid Handoff

A handoff is valid only if all of the following are explicit:
- current owner
- branch
- HEAD
- risk_class
- role
- scope
- out_of_scope
- touched_files
- checks_passed
- checks_not_run
- stop_point
- residual_risk
- next_expected_role
- blockers

A handoff is valid only if it is reconciled with current `git` state and, when operational branch / PR / execution status is relevant, with `docs/autopilot/STATE.md` and GitHub state.

## Forbidden Situations

- switching in the middle of an unresolved package
- switching with unclear ownership of current changes
- switching when `git` and handoff state disagree
- switching while risk class silently escalated
- treating dual-tool mode as a replacement for governance roles
- using `scripts/` as a final publish-policy locus
- using handoff state as rules truth or policy truth

## Phase A / R1 Boundary

This boundary is an owner-approved provisional extension for coordination clarity.
It is not yet a historical repo fact.

When canonical documents enable `R1` batch packaging, execution packaging is
defined by `docs/policies/R1_PHASE_A_BATCH_EXECUTION_STANDARD_v1_0.md`.
This contract remains tool-neutral and does not replace that standard.

Phase A is an enrichment feeder.
Phase A does not own publish policy.

`scripts/` may provide:
- evidence collection
- search expansion
- extraction
- candidate gathering
- persistence
- advisory scoring
- hints
- evidence bundles

`scripts/` must not become a final publish-policy locus.

The R1 shell is the execution locus for already-approved publish policy.
The R1 shell is not the policy owner.

Canonical publish policy remains in the governance-approved policy layer, not in ad hoc script logic.

## Non-goals of v1

- no hooks or automation requirements
- no CI enforcement changes
- no R1 execution changes
- no code-level materialization of the Phase A / R1 boundary
- no rewrite of canonical governance documents
