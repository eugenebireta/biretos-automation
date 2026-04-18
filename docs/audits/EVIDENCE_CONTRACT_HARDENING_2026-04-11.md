# EVIDENCE CONTRACT HARDENING v1 — Audit Report
**Date:** 2026-04-11
**Script:** `scripts/evidence_contract_hardening_v1.py`
**Branch:** feat/rev-r1-catalog
**Risk:** 🟢 LOW — additive only, no field deletions

---

## Goal

Foundation patch: strengthen evidence as single source of truth before
orchestration or recon work. Three new fields added to all 374 evidence bundles.

---

## A. CHANGED FILES

| File | Action |
|------|--------|
| `scripts/evidence_contract_hardening_v1.py` | NEW — migration script |
| `downloads/evidence/evidence_*.json` (374 files) | MODIFIED — new fields added |
| `docs/audits/EVIDENCE_CONTRACT_HARDENING_2026-04-11.md` | NEW — this report |

---

## B. SUBBRAND PATCH

| Outcome | Count |
|---------|-------|
| Filled — high confidence | **94** |
| → from `assembled_title` (PEHA) | 90 |
| → from `name` field (Esser) | 4 |
| Set to `null` — no signal | 280 |
| Skipped — already set | 0 |

**Detection rule:**
1. If `assembled_title` contains "PEHA/Esser/Notifier/Elster/SAIA" → use that subbrand
2. Else if `name` field contains keyword → use that subbrand
3. Else → `null` (not empty string)

**Verified cases:**
- `evidence_185091.json`: `subbrand = "PEHA"` (from assembled_title "PEHA NOVA")
- `evidence_808606.json`: `subbrand = "Esser"` (assembled_title = "Транспондер Honeywell"; name contains "Esserbus")
- `evidence_N05010.json`: `subbrand = null` (plain Honeywell, no subbrand signal)

**Important note:**
280 SKUs have `subbrand: null` intentionally. Coverage report will show 25.4% coverage —
this is correct. The 280 `null` values represent "subbrand not determinable from available
data", not missing data.

---

## C. TRAINING URLS PATCH

| Metric | Value |
|--------|-------|
| Evidence with URLs | **339** (91.6%) |
| Evidence with empty `[]` | 35 (9.4%) |
| Total URLs written | 1294 |
| Avg URLs per filled SKU | 3.8 |

**Sources:**
- `training_data/dr_url_training_2026-04-08.jsonl` (625 lines)
- `training_data/dr_url_training_2026-04-10.jsonl` (825 lines)
- `dr_sources[]` already in evidence (manufacturer/distributor URLs)

Deduplication applied. Empty `[]` written where no URLs found (not `null`).

**Sample (evidence_185091):**
```
training_urls: [
  "https://kudymkar.aelektro.ru/catalog/ramki/...",
  "https://www.etoh24.de/peha-rahmen-1-fach-...",
  ...4 URLs total
]
```

---

## D. PRICE CONTRACT PATCH

| Metric | Value |
|--------|-------|
| Skeletons created | **359** (97.0%) |
| Skipped — no price data at all | 15 |
| Skipped — already existed | 0 |
| `pack_suspect: true` flagged | 13 |

**Schema (`price_contract_v1`):**
```json
{
  "schema_version": "price_contract_v1",
  "dr_value": 343.96,
  "dr_currency": "EUR",
  "dr_source_url": "...",
  "our_price_raw": "13288,04",
  "our_price_parsed": 13288.04,
  "judge_status": "pending",
  "unit_basis": null,
  "source": null,
  "lineage": null,
  "pack_suspect": true
}
```

**Why `price_contract`, not `price`:**
The existing `price {}` object contains 80+ fields from the old Phase A
admissibility pipeline (price_admissibility_schema_version, string_lineage_status,
surface_stability, etc.). Merging into it would cause field name collisions
(`currency` vs `dr_currency`, `offer_unit_basis` vs `unit_basis`). Isolated
as `price_contract` to avoid any risk to the existing structure.

**What is NOT in the skeleton (intentionally):**
- `unit_basis = null` — will be filled by Phase 2 `PRICE_UNIT_JUDGE_FULL_RUN`
- `source = null` — not enough data to assert source reliably yet
- `lineage = null` — Phase 3B will establish lineage

---

## E. COVERAGE DELTA

| Field | Before | After |
|-------|--------|-------|
| `subbrand` (non-null) | 0 / 0.0% | **94 / 25.4%** |
| `training_urls` | 0 / 0.0% | **339 / 91.6%** |
| `price_contract` | 0 / 0.0% | **359 / 97.0%** |
| `price_contract.dr_value` | — | 276 / 74.6% |
| `price_contract.our_price_parsed` | — | 349 / 94.3% |

---

## F. VALIDATION

- Dry run executed first, results matched live run exactly
- Spot-checked 3 evidence files after patch (PEHA SKU, Esser SKU, plain Honeywell)
- `subbrand` field: correct for all 3 tested cases
- `training_urls`: deduped, sorted, http-only URLs
- `price_contract`: `judge_status = "pending"` confirmed, no invented values
- Existing `price {}` object untouched (verified: all 80+ original keys preserved)
- Existing flat fields (`dr_price`, `dr_currency`, `our_price_raw`) preserved
- No test suite exists for evidence migration scripts (operational migration batch)

---

## G. NOT IMPLEMENTED (intentionally deferred)

| Item | Reason |
|------|--------|
| `price_unit_judge` full run | Next batch: `PRICE_UNIT_JUDGE_FULL_RUN` |
| Real `source` / `lineage` in price_contract | Requires Phase 3A/3B pipeline |
| Phase 1–2 recon scripts | Batch 3: `CONTEXT_RECON_V1` |
| `research_merge_gate` stub → real | Blocked on multi-source data |
| Old `price {}` object cleanup | Separate governance batch if needed |
| subbrand for remaining 280 SKUs | Requires Phase 1 identity recon (Haiku) |

---

## H. NEXT SAFE BATCH

**Recommendation: `PRICE_UNIT_JUDGE_FULL_RUN`**

Reasoning:
- `price_contract` skeleton is now in place for 359 SKUs
- `judge_status = "pending"` for all of them
- 13 already flagged as `pack_suspect = true`
- `price_unit_judge.py` already exists and has the logic
- Running it now will populate `unit_basis` and complete the price contract
- This directly unblocks the `CONTEXT_RECON_V1` batch (no point reconning price
  context if we don't know pack vs unit status)

After `PRICE_UNIT_JUDGE_FULL_RUN` → `CONTEXT_RECON_V1` → orchestrator.

---

## Summary

Evidence contract hardened. Three fields added without breaking any existing data.
Foundation is ready for `price_unit_judge` full run.
