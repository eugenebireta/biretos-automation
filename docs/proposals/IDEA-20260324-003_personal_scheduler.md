# IDEA-20260324-003 — Personal Scheduler (Owner-Focused Planning Engine)

> **Status:** DRAFT
> **INBOX entry:** `docs/IDEA_INBOX.md` → IDEA-20260324-003
> **Risk class:** SEMI
> **Created:** 2026-03-25

---

## 1. Problem / Context

The current system manages business automation well (orders, shipments, catalog, NLU),
but has no dedicated mechanism for **owner task planning and scheduling**.

The owner currently manages their own working time through:
- Mental model of active tasks (no persistent registry).
- Ad-hoc reminders in Telegram or personal notes.
- Weekly reviews that require manually reconstructing current state.
- AI sessions that start without knowledge of what is on today's agenda.

This creates cognitive overhead that the system is not reducing — contrary to the
North Star ("минимизировать manual_interventions" and "Cognitive Load < 3/неделю" in v1 STOP RULE).

The Personal Scheduler is a **planning logic layer** that sits above Owner Intent Memory
(IDEA-001) and below the owner interface (IDEA-002 Max Executive Layer).
It is NOT a calendar app. It is NOT an autonomous task executor.
It is an owner-focused recommendation engine for: what to do, when, and in what order.

---

## 2. Why Now

- Owner Intent Memory (IDEA-001) creates the data substrate (active threads, context profile,
  strategy hypotheses). Without a scheduling layer that reads this substrate, the memory
  layer is useful but passive.
- Этап 8 (Stability Gate) introduces "Owner Cognitive Load tracking" (8.4) and requires
  Cognitive Load < 3/week (STOP RULE v1). A scheduler directly supports this metric.
- The longer this is deferred, the more the owner's working time remains unstructured
  while the automation layer grows.
- Proposal-first: no code needed now, but the design must be fixed before any implementation
  to prevent scope conflation with Max Executive Layer (IDEA-002) and Owner Intent Memory (IDEA-001).

---

## 3. Relation to Master Plan / Roadmap / DNA

### Direct connections

| Element | Connection |
|---------|-----------|
| **STOP RULE v1** — Cognitive Load < 3/week | Scheduler is a primary mechanism to hit this metric |
| **Этап 8.4** — Owner Cognitive Load tracking | Scheduler outputs are the inputs to cognitive load measurement |
| **IDEA-20260324-001** — Owner Intent Memory | Scheduler reads Active Threads, Context Profile, Strategy Hypotheses |
| **IDEA-20260324-002** — Max Executive Layer | Max is the delivery surface; Scheduler is the planning logic layer |
| **COGNITIVE LAYER (Local PC, NO side-effects)** | Scheduler runs here; no Core mutations |
| **North Star: минимизировать manual_interventions** | Scheduler reduces the overhead of daily task planning |

### What this does NOT touch

- Core FSM, Guardian, reconciliation, order lifecycle — not in scope.
- Frozen Files (DNA §3) — not in scope.
- Pinned API (DNA §4) — not in scope.
- Business task execution (order processing, catalog) — Scheduler does not trigger these.
- Master Plan and Roadmap — **not modified** at DRAFT stage.

---

## 4. Goals

1. Accept owner tasks from multiple sources (chat input, Owner Intent Memory, Idea Inbox).
2. Classify each task on two axes: **strategic/tactical** and **urgent/not-urgent**.
3. Produce a **next best action** recommendation at any point in time.
4. Maintain three time-horizon buckets: **Today / This Week / Backlog**.
5. Deliver a **morning plan** at session start and support **reminders** and **reschedule**
   requests throughout the day.
6. Remain strictly separate from Owner Intent Memory (data layer) and
   Max Executive Layer (delivery layer) — communicate via defined interfaces.

---

## 5. Non-Goals

- Do NOT build a calendar UI or integrate with external calendar services (Google Calendar etc.)
  at DRAFT scope.
- Do NOT autonomously execute tasks — Scheduler recommends; owner decides and delegates.
- Do NOT replace Owner Intent Memory — Scheduler reads it, does not duplicate it.
- Do NOT merge with Max Executive Layer — Scheduler is the logic; Max is the surface.
- Do NOT add time-tracking or billing.
- Do NOT build autonomous rescheduling logic — reschedule only on explicit owner request.
- Do NOT introduce a new FSM. Task classification is a label, not a state machine.

---

## 6. Core Thesis

**Scheduler = classification + prioritization + horizon bucketing + delivery hook.**

```
Inputs:
  Owner Intent Memory (IDEA-001):
    - active_threads       → task candidates
    - context_profile      → owner working style, planning horizon
    - strategy_hypotheses  → strategic filters

  Owner real-time input:
    - "add task: ..."
    - "what should I do now?"
    - "reschedule X to tomorrow"
    - "mark X done"

Classification dimensions:
  Axis 1: strategic | tactical
  Axis 2: urgent | not-urgent
  → 4 quadrants (Eisenhower-style, but adapted to owner context)

Time horizons:
  TODAY    — committed for today, max 3-5 items
  THIS WEEK — queued, not yet committed
  BACKLOG  — captured, not scheduled

Output:
  next_best_action      → single top recommendation
  morning_plan          → TODAY list with estimated effort
  reminders             → time-based or event-based nudges
  reschedule_suggestion → when TODAY is overloaded
```

