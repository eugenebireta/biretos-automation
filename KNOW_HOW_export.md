# Know-How: Export / InSales Pipeline

<!-- Sub-file of KNOW_HOW.md. Same format: YYYY-MM-DD | #тег | scope: Суть -->
<!-- Records here are DUPLICATED from KNOW_HOW.md (not moved) per CLAUDE.md rule. -->

## Export pipeline

2026-04-10 | #rule | export_ready.py — точка входа для экспортного слоя. Читает evidence напрямую, не использует stale card_status. Артефакты: downloads/export/export_ready_view.json + draft_insales_export.xlsx + photo_manifest.csv + missing_data_queue.csv.
2026-04-12 | #bug | export_ready.py: price_market gate не включал 'phase3a' — 43 SKУ падали в BLOCKED_NO_PRICE. Fix: добавить 'phase3a'.
2026-04-12 | #bug | exporter_insales.py: price gate читал только dr_price/our_price_raw, игнорировал normalized.best_price. Fix: check normalized.best_price first.
2026-04-09 | #bug | export_pipeline: 5 DR fields (price, currency, title_ru, description_ru, image_url) не экспортировались. Fix: added all 5 columns.

## Data quirks

2026-04-10 | #data_quirk | export-ready audit 2026-04-10 (370 SKU): EXPORT_READY=224 (60%), DRAFT_EXPORT=68 (18%), REVIEW_BLOCKED=67 (18%), BLOCKED_NO_PRICE=11 (3%).
2026-04-10 | #data_quirk | review_reasons стухли для 357 SKU: NO_IMAGE_EVIDENCE — артефакт старых runs photo_pipeline (до DR). Реально у 370/370 SKU есть фото. CRITICAL_MISMATCH (66 SKU) — по-прежнему актуален.
2026-04-12 | #data_quirk | Phase 3A+3B final metrics (370 SKU): price=98% (366/370). EXPORT_READY=278 (75%), DRAFT=21, REVIEW_BLOCKED=67, BLOCKED_NO_PRICE=4. Description=100%. Photo: url=308, local=62, missing=0.
2026-04-11 | #data_quirk | evidence 3-pipeline fragmentation (374 SKU): 27 SKU имели цену ТОЛЬКО в price.price_per_unit, невидимую для экспортёров. Fix: normalized{} layer.
2026-04-11 | #data_quirk | photo.source формат в evidence: "cached"=URL в dr_image_url; "engine:https://..."=split; bare URL=as-is. KEEP/ACCEPT=проверенное фото.

## Photo pipeline

2026-04-14 | #platform | honeywell-photos: security.honeywell.de returns 403 on ALL direct image requests. Workaround: distributor sites or evidence DR URLs.
2026-04-14 | #rule | photo-sources: Evidence DR URLs > manufacturer sites > trusted distributors. NEVER random Google Images or eBay for numeric PNs.
2026-04-14 | #data_quirk | dr-photo-accuracy: DR best_photo_url wrong for 033588.17 (ABB bearing instead of PEHA box). Cross-validation needed for numeric PNs.
2026-04-15 | #data_quirk | photo-pipeline-results: 338 PNs collected, 81 CLIP outliers quarantined, 199 QC PASS, 313 deployed to VPS.
2026-04-15 | #rule | photo-audit-identity: Haiku photo audit MUST include product identity in prompt. Without it passes wrong products as GOOD.
