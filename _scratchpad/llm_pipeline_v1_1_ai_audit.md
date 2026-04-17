# v1.1 Plan — 3-AI Audit Results (2026-04-17)

## Cross-reviewer BLOCKERS (must fix before Phase A)

1. **Gate F threshold unspecified** (arch) — §2 P5 says "≥ threshold" but no number. Unshippable.
2. **T0 phantom tier** (arch) — §2 P4 and §6 reference "T0-T2" but tier table in P2 starts at T-H/T1. Undefined.
3. **P5 computed confidence formula is symbolic, not computable** (arch + eng) — `citation_score`, `tier_score`, `url_oracle_agreement`, `sibling_agreement` have no definitions. Implementer will invent these and break shadow calibration.
4. **Guard vs override-path contradiction in §9** (eng) — `t1_brand_guard` skips ALL SKUs with T1 populated; new gate needs to override T1 on stale-multi-source consensus. Plan says "guard wraps gate entry" → override path never exercisable.
5. **Shadow ≥95% self-evaluation violates "Executor not judge"** (gov) — precision must be computed by external AUDITOR, not by gate code.

## Architecture defects (from reviewer A)

- Tier numerics non-monotonic: T1-DR weakened (0.85) < T2a (0.88) but label says T1 > T2.
- Freshness decay floors at 0.6× at 10 months then flat — 10-year-old T1-URL (0.57) still beats T4 (0.50).
- Consensus lift 0.97 for 2×T2 exceeds T1-URL (0.95) → two third-party PDFs outrank manufacturer URL.
- Freshness decay references `last_verified` field that only exists on P3 URL Oracle, not on T1-DR/T2a/T2b.
- Zero-siblings / zero-URL edge cases penalize correctness (any SKU without siblings capped at 0.80).
- Abstain semantics missing — absence of signal indistinguishable from disagreement.
- Tier + citation components double-count the same tier value.
- P4 sibling threshold behavior varies by cluster size: 3 siblings need 100%, 5 siblings need ≥80%, 4 siblings 75%<80% = no veto.
- "Veto only" claim is nominal — proposal passes when siblings agree means siblings effectively decided.
- P2 override path has no freshness weighting; state-dependent non-idempotence when batched twice.
- **P9 sub-brand preservation doesn't disambiguate within parent family** — PEHA vs Esser both Honeywell, registry is set-membership not disambiguation.
- **P9 doesn't catch false T1-DR cross-brand confusion** (Cisco↔Honeywell case) when no URL or siblings contradict.
- **P8 silver 60-day window too short** — catalog revert latency is months to years (customer returns, re-audits). Silver contaminates at ~gate-error-rate per batch, feedback loop drifts silently.
- "Used with lower weight" unquantified.

## Governance defects (from reviewer B)

- DNA ref §11 is wrong — canonical is **§7** for new-Tier-3 mandatory patterns.
- Missing DNA §7 item 5: no redaction rule for `before/proposed` payloads (may contain token-bearing URLs).
- Missing DNA §7 item 9: no `error_class` (TRANSIENT/PERMANENT/POLICY_VIOLATION) / `severity` / `retriable` in error log schema.
- Missing DNA §7 item 6: CLI entrypoint commitment not called out per module.
- No owner authorization citation — plan opens a new governed decision layer (adjacent to Stage 8.1 "local review fabric") which DNA §1c says needs "отдельного batch и отдельного owner instruction".
- **Phase A violates R1_PHASE_A_BATCH_EXECUTION_STANDARD:** bundles evidence_pack + journal + retrofit + hold-out = 3+ policy surfaces. Must split A1/A2/A3/A4. Same for Phase B.
- Future journal table (if promoted to DB) must use `rev_*`/`stg_*` prefix per DNA §5b.
- `review_bucket apply` scope must be explicit: writes only to evidence JSON + journal, never to adapters/InSales/Shopware.
- URL Oracle config file must be manually reviewed (not auto-updated by pipeline), else de facto second truth layer.
- Plan classification: **🟡 SEMI**; currently at ARCHITECT stage post-CRITIC; next stop PLANNER, not BUILDER.

## Engineering defects (from reviewer C)

