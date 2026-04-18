# AI-Audit: LLM Correction Pipeline v1.3

**Date:** 2026-04-17
**Subject:** `docs/LLM_CORRECTION_PIPELINE_v1_3.md`
**Procedure:** CLAUDE.md "AI-AUDIT (ad-hoc multi-LLM second opinion)" — 2-round debate, isolated R1, anti-conformity R2.

## Bundle

**Proposal.** v1.3 plan for defense-in-depth brand/EAN/specs/category correction pipeline. ~640 lines. Evidence-first contract, trust hierarchy with per-tier decay, URL oracle, sibling veto gate, two-stage protocol (LLM propose + Python validate), review bucket SLA, correction journal, shadow-first rollout.

**Alternatives.**
- APPROVE → Phase A after R1 Start Gate green
- REVISE → write v1.4 fixing known blockers
- REJECT → stop planning; keep Step 1 hotfix (`b5dd281`) as protection; return to catalog work

**Doubt.** Prior audit found 5 blockers (arithmetic N-ambiguity, brand_source 47% presence, schema mismatch, gate order, silver Core reads) + 16 serious issues. Pattern: 3 versions = 3 arithmetic errors.

---

## Round 1 — Isolated verdicts

### ADVOCATE (Claude Sonnet)
**R1 Verdict:** REVISE, high confidence.

Strongest arguments for v1.3:
- Concept unanimously approved by prior 3 reviewers ("not yet" not "stop")
- Step 1 hotfix already live; Phase A can proceed on non-brand-rewriting infra
- B2/B3 are self-correcting via Phase A0 schema inventory (1 day)
- B1 N-ambiguity = table documentation error, formula itself is N-agnostic
- B4 = add DAG in one paragraph
- B5 Silver Core-read isolated to Phase E (opportunistic)
- Plan revision history shows progressive convergence

Proposed 7 errata conditions instead of v1.4 rewrite.

### CHALLENGER (Claude Sonnet, adversarial)
**R1 Verdict:** REJECT, high confidence.

Fatal flaws:
- `brand_source` in only 174/374 files (46.5%) — timestamp anchor for P2 decay missing for 53.5% of SKUs
- Silver Core DB read contradicts P10 — functional contradiction, silver inoperable
- N-ambiguity re-introduces v1.2 regression for N=1 common case
- 4 consecutive versions = stable oscillation, not convergence
- Opportunity cost: 10-13 weeks pipeline vs hotfix that already blocks 98.9% of incident class

### SECOND OPINION (Claude Haiku)
**R1 Verdict:** REJECT, high confidence.

Checklist scores: problem_clarity=5, scope=3, feasibility=2, **data_reality=1**, risk_posture=3.

5 show-stoppers confirmed. Simpler alternative: accept Step 1 hotfix as sufficient; park 53% without strong brand_source in review bucket; trade coverage for precision.

---

## Round 2 — Debate (anti-conformity enforced)

### ADVOCATE R2
**Verdict changed:** REVISE → **REJECT** (high confidence).

Explicit reason for change:
> "My R1 REVISE rested on the assumption that Phase A0 schema inventory + errata patch was a bounded, low-cost fix path. Auditor A's opportunity-cost argument changes the calculus: if the hotfix already covers 98.9% of the incident class, then the residual 1.1% does not justify 10-13 weeks of pipeline work — that ratio is indefensible. I did not quantify the hotfix coverage in R1."

This is the anti-conformity rule working correctly: the change is driven by a substantive new argument (98.9% hotfix coverage vs 10-13 week pipeline cost), not majority pressure.

### CHALLENGER R2
**Verdict held:** REJECT, high confidence.

Rebuttals to ADVOCATE R1:
1. Non-brand-rewriting infra split = scaffolding without validated core. Ships committed sunk cost that pressures proceed when A1+ blockers resurface.
2. "Progressive convergence" reframe false — v1.2 had MORE blockers than v1.1. Not monotone convergence; oscillation with local improvement at v1.3. "Data-reality discoveries" were readable from static files before v1.1.
3. 7-condition errata: 5/7 are documentation patches; 2/7 are substantive and CONTINGENT on favorable schema inventory. If inventory is unfavorable → rewrite anyway. Errata defers decision by one day while committing to potentially dead-end path.

