# v1.2 Plan — External AI Audit Results (2026-04-17)

3 external chat AIs reviewed `docs/LLM_CORRECTION_PIPELINE_v1_2.md`.
Consensus: **good spec, NOT go-build spec**. Need v1.3.

## BLOCKERS (convergent, must fix before Phase A)

### B1. P5 rationale arithmetic wrong — threshold built on bug
My v1.2 §2 P5 rationale says "0.34 renormalized if both abstain". Correct
math: `(0.3×0.33 + 0.3×0.80) / 0.6 = 0.565`, not 0.34. **Forgot to divide
by total_weight 0.6.** The 0.85 threshold was calibrated against a wrong
number. All sensitivity points need recalculation.

### B2. Auto-apply rate ≠ claimed 41/55
Verified by critic #3 on concrete cases:
- FX808313 (T1-DR exact + URL agree + sibling agree): 0.877 → apply ✓
- T1-DR exact + **URL abstain** + sibling agree: 0.846 → **tiebreaker**
- T1-DR exact + URL agree + **sibling abstain** (orphan PN): 0.846 → **tiebreaker**

**One external signal abstaining = drops below 0.85.** Many real SKUs
lack either manufacturer-domain URLs or ≥3 siblings. Realistic
auto-apply rate likely 20-25/55, not 41/55. Threshold too strict OR
formula weighting wrong.

### B3. Hold-out 50 SKU statistically insufficient
Biminomial Wilson CI for 48/50=96%: [86.5%, 99.5%]. Cannot
statistically distinguish 93% (exit clause) from 95% (ship).
Need **n≥150** or explicitly document "point estimate not statistical proof."

### B4. Silent Consensus Risk in renormalization (critic #2)
Renormalizing weights when URL+sibling abstain makes it *easier* to
cross 0.85 with just text citations. 3 weak T2b citations + abstained
externals → confidence 0.85. LLM can auto-apply on text alone.
**Fix:** abstention cap — if both URL and sibling abstain, cap
max confidence at 0.84.

### B5. Gate E soft-failure regression
P9 says: if LLM proposes sub-brand without specific evidence → "downgrade
to parent-only (soft failure)." Critic #3: this overwrites existing
correct sub-brand (e.g. Notifier → Honeywell), **defeating P9's purpose.**
Fix: soft failure → review bucket, NOT parent downgrade.

### B6. Citation stacking bug (critic #3)
Gate A+B: LLM can cite 1 strong path + 5 T5/T4 mud paths. Gate A passes
(existence), Gate B passes (max tier), citation_score=1.0 from count.
Confidence inflated by low-quality citations.
**Fix:** (a) require values at all cited paths agree with proposal,
(b) exclude T4 from citation_count (it's the target, not evidence).

### B7. §8 guard/override handshake in Phase A-C period
Both Step 1 guard (active) and new gate (shadow) will run during A-C.
Unclear which writes evidence when. **Fix:** new gate runs shadow-only
until Phase C3 green, then in same PR: remove old guard + enable gate writes.

## SERIOUS (fix before Phase B)

### S1. Per-tier freshness decay
18-month halflife for all tiers is wrong. T2a (datasheet PDF, physical
specs) should barely decay. T1-DR (web research, companies rename) can
decay faster. Critic #3 proposes per-tier `decay_halflife_months` in
config; critic #2 argues B2B industrial needs 36-48 month divisor overall.
Either per-tier or flatter curve — current 18mo is aggressive for
industrial catalog.

### S2. Labeling bias in hold-out
Owner designs pipeline + labels ground truth = circular. Critic #3: need
second human labeler OR labels made before design finalization.

### S3. Disjoint guarantee
Need explicit: hold-out 50 ∩ 19 incident PNs = ∅. Currently implicit.

### S4. Adversarial stratum undersized
Critic #2+#3: 5 conflicting T1-URL vs T1-DR SKUs can't validate override
path. Expand to 10 minimum.

### S5. Sub-brand stratification
2 per sub-brand = pyl. Need ≥5 per sub-brand × 5 sub-brands = 25 SKUs
in that stratum alone.

### S6. max() non-determinism in Gate B
If two paths have equal effective_trust, iteration order decides. Fix:
require consistency of all top-tier values; collision → Gate B fail with
"tier collision" reason.

### S7. Review bucket expiry = silent failure
30-day archive without decision is silent failure of "never apply and
hope" principle. Fix: journal `decision: "expired"` entry + Telegram
digest counter for items >21 days.

## TIMING PROBLEMS (critic #2+#3)

- **A4 1.5d:** owner labeling 50 SKU = 8-12 real hours over 3-5 cal days. Not 1.5d.
- **B2 1.5d:** 200-URL golden dataset = ~4-6h owner time, calendar week.
- **C1 2d:** orchestrator wiring LLM+evidence_pack+trust_hierarchy+oracle+sibling = 3d min.
- **C3 2d:** external AUDITOR not on your calendar — add buffer.
- **No tuning buffer** after precision <95%.

Realistic: **7-8 weeks with buffer**, 5-6 happy path.

## DEFERRED / MINOR

- Tiebreaker LLM call returns LLM to Stage 2 contour — rename "Python validation + optional tiebreaker branch."
- Category gate weakest — consider deferring after brand/EAN/specs ship cleanly (critic #1).
- Schema variations in 374 legacy evidence files — compute-at-load strategy needs explicit fallback for missing fields (critic #2's open question).
- Cost ceiling: put a number. Critic #3 estimate: ~$1.80 per full brand pass; ~$7.20 across 4 gates; ~$50 total dev budget. Record this.
- DNA §7 item 4 missing in §2 P7 listing — mark N/A explicitly.
- Q-FRESH: consensus 365d hard + soft decay after 180d (critic #1).
- Q-ARCHIVE: infinite archive, cap active queue only (critic #1).

## CONVERGENT VERDICTS

- Critic #1: "v1.2 = good spec, not yet go-build spec"
- Critic #2: approved concept + interactive simulator to visualize; wants per-tier decay + abstention cap + bigger adversarial stratum
- Critic #3: "численная корректность P5 и размер hold-out — два блокера, которые превратят Phase C3 в проверку на шумной выборке по неправильной формуле. Остальное — доработка, не переработка."

## DECISION

Need v1.3 with:
1. Correct P5 arithmetic + recalibrated thresholds based on real math
2. Formula revision: either lower threshold or weight shift to not penalize abstention
3. Hold-out n≥150 OR explicit "indicative not statistical"
4. Gate E: soft fail → review, not parent downgrade
5. Citation coherence check (value agreement, exclude T4)
6. Handshake protocol between guard and gate in Phase A-C
7. Per-tier freshness decay
8. Stratification fix + disjoint guarantee + labeling-bias protection
9. Timing revisions: A4/B2 owner-labor; C1 +1 day; +tuning buffer
10. Review bucket expiry journal entry
11. Cost ceiling number; DNA item 4 note

Step 1 hotfix (b5dd281) remains the only live protection.
