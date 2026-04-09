# Escalation Protocol

When a role cannot proceed, it must escalate — not improvise.

## Escalation Rules

### CRITIC finds BLOCKER
→ Task returns to ARCHITECT for redesign.
→ Max 2 round-trips between ARCHITECT and CRITIC.
→ After 2nd BLOCKER on same issue → STOP, notify owner.

### JUDGE says REJECT
→ Task returns to ARCHITECT + CRITIC cycle.
→ Max 2 redesign attempts. After 2nd REJECT → STOP, notify owner.

### BUILDER deviates from plan
→ BUILDER STOPs immediately.
→ Deviation description goes to PLANNER for plan amendment.
→ If PLANNER cannot amend without ARCHITECT input → escalate to ARCHITECT.
→ Detection: AUDITOR compares PLANNER plan vs BUILDER result post-factum.
  A4 scope check covers file-level drift but not semantic drift.

### AUDITOR finds can_ship: NO
→ Task returns to BUILDER with blocker list.
→ BUILDER fixes and re-submits.
→ Max 2 returns. If same blocker appears on 3rd check → STOP, notify owner.

### SCOUT finds Tier-1 files in scope
→ Immediate STOP. Notify owner before any design work begins.

### Owner unresponsive
→ 24h after request: send reminder.
→ 72h after request: park task in `STATE.md` with `#stalled`.
→ Record in KNOW_HOW.md with `#stalled` tag.
→ Does NOT proceed with assumptions.

### API outage during external audit
→ 1 retry after 60s.
→ If still failing → park with `parked_api_outage` in `STATE.md`.
→ Owner notification. No model substitution.

## Loop Limits Summary

| Loop | Max iterations | After limit |
|------|---------------|-------------|
| ARCHITECT ↔ CRITIC | 2 round-trips | STOP + owner |
| BUILDER → AUDITOR | 2 returns | STOP + owner |
| JUDGE REJECT | 2 redesigns | STOP + owner |
| Full task | ~80 min wall clock | STOP + park |

## General Rule

No role may assume another role's approval.
No role may skip escalation to meet a deadline.
Silence from the next role = STOP, not "proceed".

## Known Risks (Layer 3 — fundamental LLM limitations)

These are acknowledged risks without complete technical fixes.
They are mitigated, not eliminated.

1. **Echo chamber**: Same model builds and audits → shared blind spots.
   Mitigation: external CRITIC/AUDITOR for SEMI/CORE; for LOW — deterministic gates.

2. **Context degradation**: 7-role chain loses nuance at each relay.
   Mitigation: structured artifacts preserve key facts; compression for LOW.

3. **Lessons ≠ enforcement**: Know-how in prompt is advice, not constraint.
   Mitigation: A4 scope check is deterministic; lessons supplement, don't replace.

4. **Governance erosion**: Pressure to skip reviews, downgrade risk, merge faster.
   Mitigation: risk classification requires owner approval to change; SEMI requires owner ACCEPT.

5. **Theater of artifacts**: Form without substance — reports exist but verify nothing.
   Mitigation: AUDITOR absolute prohibitions; self-check before reporting; owner checklist.

6. **Risk misclassification**: Wrong risk level → wrong pipeline → wrong controls.
   Mitigation: risk change requires owner approval; SCOUT checks Tier on entry.