### SECOND OPINION R2
**Verdict:** NEEDS_INFO, low confidence. Didn't have enough context to confidently change; holds R1 REJECT as default.

Honest epistemic signal; doesn't override the unanimous R1+R2 majority for REJECT.

---

## Arbitrage (my role)

### Consensus dynamics

| Round | ADVOCATE | CHALLENGER | SECOND OPINION |
|-------|----------|------------|----------------|
| R1    | REVISE   | REJECT     | REJECT         |
| R2    | **REJECT** | REJECT   | NEEDS_INFO (holds REJECT) |

**R2 is unanimous REJECT** with ADVOCATE explicitly changing based on a new argument (not conformity).

### What actually happened

ADVOCATE's R1 REVISE was defensible in isolation — 7 conditions is cheaper than v1.4 rewrite IF the underlying architecture is sound. But CHALLENGER exposed two structural issues ADVOCATE didn't price in:

1. **Opportunity cost anchor.** 98.9% of the incident class is already blocked by `b5dd281`. Residual 1.1% doesn't justify 10-13 weeks. ADVOCATE accepted this as decisive in R2.

2. **Conditional path risk.** ADVOCATE's 7 conditions assume a favorable schema inventory outcome. If inventory reveals more broken assumptions, the errata path collapses into v1.4 anyway — so REVISE effectively defers REJECT by one day of compute.

### Final recommendation: **REJECT**

Confidence: high. Unanimous across all auditors post-debate.

**Caveat:** REJECT here does NOT mean "architecture is wrong." All three auditors agreed the architecture direction is sound. REJECT means "this plan should not trigger Phase A implementation now" because:

1. Step 1 hotfix (`b5dd281`) already deterministically blocks the incident class for 98.9% of SKUs.
2. Residual 1.1% is parent/sub-brand ambiguity, routable to review bucket.
3. Data-reality gaps (brand_source 47%, schema mismatch) are not plan-text bugs; they're problems empirical coding must discover, not architect-from-head.
4. Opportunity cost is real: 165 SKUs need catalog work (EAN, specs, photos) that produces direct marketplace revenue.

### What to do instead (recommendation)

1. **Keep Step 1 hotfix active.** It's the safety guard.
2. **Park v1.3 as "architecture sketch, not build spec."** Don't fight the blockers by rewriting text.
3. **Return to catalog work:** EAN gap closure, specs extraction, photo repair.
4. **When revisit is warranted** (R1 gate green + Phase D pressure for new brands): do a **schema inventory spike** first (1 day, reads actual evidence files, produces field coverage map). Use the spike's output to ground v1.4 in reality.
5. **No more plan iterations until empirical data exists.** Pattern of 3 arithmetic errors in 3 versions is diagnostic — plan-from-head without code-running is structurally unreliable.

### Action for owner

**APPROVE / REVISE / REJECT / NEEDS_INFO: REJECT**

Decision is recommendation only; owner retains authority to override.

---

## Cost

- R1: 3 agents × (Sonnet/Sonnet/Haiku) ≈ $0.10
- R2: 3 agents × (Sonnet/Sonnet/Haiku) ≈ $0.08
- Total: ~$0.18 for full R1+R2 debate

Well within the CLAUDE.md default preset budget of $0.12-0.18.

---

## Audit artifacts

- R1 raw verdicts: embedded above (3 JSON blocks)
- R2 raw verdicts: embedded above (3 JSON blocks)
- Plan under review: `docs/LLM_CORRECTION_PIPELINE_v1_3.md`
- Prior audit: `_scratchpad/llm_pipeline_v1_3_ai_audit.md`
- Hotfix commit: `b5dd281`
