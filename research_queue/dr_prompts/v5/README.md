# DR Prompt v5 -- A/B Test Variants

Three optimized variants based on lessons learned from batch 1 (v1/v2/v3 comparison).

## Variants

| Variant | File | Strategy | Strength |
|---|---|---|---|
| **A** | `VARIANT_A_exhaustive_detective.md` | 8-step mandatory search protocol | Minimizes "not found" |
| **B** | `VARIANT_B_deep_catalog.md` | Narrative description is primary task | Best description quality |
| **C** | `VARIANT_C_hybrid_optimal.md` | Best of everything combined | Balance of all metrics |

## Key improvements over v4

1. **Russian price sources**: all variants now include vseinstrumenti.ru, lemanapro.ru, etm.ru, bionic.spb.ru
2. **Brand table**: v5-C has a quick-reference table of brands + search sites
3. **Narrative + tables**: v5-B and v5-C produce narrative descriptions that feed description_long_ru
4. **Consistent table format**: all use `| Part Number | Brand |` header for pipeline compatibility
5. **Documents table**: separate table for found PDFs/manuals (feeds download_documents.py)
6. **Micro Switch context**: added correct context for 101411/104011/109411 (sealing boots, NOT LOTO)

## How to test

Use the SAME 8 PNs in all 3 variants:

```
101411, 104011, 109411, 125711, 127411, 129464N/U, 153711, 1000106
```

These cover: PEHA switches, Honeywell HVAC valve, UV flame sensor, ear plugs.

### Evaluation criteria

| Metric | Weight | How to measure |
|---|---|---|
| % products identified | 30% | Rows with Category != "Not found" |
| Description quality | 25% | Manual review: is it useful for a product card? |
| Prices found | 20% | Rows with Price != "Not found" |
| Datasheets found | 10% | Rows with Datasheet PDF URL |
| Photos found | 10% | Rows with Photo URL |
| Training URLs | 5% | Table 2/3 completeness |

## Expected results

- **A**: most found prices, most URLs, shortest descriptions
- **B**: best descriptions (narrative + structured), fewer prices
- **C**: good balance, best for pipeline (all 3 tables + narrative)

My prediction: **C will win overall**, but **B will have better descriptions**.
