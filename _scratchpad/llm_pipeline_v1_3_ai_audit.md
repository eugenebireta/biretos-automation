# v1.3 Plan — 3-AI Audit Results (2026-04-17)

Three parallel reviewers (architecture, governance, engineering). Consensus: **NOT APPROVABLE. 3 new blockers, multiple serious issues.**

## NEW BLOCKERS (must fix)

### B1. P5 sensitivity table uses inconsistent N citation counts (arch)
Re-deriving each row shows the table mixes N=2 and N=3 silently:
- "T1-URL fresh + both agree = 0.988" requires N=3
- "T1-DR exact + both agree = 0.877" requires N=2
- "T2b×3 stacking = 0.780 capped" requires N=3

**For realistic SKUs with N=1 citation (the common case), T1-DR exact + both agree = 0.776 → tiebreaker, NOT apply.** The v1.2 B2 defect (one abstain → tiebreak) is **not fixed, just hidden behind ambiguous N**. Same arithmetic class of error as v1.2 (3rd consecutive version).

### B2. `brand_source` field exists in only 174/374 evidence files (47%) (eng)
§2 P2 makes `brand_source` the verification timestamp for T1-DR and T1-DR-w. Empirical check: `grep -l brand_source downloads/evidence/*.json | wc -l = 174`. **For 53% of SKUs per-tier decay silently falls back to default**, invalidating the entire sensitivity table for those cases. Plan has no fallback rule or backfill task.

### B3. Evidence schema is NOT what v1.3 describes (eng)
Reviewer read 4 evidence files (1000106, 00020211, 2CDG110146R0011, 36022-RU). Dominant schema spine is `policy_decision_v2`/`field_statuses_v2`/`review_reasons_v2`, NOT the `structured_identity`-centric structure v1.3 assumes. `confirmed_manufacturer` appears on a subset. §3.1 "schema variations via field-level defaults" glosses over the mismatch. A1 budget 1d is 3-5× too tight; needs Phase A0 schema inventory.

### B4. Gate A-F evaluation order unspecified (arch)
§2 P5 doesn't state sequence or short-circuit semantics. §7 journal shows F always populated even when B fails. "Gates A-F, all deterministic" without ordering = refactor-fragile.

### B5. Silver tier trigger reads Core DB, contradicts §P10/§7 (eng)
§P8 silver requires "no customer complaint in Core `rev_*` tables within 90 days". §P10 says no Core reads. Silver tier becomes dead code because the read path doesn't exist and isn't sanctioned.

## SERIOUS (fix before ship)

### S1. Wilson CI arithmetic inflated (arch)
"143/150 gives CI lower bound ≈91.2%" — correct value is **90.68%**, inflation of 0.5pp. At 140/150 (93.3%) lower bound is **88.16%**, not 91.2%. Minor but: 3rd consecutive arithmetic error across v1/v1.1/v1.2/v1.3.

### S2. P9 Rule (c) "≥2 T2b+ siblings with X" perpetuates cycles (arch)
If historically entire FX-series mis-tagged PEHA, any new "Esser" proposal blocked by Gate E. Rule treats sibling majority as ground truth without citation independence. Fix: require ≥2 siblings with different source URL domains.

### S3. P8 silver "no complaint 90d" clock anchor unspecified (arch)
For zero-sales SKUs (long-tail DKC/PEHA), no complaint timer starts. Silver never activates. Training data skews toward high-volume Honeywell.

### S4. AUDITOR mechanism undefined (gov)
§4 C3 "external AUDITOR pass evaluates precision" — no role spec path, no invocation mechanism, no artifact path. Without binding = self-auditor de facto, v1.1 failure mode re-introduced.

### S5. §9 handshake = 2 risk classes in 1 PR (gov)
"Same PR removes Step 1 guard AND flips gate live" violates R1 §7 single-risk-class rule. Should be 2 PRs with soak period.

### S6. No kill switch / canary at §8 promotion (eng)
If live batch corrupts 30 SKUs in 20 min, rollback is git revert + manual replay of reversible_patch. Missing: `gate_mode: shadow|live|off` config flag + 10-SKU canary before full batch.

