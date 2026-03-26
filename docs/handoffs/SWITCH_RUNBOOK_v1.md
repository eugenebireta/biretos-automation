# Switch Runbook v1

## Purpose

Provide a minimal, mechanical protocol for switching execution between Claude Code and Codex.

## Switch Allowed

Switch is allowed only if all conditions hold:
- current package has a valid clean stop-point
- current owner is explicit
- branch is explicit
- HEAD is explicit
- risk_class is explicit
- role is explicit
- handoff summary is updated
- handoff summary is reconciled with current `git` state
- clean tree is preferred; dirty-tree switch is fallback only under the narrow conditions defined below

## Switch Forbidden

Do not switch if any of the following is true:
- package is unresolved
- current owner of changes is unclear
- `git` and `HANDOFF_STATE.json` disagree
- unresolved conflicts exist
- risk class increased without review
- the switch would create a parallel major track
- the next tool would enter CORE work without the full external pipeline

## Pre-Switch Checklist

Before switching, confirm:
- `task_id`
- `owner_tool`
- `branch`
- `HEAD`
- `risk_class`
- `role`
- `scope`
- `out_of_scope`
- `touched_files`
- `checks_passed`
- `checks_not_run`
- `stop_point`
- `residual_risk`
- `next_expected_role`
- `blockers`

Then compare the handoff summary against:
- `git branch`
- `git rev-parse HEAD`
- `git status`
- `git diff`

## Required Read Order For Next Tool

Read in this order:
1. `docs/PROJECT_DNA.md`
2. canonical boundary / governance documents referenced by DNA
3. `docs/MASTER_PLAN_v1_9_2.md`
4. `docs/autopilot/STATE.md`
5. GitHub current state
6. `docs/EXECUTION_ROADMAP_v2_3.md`
7. `docs/_governance/AI_EXECUTION_CONTRACT_v1.md`
8. `docs/autopilot/HANDOFF_STATE.json`
9. this runbook

## Dirty Tree Handling

Preferred standard: switch on a clean tree, or after a WIP commit or stash that preserves an unambiguous handoff point.

Dirty-tree handoff is fallback only, not normal practice.

If the tree is dirty:
- inspect `git branch`
- inspect `git rev-parse HEAD`
- inspect `git status`
- inspect `git diff`
- identify which paths belong to the current package
- identify unknown or unrelated changes

A clean stop-point on a dirty tree is allowed only if:
- all dirty paths belong to the current package
- all dirty paths are explicitly listed in handoff
- ownership is explicit
- unresolved conflicts are none
- handoff matches `git status` and `git diff`

Otherwise, the stop-point is invalid and switching is blocked.

## Risk Escalation

If risk increases:
- `LOW -> SEMI`: stop and require external framing
- `SEMI -> CORE`: Codex becomes read-only / proposal-only until the full external pipeline is complete
- update the handoff summary before any further work
- do not continue as if the original risk class still applies

## Git vs Handoff Conflict

If `git` and `HANDOFF_STATE.json` disagree:
- trust `git`
- treat the handoff as non-authoritative
- discard the stale or contradictory handoff summary
- reconstruct the handoff from canonical docs, current `git` state, `STATE.md`, and GitHub state
- do not switch tools until reconciliation is complete

## Clean Stop-Point

A switch is valid only at a clean stop-point.

A clean stop-point requires all of the following:
- branch is explicit
- HEAD is explicit
- current owner is explicit
- unresolved conflicts are none
- risk_class is explicit
- next_expected_role is explicit
- handoff summary is reconciled with current `git` state
- if review, test, or validation evidence is claimed, it is tied to a commit, ref, or current working tree state, not to chat memory alone

## Stop-Point Rule

No silent continuation is allowed after switch.
The next tool must start from authoritative sources, not from assumed chat memory.
