# Tiny Photo Rescue v1 — Operational Report

**Date**: 2026-04-11
**Risk**: LOW (operational batch, no business logic changes)
**Branch**: feat/rev-r1-catalog

---

## A. Changed Files

| File | Change |
|---|---|
| `scripts/rescue_tiny_photos.py` | **NEW** — bounded rescue orchestrator |
| `downloads/photos_quarantine/raw/` | **NEW DIR** — 25 quarantined tiny raw files |
| `downloads/photos_quarantine/enhanced/` | **NEW DIR** — 21 quarantined tiny enhanced files |
| `downloads/photo_triage/rescue_quarantine_map.json` | **NEW** — full audit trail with old/quarantine paths |
| `downloads/scout_cache/rescue_tiny_seed.jsonl` | **NEW** — 3-record seed for rescued SKUs |
| `downloads/scout_cache/rescue_tiny_manifest.jsonl` | **NEW** — enhance manifest for 3 rescued |
| `downloads/photo_triage/rescue_tiny_delta.csv` | **NEW** — delta manifest 25 rows with rescue outcomes |
| `downloads/photo_triage/rescue_tiny_report.json` | **NEW** — full rescue JSON report |
| `downloads/photos/885811.jpg` | **REPLACED** — 2448x3264 (was 702x141) |
| `downloads/photos/N05010.jpg` | **REPLACED** — 253x464 (was 196x274) |
| `downloads/photos/T7560B1024.jpg` | **REPLACED** — 300x300 (was 138x162) |
| `downloads/photos_enhanced/885811__*.jpg` | **NEW** — enhanced from rescued raw |
| `downloads/photos_enhanced/N05010__*.jpg` | **NEW** — enhanced from rescued raw |
| `downloads/photos_enhanced/T7560B1024__*.jpg` | **NEW** — enhanced from rescued raw |

---

## B. Quarantine

| Metric | Count |
|---|---|
| Raw files quarantined | 25 |
| Enhanced files quarantined | 21 |
| Audit trail file | `rescue_quarantine_map.json` |

All quarantined files preserved at:
- Raw: `downloads/photos_quarantine/raw/{pn}.jpg`
- Enhanced: `downloads/photos_quarantine/enhanced/{pn}__*.jpg`

Quarantine map records per SKU: `old_raw_path`, `old_enhanced_path`, `quarantine_raw_path`, `quarantine_enhanced_path`, `old_raw_dims`, `old_min_dimension`, `reason=tiny_rescue_replaced_candidate`, `superseded=True`.

For the 22 unresolved SKUs: old tiny raw files were **copied back** to `downloads/photos/` from quarantine (quarantine copy retained as audit). Pipeline remains intact with 370 photos.

---

## C. Re-Search Results

**Channels attempted:** 1 (OG-scrape), 2 (PDF), 3 (Family), 6 (Gemini Imagen)

| Outcome | Count | Notes |
|---|---|---|
| `rescued_good` | **1** | 885811: 2448x3264 from surpluscityliquidators.com |
| `rescued_but_small` | **2** | N05010: 253x464, T7560B1024: 300x300 |
| `no_better_candidate` | **22** | Channel 6 hit spending cap (429 RESOURCE_EXHAUSTED) |
| `search_failed` | **0** | — |

**Channel yield:**
- Channel 1 (OG-scrape): **3 finds**, 2 useful (885811=good, N05010=small, T7560B1024=small), 3 found but still tiny (FX808324=240px, FX808332=240px, N3424=172px)
- Channel 2 (PDF): 0 — no PDF source URLs in evidence for tiny SKUs
- Channel 3 (Family): 0 — no `dr_series` set for tiny SKUs
- Channel 6 (Gemini Imagen): 0 — API spending cap exhausted (`429 RESOURCE_EXHAUSTED`)

**Root cause of 22 unresolved:** Gemini Imagen API monthly spending cap hit from start. Only channel that had any chance of generating images was unavailable. OG-scrape had source URLs for 13/25 SKUs but most returned small images.

---

## D. Enhance Results

| Metric | Count |
|---|---|
| Seed records (rescued) | 3 |
| Enhanced success | 3 |
| Enhanced failed | 0 |

All 3 rescued SKUs enhanced to 1400x1400 JPEG via `photo_enhance_local.py catalog_placeholder_v1` profile.

---

## E. Manifest Update

**Delta manifest:** `downloads/photo_triage/rescue_tiny_delta.csv` — 25 rows.

Fields added vs base manifest:
- `rescue_outcome`: rescued_good / rescued_but_small / no_better_candidate
- `previous_status`: superseded_tiny

**Updated bucket counts (after rescue):**
- From tiny_quarantine: 885811 → good_quality
- From tiny_quarantine: N05010, T7560B1024 → needs_upscale
- Remaining unresolved: 22 still in tiny_quarantine category

Superseded → selected transition: visible in `rescue_quarantine_map.json` (old paths) + `rescue_tiny_delta.csv` (new paths and outcomes).

---

## F. Validation

- Dry-run confirmed 25 SKUs loaded before live run
- Quarantine move: verified 25 files moved by log output
- Raw file restoration: 22/22 unresolved restored, `photos/` count = 370 ✓
- Enhance: 3 success, 0 fail, confirmed by manifest
- No pytest — operational data batch

---

## G. Not Implemented (Deferred)

- needs_upscale batch (78 SKUs + 2 newly rescued)
- Cloud upload
- Excel export
- SerpAPI channel (no key)
- DALL-E channel (no key)
- Gemini Imagen retry (spending cap — needs owner to manage API budget at ai.studio)

---

## H. Next Safe Batch

**Option A — Upscale pipeline for 80 small SKUs** (78 needs_upscale + 2 rescued_but_small)
- Real-ESRGAN or similar upscale for min_dim 200-399 photos
- Bounded: only these 80 SKUs, only local processing
- Risk: LOW, no cloud, no export

**Option B — Cloud upload prep** (260 photo-ready good_quality SKUs)
- Build upload manifest from existing good_quality enhanced derivatives
- No re-search, no upscale — just asset transfer
- Risk: LOW (read + write, no business logic)

**Recommended: Option B (cloud upload prep)**
Good-quality assets already exist (260 SKUs), enhanced to 1400x1400. Cloud upload is the next logical step before upscale pipeline (which is more complex and needs external tool setup).
