# IDEA-20260324-002 — Max Executive Layer (Channel-Agnostic Owner Interface)

> **Status:** DRAFT
> **INBOX entry:** `docs/IDEA_INBOX.md` → IDEA-20260324-002
> **Risk class:** SEMI
> **Created:** 2026-03-25

---

## 1. Problem / Context

The current AI Executive Assistant (Этап 7) delivers its UX exclusively through Telegram.
This couples two distinct concerns:

1. **The assistant logic** — NLU, intent routing, task execution.
2. **The delivery channel** — Telegram as the only surface.

This tight coupling creates several problems:
- Telegram is a third-party channel: downtime, API changes, or rate limits break owner UX entirely.
- Voice-first capture (dictating a task while driving, for example) has no path — Telegram is
  text/mobile-first but not designed as the primary owner productivity interface.
- Future channels (web dashboard, desktop app, voice terminal, "Max") require a full rewrite
  rather than a plug-in adapter.
- Owner intent context (IDEA-001) cannot be cleanly surfaced in a Telegram message thread.

The idea: introduce a **channel-agnostic assistant layer** where "Max" is the product name
for the primary owner-facing interface, and Telegram is demoted to a fallback/alerts/export channel.

---

## 2. Why Now

- Этап 7 (AI Executive Assistant NLU) is nearly complete and establishes the assistant contract.
  Now is the right time to define the evolution path *before* Этап 8 embeds deeper Telegram coupling.
- Owner Intent Memory (IDEA-001) creates a portable context layer — which only pays off if
  multiple channels can consume it. A channel-agnostic interface design is the unlock.
- Telegram has already shown its limits as a UX surface: button confirmations (INV-MBC),
  inline menus, and context-heavy flows are awkward in a chat interface.
- The proposal does NOT require code changes today — it defines the target architecture
  so that future Этап decisions don't lock in the wrong substrate.

---

## 3. Relation to Master Plan / Roadmap / DNA

### Direct connections

| Element | Connection |
|---------|-----------|
| **Этап 7 — AI Executive Assistant NLU** | Foundation: NLU contract that Max will wrap |
| **Этап 8 — Stability Gate** | "Максим работает через AI Assistant" — this is the first real usage context; Max layer should not break Этап 8 requirements |
| **TD-029 — Selective Channel Routing Policy** | Directly related: channel routing is the mechanism this idea formalizes |
| **IDEA-20260324-001 — Owner Intent Memory** | Max reads the memory layer at session start; dependency |
| **IDEA-20260324-003 — Personal Scheduler** | Max is the UX surface; Scheduler is the planning logic underneath |
| **COGNITIVE LAYER (Local PC, NO side-effects)** | Max UI components that run locally comply with this constraint |
| **North Star: минимизировать manual_interventions** | Direct motivation: voice-first capture reduces friction to near-zero |

### What this does NOT touch

- Core FSM, Guardian, reconciliation — not in scope.
- Frozen Files (DNA §3) — not in scope.
- Pinned API (DNA §4) — not in scope.
- Telegram routing code in Этап 7 — remains unchanged until explicit migration decision.
- Master Plan and Roadmap — **not modified** at DRAFT stage.

---

## 4. Goals

1. Define a **channel-agnostic assistant contract**: what the owner assistant *is* vs. what it *runs on*.
2. Establish "Max" as the product identity for the primary owner-facing interface
   (name, not a model — any AI can power it).
3. Specify Telegram's role post-Max: **fallback + alerts + export + reserve channel**.
4. Define voice-first capture as a first-class input path (not bolted on later).
5. Ensure Owner Intent Memory (IDEA-001) can be surfaced through any Max-compatible channel
   without channel-specific logic.

---

## 5. Non-Goals

- Do NOT rewrite Этап 7 Telegram code now.
- Do NOT build Max UI (web app, desktop, voice terminal) now — proposal only.
- Do NOT create a new NLU model or replace the intent engine.
- Do NOT define Max branding/naming in authoritative docs before promotion.
- Do NOT overlap with Personal Scheduler (IDEA-003) — Max is the interface, Scheduler is
  the planning logic. They communicate; they are not merged.
- Do NOT change Telegram alert/export functionality (R2).

---

## 6. Core Thesis

**Assistant = Logic + Interface. Max = the interface contract.**

```
Owner
  │
  ├─ Max (primary)          ← web / desktop / voice terminal / future
  │    reads: Owner Intent Memory (IDEA-001)
  │    calls: NLU intent engine (Этап 7 contract)
  │    calls: Personal Scheduler (IDEA-003)
  │
  └─ Telegram (fallback)    ← alerts / export / emergency commands
       15 commands remain
       R2 export remains
```

Channel adapter contract (interface, not implementation):

