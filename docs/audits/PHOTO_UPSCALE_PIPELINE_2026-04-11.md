# Photo Upscale Pipeline v1 — Implementation Report

**Date**: 2026-04-11
**Risk**: LOW (preparation only, no production changes without binary)
**Branch**: feat/rev-r1-catalog

---

## A. Changed Files

| File | Change |
|---|---|
| `scripts/photo_upscale_orchestrator.py` | **NEW** — full upscale pipeline: detect → upscale → enhance → validate → state update |
| `tests/enrichment/test_photo_upscale_orchestrator.py` | **NEW** — 13 unit tests |

---

## B. Engine Detection

**Checked paths:**
- Binary: `tools/realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan.exe`
- Model param: `tools/realesrgan-ncnn-vulkan/models/realesrnet-x4plus.param`
- Model bin: `tools/realesrgan-ncnn-vulkan/models/realesrnet-x4plus.bin`

**Fail-loud message when missing:**
```
======================================================================
FATAL: realesrgan-ncnn-vulkan engine NOT FOUND
======================================================================

  [MISSING] Binary not found: ...tools\realesrgan-ncnn-vulkan\realesrgan-ncnn-vulkan.exe
  [MISSING] Model file not found: ...models\realesrnet-x4plus.param
  [MISSING] Model file not found: ...models\realesrnet-x4plus.bin

Expected layout:
  tools\realesrgan-ncnn-vulkan\
    realesrgan-ncnn-vulkan.exe
    models\
      realesrnet-x4plus.param
      realesrnet-x4plus.bin
```

Exit code 1. No silent fallback. No fake success.

**CLI command template:**
```
realesrgan-ncnn-vulkan.exe -i {input} -o {output} -s 4 -n realesrnet-x4plus -g {gpu_id} -f png
```

- `-s 4` — 4x upscale
- `-n realesrnet-x4plus` — deterministic model (NOT generative realesrgan-x4plus)
- `-g {0|1}` — GPU ID
- `-f png` — lossless intermediate; `photo_enhance_local.py` converts to JPEG

---

## C. Parallel Execution

**Architecture:** `ThreadPoolExecutor(max_workers=N)` where N = number of GPUs.

**GPU assignment:** Deterministic round-robin.
- SKU[0] → GPU 0
- SKU[1] → GPU 1
- SKU[2] → GPU 0
- SKU[3] → GPU 1
- ...

Each GPU gets its own subprocess — `realesrgan-ncnn-vulkan` is single-GPU per invocation.

**Default:** `--gpu 0,1` (2x RTX 3090)

---

## D. State Update Logic

**SKU promoted to `good_quality` ONLY when ALL conditions met:**
1. Raw source file exists
2. Upscale subprocess exits 0
3. Upscaled output file exists and is readable
4. Upscaled dimensions > original dimensions
5. `photo_enhance_local.py` produces 1400x1400 derivative
6. Enhanced file exists on disk

**Outcome codes:**
| Outcome | Meaning | State Change |
|---|---|---|
| `upscale_success_promoted` | Full pipeline passed | Moved to good_quality |
| `upscale_failed` | Binary error or validation fail | Stays in needs_upscale |
| `enhance_failed` | Upscale OK but enhance crashed | Stays in needs_upscale |
| `source_missing` | Raw file not found | Stays in needs_upscale |
| `binary_missing` | Engine not installed | N/A (fail-fast) |
| `dry_run_skipped` | --dry-run mode | No changes |

**On success:** SKU removed from `needs_upscale.json`, added to `good_quality.json` with `upscale_source: realesrgan_x4`. Photo manifest rebuilt.

**On failure:** SKU stays in `needs_upscale.json` unchanged. Error logged in `upscale_report.json`.

---

## E. Test Results

**File:** `tests/enrichment/test_photo_upscale_orchestrator.py`
**Tests:** 13/13 pass

| Class | Tests | Covers |
|---|---|---|
| TestEngineDetection | 3 | Binary/model path checks, expected path structure |
| TestCommandConstruction | 3 | CLI flags, GPU param, deterministic model name |
| TestGpuAssignment | 2 | Round-robin 2 GPUs, single GPU fallback |
| TestFailLoud | 2 | Source missing outcome, dry-run skips execution |
| TestStateUpdate | 3 | Promoted moves to good, failed stays, empty results safe |

---

## F. Owner Next Step

**After installing `realesrgan-ncnn-vulkan`:**

1. Download: `https://github.com/xinntao/Real-ESRGAN/releases`
   - File: `realesrgan-ncnn-vulkan-*-windows.zip`

2. Extract to:
   ```
   D:\BIRETOS\projects\biretos-automation\tools\realesrgan-ncnn-vulkan\
   ```

3. Verify:
   ```
   tools\realesrgan-ncnn-vulkan\realesrgan-ncnn-vulkan.exe -h
   ```

4. Test on 3 SKUs:
   ```
   python scripts/photo_upscale_orchestrator.py --limit 3
   ```

5. Full batch (78 SKUs, 2 GPUs):
   ```
   python scripts/photo_upscale_orchestrator.py
   ```

6. After upscale, rebuild cloud upload manifest:
   ```
   python scripts/build_cloud_upload_manifest.py --dry-run
   ```

7. Re-export InSales CSV with new photo URLs:
   ```
   python scripts/exporter_insales.py
   ```

---

## G. SUPIR Deferred (Line 2)

Per owner engineering critique: SUPIR uses generative prior → risk of "красиво дорисовать не то" for B2B catalog.

**Line 1 (this batch):** `realesrgan-ncnn-vulkan` + `realesrnet-x4plus` — deterministic, safe for mass batch.
**Line 2 (deferred):** SUPIR — premium/manual subset only, visual verification required per SKU.

No SUPIR code written. No generative fallback. No cloud/API upscalers.
