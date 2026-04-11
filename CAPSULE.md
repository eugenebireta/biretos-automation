# CAPSULE — Evidence Foundation Hardening (2026-04-11)

## Batch Summary

Three sequential batches on `feat/rev-r1-catalog`:

### 1. EVIDENCE CONTRACT HARDENING v1
- `scripts/evidence_contract_hardening_v1.py` (NEW)
- Adds 3 new fields to 374 evidence files: `subbrand`, `training_urls`, `price_contract`
- Results: 94 subbrands detected (90 PEHA + 4 Esser), 339 training_urls, 359 price_contract skeletons
- Audit: LOW, additive only

### 2. PRICE_UNIT_JUDGE — FULL RUN + LLM PASS
- `scripts/price_unit_judge_full_run.py` (NEW) — deterministic pass, 42 triggered
- `scripts/price_unit_judge.py` (FIXED) — 2 bugs: EU currencies + x-pattern regex
- `scripts/price_unit_judge_llm_pass.py` (NEW) — domain knowledge judge for 42 unknowns
- Results: 265 per_unit, 10 per_pack (PEHA NOVA frames + earplug packs), 0 unknown remaining
- Audit doc: `docs/audits/EVIDENCE_CONTRACT_HARDENING_2026-04-11.md`

### 3. EVIDENCE NORMALIZATION LAYER
- `scripts/evidence_normalize.py` (NEW)
- Unifies 3 pipelines into canonical `normalized{}` block per evidence file
- Fixes: 27 SKUs with price ONLY in `price.price_per_unit` (invisible to all exporters)
- Results: price=302/374 (80.7%), desc=370/374 (98.9%), photo=310/374 (82.9%)
- Auditor pre-validation: 2 design rejections → code approved AUTO_PASS (run_0a311a28da35)
- All 374 files updated, 0 errors, 20 deterministic tests pass

## Coverage After Batch

| Field | Before | After |
|-------|--------|-------|
| subbrand (non-null) | 0% | 25.4% (94/374) |
| price_contract | 0% | 97.0% (359/374) |
| price_contract.unit_basis resolved | 0% | 100% of priced SKUs |
| normalized.best_price | 0% | 80.7% (302/374) |
| normalized.best_description | 0% | 98.9% (370/374) |
| normalized.best_photo_url | 0% | 82.9% (310/374) |

## Next Batch Recommendation

`CONTEXT_RECON_V1` — Haiku recon for identity/category gaps (67 REVIEW_BLOCKED SKUs).
Normalization layer now provides `normalized.best_price` to unblock accurate export stats.