### S7. Test suite 4-7d minimum, not budgeted (eng)
8 test files @ 0.5-1d each = 4-7d. Phase B bundles tests with logic. Budget gap 2-3d.

### S8. Telegram digest via biretarus_bot.py wrong surface (eng)
`biretarus_bot.py` is 1066-LOC T-Bank/CDEK invoice bot. Zero digest/broadcast API. §3.10 "existing biretarus_bot.py" is not free; needs new send-only client OR `@bireta_code_bot`. +0.5-1d.

### S9. P7 error schema ErrorClass enum doesn't exist in repo (eng)
`POLICY_VIOLATION` referenced in CLAUDE.md but no `scripts/pipeline_v2/errors.py` module. +0.5d to build.

### S10. Grep-based no_forbidden_imports insufficient (gov)
Misses transitive imports, dynamic imports, subprocess calls to writers. Need AST walker + import graph closure.

### S11. A4 splits policy surfaces (gov)
Hold-out construction (data/labeling policy) + baseline measurement (decision-semantics validation) = 2 surfaces. Must split A4a/A4b per R1 standard.

### S12. Owner authorization path undefined (gov)
"Owner written authorization" referenced twice, no canonical artifact path or verification mechanism.

### S13. A4 labeling 10h owner for n=150 under-scoped 2-3× (eng)
Critic #3 said n=50 = 8-12h. Linear scale: n=150 = 24-36h. Plan says 10h. Plus stratified selection needs prior evidence coverage analysis (~1d).

### S14. Phase D 3 weeks optimistic (eng)
EAN + specs + category each needs own hold-out + AUDITOR pass. Specs has unit-normalization domain work. Realistic 4-5 weeks.

### S15. Phase D risk class drift (gov)
EAN/specs/category feed Revenue adapters (Ozon/WB sync). Wrong EAN → marketplace delisting risk. Should be SEMI-high or split plan.

### S16. Audit trails in `_scratchpad/` (gov)
Load-bearing governance artifacts referenced from the plan belong in `docs/_governance/audits/`, not throwaway scratchpad.

## REALISTIC TIMING

Reviewer #3 (eng): **9-10 weeks**, not 7-8. Adds: Phase A0 schema inventory, evidence_pack legacy mapping (B3), A4 labeling reality, Phase D realism, integration seams (digest, errors, brand_source backfill).

## CONSENSUS

All 3 reviewers approve concept + direction. **None approve for build.**

Pattern: 3 versions in a row, 3 arithmetic errors. v1.2 had 0.34→0.565 bug. v1.3 has N-ambiguity + Wilson 91.2→90.68. Suggests plan-from-head without empirical grounding is structurally unreliable.

## Reviewer #1 verdict
"Reject v1.3 for Phase A start. Require v1.4 with (a) single-N sensitivity table, (b) gate evaluation DAG, (c) 90d silver clock anchor, (d) Wilson CI corrected, (e) sibling independence requirement."

## Reviewer #2 verdict
"Not yet approvable. Must-fix before Phase A: split A4, bind AUDITOR, split guard-removal + shadow→live into 2 PRs, name authorization artifact path, relocate audit trails, AST walker for import test, typed redactor, reclassify Phase D."

## Reviewer #3 verdict
"Architecturally ready for external review. Before BUILDER starts: Phase A0 schema inventory, brand_source backfill, digest surface clarity, drop silver Core-read or define view, gate_mode flag + canary, widen timing to 9-10 weeks OR narrow Phase D to EAN only."

## Decision for owner

Three cycles of audit have converged on: **plan maturity plateau reached**. Each version fixes prior blockers but introduces new ones at a similar rate because the design is being built in a vacuum without running code.

Two options:
- **A.** Write v1.4 fixing B1-B5 + key serious. +1-2 hours. Expect cycle 4 to find its own new blockers.
- **B.** Stop planning. Accept plan is architecture doc (good), not build spec (not yet). Return to catalog work. Write v1.4 only when R1 gate is green AND real empirical data (hold-out labels, actual evidence coverage) is available.

**Strong recommendation: B.** The blockers at this point are data-reality problems (brand_source 47% presence, schema mismatch), not plan-text problems. Plan-text iteration cannot solve them.
