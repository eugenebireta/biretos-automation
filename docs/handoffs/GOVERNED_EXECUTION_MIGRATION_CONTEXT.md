# Governed Execution & Migration Safety — Handoff Context

**Version:** 2.0
**Created:** 2026-03-24
**Status:** READY FOR AI CONSUMPTION
**Risk class of this document:** LOW (documentation only, no code changes)

---

## 0. Purpose

This document gives AI executors (Claude Code, ChatGPT CRITIC/JUDGE) accurate context on
the current state of governed execution infrastructure in Biretos Automation.

It does **NOT** introduce new rules or redefine risk levels.
All rules originate from authoritative sources (see §10).
This handoff only explains current state, target state, and what is and is not safe to start now.

---

## 1. Risk Classification (from Master Plan v1.9.2 — not redefined here)

`LOW / SEMI / CORE` are defined in `MASTER_PLAN_v1_9_2.md` (section "GOVERNED AI EXECUTION LAYER")
and `MIGRATION_POLICY_v1_0.md` §5. This handoff does not introduce them — it references them.

| Risk  | AI execution mode                                    |
|-------|------------------------------------------------------|
| 🟢 LOW  | Semi-autonomous within guardrails                  |
| 🟡 SEMI | Commit/merge requires explicit owner approval      |
| 🔴 CORE | Proposal-only (Pass 1) + Strict Mode (Pass 1→2→3) |

---

## 2. Readiness Gates

### Gate READY (source: MIGRATION_POLICY §10)

Required before first SEMI/CORE execution:
- hooks / sandbox / permissions реально работают
- CI стабильно зелёный
- 3 LOW/SEMI задачи без architectural violations
- 1 failback drill
- Zero-Memory Reset отработан
- fallback в Cursor + Autopilot сработал clean

### Gate CORE-APPROVED (source: MIGRATION_POLICY §10)

Required before CORE becomes primary build mode:
- 2–3 CORE strict-runs успешно
- CRITIC и AUDITOR раздельные
- JUDGE не нашёл architectural violation
- diff quality не хуже fallback-контура

---

## 3. Readiness Gates C + A + B — Explicit TD Mapping

MIGRATION_POLICY §7 lists "Mandatory Hardening Before First CORE".
Three of those items are tracked as Tech Debt entries in MASTER_PLAN_v1_9_2.md:

| Label | TD entry | Review trigger | Description |
|-------|---------|----------------|-------------|
| **C** | **TD-047** — Authoritative Security Gate cleanup | After CORE-APPROVED gate | Consolidate fragmented security checks; remove redundant/conflicting gates |
| **A** | **TD-044** — Portable Guard Validation | При смене рабочей станции | Verify all hooks/guards transfer correctly to a new workstation |
| **B** | **TD-046** — Workstation Cutover Runbook | При смене рабочей станции | Step-by-step runbook for safe workstation cutover without breaking guarded contour |

**Note:** C (TD-047) targets cleanup after CORE-APPROVED. A+B (TD-044, TD-046) are triggered
by workstation migration. They are independent tracks with different triggers.

### TD-045 — SEMI Approval Artifact (separate dependency, not part of C+A+B)

| Field | Value |
|-------|-------|
| **TD entry** | TD-045 — SEMI Approval Artifact |
| **Review trigger** | После CORE-APPROVED gate |
| **Status** | **NOT YET IMPLEMENTED** |
| **What it provides** | Structured, versioned record proving owner approval for each SEMI commit/merge |
| **Current fallback** | Explicit owner approval communicated outside Claude (chat message, GitHub comment). Valid and sufficient until TD-045 is implemented, but lacks formal auditability. |

Do not describe TD-045 as implemented or functional — it does not exist yet.

---

## 4. Current State vs Target State

### 4.1 CURRENT STATE (as of 2026-03-24)

