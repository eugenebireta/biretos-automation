# Kalashnikov Import Report (2025-12-17 13:45 UTC)

## Pre-flight cleanup
- `python src/reset_shopware_for_test.py --apply` removed 10 products, 5 unused manufacturers and left the canonical Marketplace Price rule intact (`_reports/reset_before_test.md`).
- Categories, taxes and sales-channel configs were left untouched; Shopware started empty before import.

## Global normalization
- `python src/normalize_entities.py --apply --only all` confirmed 0 duplicate manufacturers/rules remain (canon_map.json updated on demand during import).

## Import batch (10 SKUs)
- `python src/pipeline_import.py --batch 10 --apply` ran with the new idempotent media/visibility cleanup.
- Every step `skeleton -> manufacturer -> categories -> media -> prices -> visibilities -> verify` finished with `SUCCESS` (`_reports/pipeline_batch_10_summary.md`).
- Invariants enforced: canonical manufacturer + Marketplace Price rule via `CanonRegistry`, full category chains, media only when present in snapshot, `product-price` wiped before recreate, marketplace rule `39a5ceca6c11481fa511235a196fe5b7`, `manufacturerNumber` stored verbatim.

### SKU health matrix
| SKU | Manufacturer | Snapshot->Shopware media | Category depth | Leaf chain |
| --- | --- | --- | --- | --- |
| 00-1427-1 | Skip manufacturer: brand missing in snapshot | 2->2 | 2 | e56b3914e6544f5a9f4fe29adb759c2e > fc027b71175946199e578a53ae5ce8da |
| 1199082497 | manufacturerId=1083834196b244aba41f5f907ff4fe32 | 0->0 | 2 | 0f1349cbb19741a6ad4732f0949f9052 > fc027b71175946199e578a53ae5ce8da |
| 123654593 | manufacturerId=37a6b3aa2f7c43c5846ec6d9ae4d6297 | 0->0 | 2 | 0f1349cbb19741a6ad4732f0949f9052 > fc027b71175946199e578a53ae5ce8da |
| 1284133121 | manufacturerId=8c9e7968efb145d180d4fbe0d990049d | 5->5 | 2 | 0f1349cbb19741a6ad4732f0949f9052 > fc027b71175946199e578a53ae5ce8da |
| 1554153361 | manufacturerId=ef5548676a3e4cf0b37096bafe9ba69f | 1->1 | 2 | e56b3914e6544f5a9f4fe29adb759c2e > fc027b71175946199e578a53ae5ce8da |
| 1556618297 | manufacturerId=ef5548676a3e4cf0b37096bafe9ba69f | 2->2 | 2 | e56b3914e6544f5a9f4fe29adb759c2e > fc027b71175946199e578a53ae5ce8da |
| 1558861041 | manufacturerId=ef5548676a3e4cf0b37096bafe9ba69f | 1->1 | 2 | e56b3914e6544f5a9f4fe29adb759c2e > fc027b71175946199e578a53ae5ce8da |
| 1560044913 | manufacturerId=ef5548676a3e4cf0b37096bafe9ba69f | 1->1 | 2 | e56b3914e6544f5a9f4fe29adb759c2e > fc027b71175946199e578a53ae5ce8da |
| 1577334969 | manufacturerId=8c9e7968efb145d180d4fbe0d990049d | 4->4 | 2 | 0f1349cbb19741a6ad4732f0949f9052 > fc027b71175946199e578a53ae5ce8da |
| 1637861577 | manufacturerId=12a970c853114deaa19fe7f44ac5fbf4 | 6->6 | 2 | e56b3914e6544f5a9f4fe29adb759c2e > fc027b71175946199e578a53ae5ce8da |

_Source data: `_reports/pipeline_batch_10_details.json`, `_reports/media_check.json`, `_reports/category_check.json`._

## Verification / QA
- `verify_product_state.py` executed for all 10 SKUs -> every run returned 0 (see `_reports/verify_run_last.json`).
- Category API checks confirm depth >=2 with leaf present for every product, and media counts exactly match the snapshot counts (no ghost uploads).
- API audits confirm 5 unique manufacturers and exactly one Marketplace Price rule exist (`delete_all_product_media` / `delete_all_product_visibilities` keep reruns idempotent).

## Final verdict
**GO** — Shopware now contains a clean deterministic import of the first 10 NDJSON products and all strict/relaxed checks pass end-to-end (reset -> normalize -> import -> verify). No duplicate manufacturers/rules, one marketplace price per SKU, and data matches the local snapshot.
