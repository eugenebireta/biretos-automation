# InSales Export Draft v1 — Implementation Report

**Date**: 2026-04-11
**Risk**: LOW (read-only from evidence, no business logic changes)
**Branch**: feat/rev-r1-catalog

---

## A. Changed Files

| File | Change |
|---|---|
| `scripts/exporter_insales.py` | **NEW** — draft InSales CSV exporter from validated evidence |
| `tests/enrichment/test_exporter_insales.py` | **NEW** — 26 unit tests |
| `downloads/export/insales_draft_export.csv` | **NEW** — 351 exportable rows |
| `downloads/export/insales_skipped.csv` | **NEW** — 19 skipped rows with reasons |

---

## B. Source of Truth for Export

| Field | Source | Validation Status |
|---|---|---|
| `Артикул` | `evidence._pn` | Hard requirement — skip if missing |
| `Название` | `evidence.assembled_title` (fallback: `name`) | Validated — deterministic assembly |
| `Бренд` | `evidence.brand` | From evidence, NOT hardcoded |
| `Изображение` | `cloud_upload_manifest.csv → public_url` | From manifest as-is, not reconstructed |
| `Цена` | `evidence.our_price_raw` (RUB preferred), fallback `dr_price` | Validated: blocked/flagged prices excluded |
| `Валюта` | Derived from price source (RUB if our_price, else dr_currency) | — |
| `Категория` | `evidence.product_category` (fallback: `dr_category`) | Advisory — no blocking |
| `Краткое описание` | `evidence.deep_research.specs` | Structured HTML or raw text from DR |
| `Статус экспорта` | Computed from gap analysis | `export_ready_draft` or `export_with_gaps` |
| `Примечание` | Gap flags aggregated | Machine-readable: weak_identity, no_photo, etc. |

**Excluded raw/unvalidated fields:**
- `specs_raw_unvalidated` — blocked by identity gate, never exported
- `dr_price_blocked` — price blocked by identity gate
- `dr_price_flag == WRONG_SOURCE` — known wrong-source prices cleared
- Evidence with `identity_gate.gate_result == "block"` — fully excluded

---

## C. Export Results

| Metric | Count |
|---|---|
| Total evidence | 370 |
| **Exported** | **351** |
| Skipped | 19 |
| With photo URL | 248 |
| With price | 351 (all exported have price) |
| With specs | 218 |
| Export-ready (no gaps) | 77 |
| Export with gaps | 274 |

**Skipped reasons (19 SKUs):**
- `no_usable_price`: 19 — SKUs with no dr_price and our_price_raw = 0

**Gap notes across 274 SKUs with gaps:**

| Gap | Count |
|---|---|
| `draft_only` (card_status) | 212 |
| `no_specs` | 133 |
| `no_photo` | 103 |
| `weak_identity` | 96 |
| `pack_suspect_price` | 13 |

---

## D. Specs Format

**Chosen: HTML** — `<ul><li><b>Key:</b> Value</li>...</ul>` for structured specs, `<p>text</p>` for raw DR text.

Decision rationale: InSales supports HTML in description fields. HTML list is the most practical format for structured key-value specs. Plain text `<p>` fallback used when only DR raw text is available (269 SKUs).

**How unvalidated specs are excluded:**
- If `evidence.specs_status == "blocked_identity_unresolved"`, specs field is set to empty string
- `specs_raw_unvalidated` evidence field is never read by the exporter
- Internal keys (`raw`, `aliases`, `merge_ts`, `confidence`, etc.) are excluded from structured HTML

---

## E. Test Results

**File:** `tests/enrichment/test_exporter_insales.py`
**Tests:** 26/26 pass

| Class | Tests | Covers |
|---|---|---|
| TestPhotoMapping | 4 | URL from manifest, missing photo, URL not reconstructed |
| TestSpecsFormatting | 7 | Structured HTML, raw fallback, blocked excluded, None handling |
| TestMissingFields | 10 | No brand/title/price skipped, blocked price, identity gate, price priority |
| TestMultiVendor | 3 | Brand from evidence, photo URL not vendor-specific |
| TestExportStatus | 3 | Ready draft, gaps flagged, pack_suspect noted |

---

## F. Warnings

**Honeywell-bias in cloud manifest object keys:**
- `cloud_upload_manifest.csv` contains object keys like `products/honeywell/{pn}.jpg`
- The `honeywell` component comes from `evidence.brand` (all current catalog is Honeywell)
- The exporter reads `public_url` from manifest as-is — it does NOT reconstruct URLs
- If a future SKU has brand="Siemens", `build_cloud_upload_manifest.py` will produce `products/siemens/{pn}.jpg`
- **No code fix needed** — the key derivation in `build_cloud_upload_manifest.py` already uses `evidence.brand`, not a hardcoded value

**Other gaps blocking production export:**
1. No real cloud upload yet (all photo URLs are dry-run placeholders)
2. 103 exported SKUs have no photo URL (not in good_quality manifest)
3. 96 exported SKUs have weak identity
4. 133 exported SKUs have no specs
5. Mixed currencies in export (RUB + EUR + USD + GBP + ...) — may need FX normalization

---

## G. Not Implemented (Deferred)

- Real cloud upload
- FX normalization to single currency
- Upscale pipeline for 78 small photos
- InSales API integration (actual import)
- Production-grade specs validation
- Category normalization/mapping to InSales categories

---

## H. Next Safe Batch

**Recommended: Real cloud upload after provider selection**

The draft CSV is complete and ready for visual review. The next blocker is:
1. Owner selects S3-compatible cloud provider
2. Set `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` in `.env`
3. Run `build_cloud_upload_manifest.py` without `--dry-run`
4. Re-run `exporter_insales.py` — real URLs will flow through automatically

Alternative: **Upscale pipeline for 80 small photos** to increase photo coverage from 248/351 (71%) to potentially 328/351 (93%).