| Component | Status | Note |
|-----------|--------|------|
| CLAUDE.md in repo root | ✅ Present | |
| `.claude/settings.json` deny permissions | ✅ Present | |
| PreToolUse hooks (protected paths) | ✅ Present | |
| git pre-commit guard | ✅ Present | |
| CI — GitHub Actions pytest on push (Этап 2.1) | ✅ Active | |
| Hash Lock — Tier-1 files (Этап 5.5.1) | ✅ Active | SHA-256, CRLF-safe |
| Boundary Grep guard (Этап 5.5) | 🔄 Status not confirmed | M3b/M3c не подтверждены |
| DDL Guard (Этап 5.5) | 🔄 Status not confirmed | M3c не подтверждён |
| **Branch protection on master (Этап 2.2)** | ❌ **NOT DONE** | Explicit in Roadmap state |
| SEMI Approval Artifact (TD-045) | ❌ NOT IMPLEMENTED | Planned after CORE-APPROVED |
| OS-level process isolation | ❌ NOT implemented | See §5 |
| Active implementation task | Этап 7 — AI Executive Assistant NLU (PR #9 open, awaiting external CRITIC / AUDITOR / JUDGE review) | No new code; Этап 8 not yet started |

### 4.2 TARGET STATE

| Component | Target condition |
|-----------|-----------------|
| Branch protection on master | Server-side rule: PRs required, CI must pass, no direct push |
| SEMI Approval Artifact | Structured record per SEMI commit/merge (TD-045 closed) |
| Portable Guard Validation | Guards verified on new workstation (TD-044 closed) |
| Workstation Cutover Runbook | Documented procedure (TD-046 closed) |
| Security Gate consolidation | Single authoritative gate, no redundant checks (TD-047 closed) |
| OS-level isolation | Full process-level sandbox for Claude Code execution |

---

## 5. OS-Level Isolation

**Stance: REQUIRED for fully safe SEMI execution. Currently NOT implemented.**

OS-level process isolation (e.g., sandboxed environment, container, or restricted OS user
for Claude Code) is a **required** element of the full guarded execution contour for SEMI tasks.

**Known risk of operating without OS-level isolation:**
- Hook misconfiguration or permission error can affect the host filesystem beyond the repo scope.
- `.claude/settings.json` deny rules operate at application level only — not enforced by the OS.
- Reverting an OS-level mistake requires manual intervention outside Claude.

**Current posture:**
Working without OS-level isolation. This is an **accepted known risk** for the current
review / documentation / pre-next-sprint period (Этап 7 external review pending;
no active SEMI/CORE implementation tasks running).

**Trigger for resolution:** Before the next active SEMI or CORE implementation sprint begins.

---

## 6. SEMI Approval Mechanism

**Status: NOT YET IMPLEMENTED. Planned via TD-045.**

The SEMI Approval Artifact (TD-045) is a planned but non-existent mechanism.

**When implemented it will provide:**
- Structured, versioned approval record: task_id, branch, commit hash, approval timestamp, channel.
- Auditability trail for SEMI merges.

**Current fallback (valid until TD-045 is closed):**
- Owner provides explicit approval outside Claude (chat message, GitHub comment, or similar).
- Claude Code records approval reference in commit message or PR description.
- This fallback is **valid and sufficient for current SEMI work**,
  but does not provide the formal auditability that TD-045 will introduce.

Do not describe the SEMI approval mechanism as functional or implemented until TD-045 is closed.

---

## 7. Branch Protection

**Этап 2.2 status: NOT DONE (as of 2026-03-24)**

Branch protection on `master` is a server-side barrier (GitHub branch protection rules).
It is a **target-state requirement**, not a current capability.

### What branch protection provides (target state)

- No direct push to `master` — all changes must go through PRs.
- CI (pytest) must pass before merge is allowed.
- Force-push to `master` blocked at server level.

### Impact of Этап 2.2 absence on current work

The absence of Этап 2.2 does **NOT block:**
- Local guard validation (hooks, permissions, pre-commit)
- LOW task execution
- Documentation and proposal work
- Stability Gate monitoring (Этап 8)
- Local preparation of guarded execution contour

The absence of Этап 2.2 **DOES mean:**
- A fully safe push-enabled workstation cutover cannot be declared complete.
- A misconfigured Claude Code session could push directly to `master` if local hooks fail
  (no server-side fallback).
- CORE implementation readiness (MIGRATION_POLICY §7) requires branch protection.

### Resolution path

Close Этап 2.2 before the next active CORE implementation sprint.
No code changes required — this is a GitHub repository settings action (owner).

---

## 8. What Is Startable Now / What Is Not

### ✅ Startable now

| Activity | Reason |
|---------|--------|
| Этап 7 external review (CRITIC / AUDITOR / JUDGE) | Active task, no new code — awaiting review of PR #9 |
| LOW task execution | Guardrails L1-L4 active, low blast radius |
| Documentation hardening (proposals, handoffs, IDEA_INBOX) | No Core touch |
| TD-044 Portable Guard Validation — research/prep phase | Documentation only |
| TD-046 Workstation Cutover Runbook — drafting | Documentation only |
| SEMI tasks with owner fallback approval | Fallback sufficient; TD-045 absence acknowledged |

### ❌ Not startable yet (blocked or not safe without acknowledged risk)

| Activity | Blocker | Resolution path |
|---------|---------|----------------|
| Fully safe push-enabled workstation cutover | Этап 2.2 (branch protection) not closed | Owner closes Этап 2.2 in GitHub settings |
| SEMI tasks with full formal auditability | TD-045 not implemented | Use fallback approval; close TD-045 after CORE-APPROVED |
| CORE implementation sprint | Этап 2.2 absent; OS-level isolation absent | Close Этап 2.2 first; address OS isolation |
| Security Gate consolidation (TD-047) | Deferred until CORE-APPROVED gate | Not yet reached |

---

## 9. Current Guard Stack (Operative Layers)

| Layer | Component | Status |
|-------|-----------|--------|
| L1: Application | CLAUDE.md rules | ✅ Active |
| L1: Application | `.claude/settings.json` deny rules | ✅ Active |
| L2: Hook | PreToolUse(Edit/Write/Bash) on protected paths | ✅ Active |
| L3: Git | pre-commit guard | ✅ Active |
| L4: CI | GitHub Actions pytest + Hash Lock (Tier-1) | ✅ Active |
| L5: Server-side | Branch protection (Этап 2.2) | ❌ Not done |
| L6: OS | Process-level isolation | ❌ Not implemented |

**Current operative posture:** L1-L4 active. L5-L6 absent.
Sufficient for LOW tasks and monitoring. Insufficient for fully safe CORE cutover.

---

## 10. Failback

From `MIGRATION_POLICY_v1_0.md` §12. Triggers for failback to Cursor + Autopilot:

- Claude Code touches a protected path
- Claude Code gives unsafe diff
- Claude Code fails external review
- Claude Code twice fails a CORE strict-run
- Claude Code violates boundaries / invariants / frozen rules

On failback: task → Cursor + Autopilot; Claude Code restricted to LOW/SEMI;
re-admission only after new hardening + shadow-run.

---

## 11. Document Governance

This handoff is a **working context document**, not an authoritative governance document.

Authoritative sources (priority order per CLAUDE.md):
1. `docs/PROJECT_DNA.md`
2. `docs/MASTER_PLAN_v1_9_2.md`
3. `docs/EXECUTION_ROADMAP_v2_3.md`
4. `docs/claude/MIGRATION_POLICY_v1_0.md`
5. `docs/autopilot/STATE.md`

If any statement in this handoff conflicts with the above — the authoritative source wins.

**Update triggers:** TD-044, TD-045, TD-046, or TD-047 closed; Этап 2.2 closed;
OS-level isolation implemented; next CORE sprint begins.

---

*End of GOVERNED_EXECUTION_MIGRATION_CONTEXT v2*