```
ChannelAdapter:
  send_message(text, buttons)
  receive_input() → RawInput
  request_confirmation(prompt) → bool
```

NLU engine and Task Engine (Этап 6/7) remain channel-unaware.
Max/Telegram adapters implement the ChannelAdapter interface.

---

## 7. Consumers

| Consumer | Role |
|----------|------|
| **Owner (primary)** | Uses Max as the main daily interface |
| **Owner (fallback)** | Uses Telegram for alerts and quick commands when Max unavailable |
| **Owner Intent Memory (IDEA-001)** | Read by Max at session start for context injection |
| **Personal Scheduler (IDEA-003)** | Surfaces today's plan / reminders through Max |
| **AI Assistant (NLU, Этап 7)** | Powers the intent resolution behind Max |

---

## 8. Data Sources

| Source | What it provides |
|--------|-----------------|
| Owner Intent Memory (IDEA-001) | Context Profile, Active Threads, SOP Registry |
| NLU intent engine (Этап 7) | Parsed TaskIntent from owner input |
| Personal Scheduler (IDEA-003) | Today's plan, pending reminders |
| Core read-only views | Order status, shipment status (no direct Core table access) |

---

## 9. Constraints

1. **No side-effects from UI layer.** Max interface components must not write to Core tables directly.
   All mutations go through the Task Engine / Executor (Этап 6/7 contract).
2. **INV-MBC must hold.** Button confirmation (Mandatory Button Confirmation invariant) applies
   regardless of channel. Max must implement this via its own confirmation flow.
3. **Telegram remains active** until explicit deprecation decision — no silent removal.
4. **Channel-agnostic = no Telegram-specific logic in NLU engine.** NLU engine must not
   contain `if telegram:` branches.
5. **Voice-first capture is input-only.** Voice → text transcription → standard NLU pipeline.
   No voice output required at DRAFT scope.

---

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Max scope creep into full-stack app | High | High | Strict non-goals; channel-agnostic contract only at DRAFT |
| Telegram migration breaks active workflows | Medium | High | Telegram stays active as parallel channel; no migration until Max proven |
| Voice capture adds dependency on third-party STT service | Medium | Medium | Voice = optional add-on; text input sufficient for MVP Max |
| INV-MBC violated in new channel | Low | Critical | Channel adapter contract must include confirmation step as mandatory |
| IDEA-001 + IDEA-003 scope bleeds into this idea | Medium | Medium | Explicit non-goals; dependencies documented, not merged |

---

## 11. Promotion Options

### Option A (recommended) — TD-029 expansion + sub-stage under Этап 8+

1. Expand TD-029 (Selective Channel Routing Policy) to reference this proposal.
2. Add sub-stage 8.5 "Channel Abstraction Design" to EXECUTION_ROADMAP under Этап 8 or post-8.
3. Define ChannelAdapter interface as a design artifact (not code) in MASTER_PLAN.

### Option B — New TD entry

Create TD-048: Channel-Agnostic Executive Interface. Deferred review: post-Этап 8 stable.

### Option C — Park

Defer entirely until Этап 8 (Stability Gate) is closed and Telegram UX pain is measured.
Re-evaluate with real usage data.

---

## 12. Open Questions

1. **"Max" name scope:** Is "Max" a UI product name, an internal alias, or a future brand?
   Does naming conflict with "Максим" (owner name) in Этап 8.1 context?
2. **Voice capture infra:** What STT service is acceptable? Local model (Whisper on Local PC)
   or third-party API? Privacy implications for voice of business intent?
3. **ChannelAdapter protocol:** gRPC? REST? Python ABC? Which part of the stack owns this interface?
4. **Migration path from Telegram:** When does Telegram move from primary to fallback?
   What usage threshold triggers the switch?
5. **Max and Personal Scheduler coordination:** Who initiates the morning briefing —
   the Scheduler pushes to Max, or Max polls the Scheduler?

---

## What a Critic Should Check

- Does the channel-agnostic contract actually decouple NLU from Telegram,
  or does it just add an abstraction layer that Telegram still bleeds through?
- Is TD-029 the right anchor for this idea, or does it need a new TD?
- Is the Telegram → fallback transition a realistic path given current Этап 7/8 architecture?
- Is voice-first capture scoped correctly, or is it a hidden large dependency?
- Does IDEA-001 (Owner Intent Memory) need to be promoted first before this idea can proceed?

---

## Current Recommendation

**Status: DRAFT. Do not promote to plan until Этап 8 completes and Telegram UX limitations
are measured empirically.** The proposal is ready for CRITIC review as-is.

---

## Review Log

| Date | Reviewer | Status change | Notes |
|------|----------|---------------|-------|
| 2026-03-25 | Claude Code (SCOUT) | INBOX → DRAFT | Proposal created per owner request. No code. |
