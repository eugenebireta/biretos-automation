# Cloud Upload Prep v1 — Implementation Report

**Date**: 2026-04-11
**Risk**: LOW (no business logic changes, no live uploads)
**Branch**: feat/rev-r1-catalog

---

## A. Changed Files

| File | Change |
|---|---|
| `scripts/cloud_uploader.py` | **NEW** — S3-compatible uploader class with dry-run default |
| `scripts/build_cloud_upload_manifest.py` | **NEW** — builds upload manifest for photo-ready subset |
| `tests/enrichment/test_cloud_uploader.py` | **NEW** — 10 unit tests |
| `downloads/photo_triage/cloud_upload_manifest.csv` | **NEW** — 261 rows, dry-run URLs |

---

## B. Ready Subset

**261 photo-ready SKUs** out of 370 total.

Breakdown:
- 268 good_quality total (from triage + rescue)
- 261 have enhanced derivative file confirmed on disk
- 7 good_quality SKUs without enhanced file (REJECT-verdicted by photo_verdict.json)

Excluded from upload:
- 80 needs_upscale — not touched
- 22 unresolved_tiny — not touched

---

## C. Uploader

**Class:** `S3Uploader` in `scripts/cloud_uploader.py`

**Dry-run mode (default):**
- Activates when any of `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` is missing
- Activates when `S3_DRY_RUN=true`
- Returns predictable placeholder URLs: `https://{bucket}.example.com/{object_key}`
- If `S3_PUBLIC_BASE_URL` is set, uses it even in dry-run: `{base}/{object_key}`
- Logs "WOULD UPLOAD" — never touches network

**Live mode:**
- Requires all 4 credentials + bucket
- Uses `boto3.client("s3")` with custom `endpoint_url`
- Supports any S3-compatible provider (AWS, Yandex, MinIO, R2, Selectel)
- `S3_PUBLIC_BASE_URL` overrides URL construction
- Per-file error handling, never fails silently

**Environment variables:**

| Variable | Required | Example |
|---|---|---|
| `S3_ENDPOINT_URL` | Yes | `https://storage.yandexcloud.net` |
| `S3_BUCKET_NAME` | Yes | `biretos-catalog` |
| `S3_ACCESS_KEY` | Yes | access key id |
| `S3_SECRET_KEY` | Yes | secret key |
| `S3_REGION` | No | `ru-central1` (default: us-east-1) |
| `S3_PUBLIC_BASE_URL` | No | `https://cdn.biretos.ru` |
| `S3_DRY_RUN` | No | `true` forces dry-run |

---

## D. Upload Manifest

**File:** `downloads/photo_triage/cloud_upload_manifest.csv`

**Fields:**
- `part_number` — SKU identifier
- `brand` — from evidence (all Honeywell in current catalog)
- `local_path` — absolute path to enhanced derivative
- `object_key` — deterministic S3 key: `products/{brand}/{pn}.jpg`
- `upload_mode` — `dry_run` | `uploaded` | `error`
- `upload_status` — `ok` | `error`
- `public_url` — placeholder or real URL
- `size_kb` — file size
- `error` — error message if any

**Stats:**
- 261 rows, all `dry_run`, all `ok`
- Total size: 42.7 MB
- 0 errors

---

## E. Validation

- **pytest:** 10/10 tests pass (`test_cloud_uploader.py`)
  - Dry-run default, forced dry-run, placeholder URLs, public base URL override
  - Live URL construction, missing file error, batch mixed results
- **Dry-run execution:** 261 SKUs processed, 0 errors
- **Subset count:** 261 matches expected (268 good - 7 REJECT-verdicted = 261)
- **Object keys:** deterministic, clean, stable: `products/honeywell/{pn}.jpg`
- **No tiny/unresolved included:** verified by subset filter

---

## F. Not Implemented (Deferred)

- Real cloud upload (no provider chosen, no credentials set)
- InSales export with public URLs
- needs_upscale processing (78 SKUs)
- unresolved_tiny re-search (22 SKUs)
- Upscale pipeline (Real-ESRGAN)

---

## G. Next Safe Batch

**Recommended: Draft InSales export with photo URL column**

Now that we have:
- 261 upload-ready assets with deterministic object keys
- Cloud uploader that will produce real URLs once credentials are set
- Upload manifest linking SKU → object_key → public_url

The next logical step is building the **draft InSales CSV** that includes the photo URL column (using dry-run URLs as placeholder, swappable to real URLs after cloud upload).

This would produce a complete export-ready artifact: all catalog fields + photo URLs + price + category — the final deliverable for InSales import.