Delivery: via Max Executive Layer (IDEA-002) or directly via Telegram in the interim.

---

## 7. Consumers

| Consumer | What they get |
|----------|--------------|
| **Owner (morning)** | Morning plan: Today list + next best action |
| **Owner (during day)** | On-demand: "what next?" → next best action |
| **Owner (evening)** | Reschedule suggestions for incomplete TODAY items |
| **Max Executive Layer (IDEA-002)** | Scheduler output surfaced in primary interface |
| **Этап 8.4 Cognitive Load tracking** | Scheduler provides task count and completion rate data |

---

## 8. Data Sources

| Source | What it provides |
|--------|-----------------|
| Owner Intent Memory — active_threads | Task candidates with current status and next_step |
| Owner Intent Memory — context_profile | Planning horizon, working style, preferred session length |
| Owner Intent Memory — strategy_hypotheses | Strategic filter for "strategic vs tactical" classification |
| Owner real-time input | New tasks, completions, reschedule requests |
| System clock | Today / This Week boundaries, reminder triggers |

---

## 9. Constraints

1. **No side-effects.** Scheduler does not mutate Core tables, does not send orders,
   does not trigger business workflows.
2. **No new FSM.** Task state is a simple label (TODO / IN_PROGRESS / DONE / DEFERRED).
   Maximum 4 states, linear, no branches.
3. **Owner-confirmed execution.** Scheduler produces recommendations; owner approves
   before any downstream action is taken.
4. **Plain-text first.** Morning plan and next best action delivered as structured text.
   No UI rendering required at MVP scope.
5. **Read-only access to Owner Intent Memory.** Scheduler does not write back to memory
   files — it reads them and maintains its own schedule state separately.
6. **TODAY list hard cap: 5 items.** Prevents planning overload anti-pattern.

---

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Scope bleed into Max Executive Layer | High | Medium | Strict interface: Scheduler exposes plan API; Max calls it; no shared code |
| Task classification logic becomes subjective / unreliable | Medium | Medium | Limit classification to rule-based heuristics initially; no ML at DRAFT |
| Owner ignores recommendations — scheduler becomes noise | Medium | Medium | Lightweight format; morning plan max 5 items; no constant interruption |
| Dependency on IDEA-001 blocks Scheduler MVP | Low | High | Scheduler can use a minimal stub of active_threads.md without full memory layer |
| Reschedule logic becomes complex (dependencies, deadlines) | Medium | High | Scope freeze: reschedule = manual owner request only; no auto-dependency chains |

---

## 11. Promotion Options

### Option A (recommended) — New sub-stage under Этап 9 or Этап 19

1. Add sub-stage 9.x "Owner Planning Engine" or 19.x "Scheduler MVP" to EXECUTION_ROADMAP.
2. Add TD-049: Personal Scheduler to MASTER_PLAN, deferred review: post-Этап 8 stable.
3. Prerequisite: IDEA-001 promoted and at least `active_threads.md` exists.

### Option B — Embedded in Owner Intent Memory scope

Treat Scheduler as a module within Этап 19 (Business Memory) sub-stages.
19.4: Scheduler MVP on top of 19.1–19.3 memory entities.

### Option C — Park until Этап 8 complete

Defer until Cognitive Load tracking (8.4) produces real data. Then build Scheduler
against measured pain points rather than assumptions.

---

## 12. Open Questions

1. **Where does Scheduler state live?** A `schedule.md` file in `docs/memory/`?
   Or a separate `scheduler/` directory? Should it be in repo or local-only?
2. **Classification rules:** How does the system distinguish "strategic" from "tactical"
   without AI judgment? Rule-based: tasks linked to strategy_hypotheses = strategic?
3. **Reminder mechanism:** Push (cron + Claude Code message) or pull (owner asks "any reminders")?
   Cron requires infra; pull is simpler but passive.
4. **Integration with Этап 8.4 Cognitive Load:** Is the Scheduler output directly
   the input to cognitive load tracking, or is there a separate measurement step?
5. **TODAY cap enforcement:** What happens when owner adds a 6th item to TODAY?
   Hard block, soft warning, or silent append?

---

## What a Critic Should Check

- Is the Scheduler correctly scoped as *planning logic only*, or does it smuggle
  execution concerns (triggering tasks, sending messages)?
- Is the dependency on IDEA-001 (Owner Intent Memory) a hard blocker, or can a
  lightweight Scheduler MVP work with a minimal stub?
- Does the Eisenhower-style classification actually fit the owner's workload, or is
  it a model borrowed from personal productivity that won't survive contact with reality?
- Is TODAY cap of 5 items justified or arbitrary?
- Should Scheduler be a separate Этап / TD, or is it naturally a sub-stage of
  Business Memory (Этап 19)?

---

## Current Recommendation

**Status: DRAFT. Prerequisites: IDEA-001 must be promoted first.** Scheduler MVP is
a Layer 2 build on top of the memory layer. Do not implement before active_threads.md
and context_profile.md exist as real artifacts.

---

## Review Log

| Date | Reviewer | Status change | Notes |
|------|----------|---------------|-------|
| 2026-03-25 | Claude Code (SCOUT) | INBOX → DRAFT | Proposal created per owner request. No code. |