- Golden 1000-URL dataset hidden cost: 2-3 dev-days alone, buried as one-line §8 checkbox.
- Phase B 5-7d realistic only if golden dataset descoped to ~200 URLs.
- Phase D 2 weeks optimistic: EAN/specs/category are three different evidence shapes/ontologies, not copy-pastes of brand gate. Realistic 3 weeks.
- §3.8 specs gate hits ontology problems (unit normalization, dimensional vs electrical) not acknowledged.
- §3.10 daily digest mentions SMTP — no SMTP layer exists in repo.
- **§5 hold-out stratification unspecified** — 50 SKU random from brand-skewed corpus (Honeywell 302/374) won't exercise T4 legacy or sub-brand paths. Need X Honeywell, Y DKC, Z sub-brand, W parent-only, V no-T1.
- §5 criterion 5 (median age <14d) only measurable in production — not a phase gate, operational SLI.
- **93% plateau has no exit clause** — engineers will either game hold-out or stall indefinitely. Need: "after 2 tuning iterations, either lower coverage or accept 93% with documented residual risk."
- §8 pre-flight missing: EvidencePack schema version, migration story, baseline precision measurement, review_bucket path confirmation, cost ceiling for Stage-1 across 374 SKUs.
- §2 P7 journal doesn't capture per-gate failure reason — "why SKU X in review" unanswerable.
- No trace correlation to DR batch log or Stage-1 LLM transcripts — misfires unreconstructible.
- url_brand_oracle flat JSON + regex hurts at ~500 entries; migrate to SQLite/YAML-per-brand at 200+.
- **Test suite needs 6 files minimum, currently has 1** (test_t1_brand_guard.py).
- Data migration story absent: adding T2a/T2b/T1-H provenance flags — enrich evidence files in place (irreversible) or compute at load time. Plan implies compute-at-load but doesn't say so. If persisted → migration script + backup + schema bump required.

## Reviewer verdicts

- **Reviewer A (arch):** Blockers (T0 def, Gate F threshold) must be resolved before any code. Confidence formula needs abstention renormalization + explicit threshold; tier table needs monotonicity + per-tier verification timestamp.
- **Reviewer B (gov):** Mostly compliant with narrow intent, but governance leaks + one hard contradiction with Current Corrective Execution Order. Not blocking, needs patches before Phase A.
- **Reviewer C (eng):** Conceptually solid but three concrete time-bombs: (1) P5 formula symbolic, (2) §9 guard/override contradiction, (3) golden dataset under-spoken. Fix these before kickoff and 4-5 week estimate becomes defensible.

## Cross-reviewer convergence (action items for v1.2)

**Must fix (blockers):**
1. Define T0 in tier table (P2).
2. Define all P5 sub-scores with concrete formulas + specify Gate F threshold.
3. Resolve §9 guard vs override-path contradiction (options: guard is exempt for gate, or override path goes through separate review mechanism).
4. Freshness decay: extend past 10mo floor; define verification timestamp per tier; fix consensus-lift ceiling.
5. Shadow ≥95% evaluated by external AUDITOR, not gate code.
6. Split Phase A into A1/A2/A3/A4 per R1 batch standard.

**Should fix (governance + architecture):**
7. Cite owner authorization or reclassify plan under Phase 1 governance codification.
8. Add DNA §7 items 5 (redaction) and 9 (error schema) to P7.
9. Fix DNA ref §11 → §7.
10. P8 silver window tied to catalog revert latency, not calendar (trigger-based: "not reverted AND re-audited AND no customer complaint").
11. P9 extend to disambiguate within parent family (PEHA vs Esser) via evidence-required-for-subbrand rule.
12. Per-gate failure reason capture in journal.
13. Stratify hold-out; document baseline; add 93% plateau exit clause.
14. Plan computed-at-load provenance, not in-place mutation.

**Nice to have:**
15. SMTP alternative for digest (Telegram?).
16. Cost ceiling for Stage-1 LLM across 374 SKUs.
17. Config data-structure roadmap at 200+/500+ entries.

## Conclusion

Plan v1.1 is NOT APPROVABLE for implementation.
- **Architecture:** needs numeric calibration + edge-case rules (blockers).
- **Governance:** fixable patches but batch-structure must change.
- **Engineering:** three blockers before Phase A kickoff.

Recommendation: write **v1.2** that addresses items 1-6 at minimum.
Step 1 hotfix (b5dd281) remains the only production-active protection until v1.2.
