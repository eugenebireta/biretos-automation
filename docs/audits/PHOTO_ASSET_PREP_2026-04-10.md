# Photo Asset Prep v1 — Operational Report

**Date**: 2026-04-10
**Risk**: LOW (operational batch, no code logic changes)
**Branch**: feat/rev-r1-catalog

---

## A. Changed Files

| File | Change |
|---|---|
| `scripts/generate_enhance_seed.py` | **NEW** — builds seed JSONL from raw photos + evidence |
| `scripts/photo_quality_triage.py` | **NEW** — classifies raw photos into quality buckets |
| `downloads/scout_cache/photo_enhance_seed.jsonl` | **REGENERATED** — 370 records (was 5) |
| `downloads/scout_cache/photo_enhance_manifest.jsonl` | **REGENERATED** — 370 enhance results |
| `downloads/scout_cache/photo_enhance_ambiguous.json` | **NEW** — 2 ambiguous PNs |
| `downloads/photos_enhanced/*.jpg` | **356 files** — enhanced derivatives |
| `downloads/photo_triage/tiny_quarantine.json` | **NEW** — 25 tiny SKUs |
| `downloads/photo_triage/needs_upscale.json` | **NEW** — 78 small SKUs |
| `downloads/photo_triage/good_quality.json` | **NEW** — 267 good SKUs |
| `downloads/photo_triage/photo_manifest.csv` | **NEW** — unified manifest, 370 rows |

---

## B. Seed Generation

**Seed format** recovered from `photo_enhance_local.py` lines 68-103:
- Required: `part_number`, `source_local_path`
- Optional: `brand`, `product_name`, `source_photo_status`, `source_storage_role`, `source_provider`, `enhancement_profile`, `background_hex`, `canvas_px`, `content_ratio`, `notes`
- Validation: `source_photo_status` must be in `{placeholder, family_evidence, exact_evidence, rejected}`

**Results:**
- 372 raw photo files found in `downloads/photos/`
- 370 unique PNs (2 PNs had .jpg + .webp duplicates: 00020211, 802371)
- 370 seed records written (all PNs with at least one raw photo)
- 2 ambiguous PNs resolved by extension priority (.jpg preferred)
- 0 skipped

**PN-to-evidence mapping:** 370/370 PNs have matching evidence files. 4 garbage evidence files (`---`, `-----`, `PN`, `_`) excluded.

---

## C. Enhance Run

| Metric | Count |
|---|---|
| Seed records | 370 |
| Enhanced OK | 356 |
| Rejected (by photo_verdict.json) | 14 |
| Source missing | 0 |
| Other failures | 0 |
| Preserved existing derivatives | 11 |
| Newly generated | 345 |

**Output directory:** `downloads/photos_enhanced/`
**Output format:** `{pn}__catalog_placeholder_v1__{sha1[:8]}.jpg` — 1400x1400px JPEG, gradient background, soft shadow, autocontrast.

14 SKUs rejected by `photo_verdict.json` (REJECT verdict from prior vision validation). These are NOT enhanced — their raw photos exist but were flagged as unsuitable.

---

## D. Quality Triage

Based on raw photo dimensions (min of width, height):

| Bucket | Count | Criteria | Next Action |
|---|---|---|---|
| **tiny_quarantine** | 25 | min(w,h) < 200px | re-search required |
| **needs_upscale** | 78 | 200 ≤ min(w,h) < 400px | upscale then review |
| **good_quality** | 267 | min(w,h) ≥ 400px | keep enhanced |

**Photo-ready for future cloud:** 260 SKUs (good_quality with enhanced derivative)

Note: 7 good_quality SKUs are not photo-ready because they were REJECT-verdicted (no enhanced derivative generated).

---

## E. Photo Manifest

**File:** `downloads/photo_triage/photo_manifest.csv`

**Fields:**
- `part_number` — SKU identifier
- `raw_photo_path` — absolute path to raw photo
- `raw_width`, `raw_height` — raw photo dimensions
- `min_dimension` — min(width, height)
- `bucket` — tiny_quarantine / needs_upscale / good_quality
- `enhanced_photo_path` — path to enhanced derivative (if exists)
- `enhanced_generated` — true/false
- `photo_ready_for_future_cloud` — true if good_quality AND enhanced exists
- `next_action` — keep_enhanced / upscale_then_review / re_search_required / manual_review

**370 rows total.** 260 photo-ready for future cloud step.

---

## F. Validation

- Dry-run of `generate_enhance_seed.py` confirmed 370 records before write
- `photo_enhance_local.py` ran without errors on all 370 seed records
- Manifest line count verified: 370 data rows
- Triage bucket sums verified: 25 + 78 + 267 = 370
- Enhanced file count verified: 356 files in `downloads/photos_enhanced/`
- No pytest for this operational batch — these are data generation scripts, not logic modules. Validation was manual count verification.

---

## G. Not Implemented (Deferred)

- Cloud upload (any provider)
- Excel/InSales export with photo URLs
- Re-search for tiny_quarantine group
- Real-ESRGAN / upscale pipeline for needs_upscale group
- Photo URL insertion into evidence files
- Modification of existing pipeline code (photo_pipeline.py, photo_enhance_local.py)
- Price/identity logic changes

---

## H. Next Safe Batch

**Recommended: Re-search for tiny_quarantine (25 SKUs)**

These 25 SKUs have raw photos with min dimension < 200px — thumbnails, banners, or icons that are not usable for catalog. The enhance step produces 1400x1400 derivatives from them, but upscaling a 55px-tall banner to 1400px is not useful.

Bounded scope:
1. Run `photo_hunter.py` channels (SerpAPI, Google Images) for 25 tiny PNs only
2. If better photos found, download and replace raw
3. Re-run enhance + triage for affected PNs
4. Update manifest

This is the highest-ROI photo improvement: 25 SKUs, all have known bad sources, local scripts already support the search.
