# Escalation Protocol

When a role cannot proceed, it must escalate — not improvise.

## Escalation Rules

### CRITIC finds BLOCKER
→ Task returns to ARCHITECT for redesign.
→ If ARCHITECT cannot resolve → STOP, notify owner with BLOCKER description.

### JUDGE says REJECT
→ Task returns to ARCHITECT + CRITIC cycle.
→ Max 2 redesign attempts. After 2nd REJECT → STOP, notify owner.

### BUILDER deviates from plan
→ BUILDER STOPs immediately.
→ Deviation description goes to PLANNER for plan amendment.
→ If PLANNER cannot amend without ARCHITECT input → escalate to ARCHITECT.

### AUDITOR finds can_ship: NO
→ Task returns to BUILDER with blocker list.
→ BUILDER fixes and re-submits.
→ If same blocker appears twice → STOP, notify owner.

### SCOUT finds Tier-1 files in scope
→ Immediate STOP. Notify owner before any design work begins.

### Owner unresponsive
→ Agent parks the task with status `WAITING_FOR_OWNER`.
→ Writes reason and blockers to `docs/autopilot/STATE.md`.
→ Does NOT proceed with assumptions.

## General Rule

No role may assume another role's approval.
No role may skip escalation to meet a deadline.
Silence from the next role = STOP, not "proceed".
