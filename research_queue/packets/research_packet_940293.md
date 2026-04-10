# Research Brief — 940293

**Priority:** high | **Reason:** category_mismatch
**Goal:** Close unresolved enrichment gaps for PN 940293 (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Тепловой извещатель Esser D 20.607.022 FTR
- Expected Category: Извещатель
- Our Price (xlsx): 1295,53

## Questions to Resolve
- What is the correct product category for Honeywell 940293 (Тепловой извещатель Esser D 20.607.022 FTR)?
- Is the expected category 'Извещатель' correct for this product?
- What similar part numbers exist in the same product family?
- Provide any relevant Russian-language product description for Honeywell 940293

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "strong",
  "photo_verdict": "REJECT",
  "price_status": "category_mismatch_only",
  "price_source_url": "http://teslatorg.ru/elektroustanovochnye-izdeliya/rozetki-i-vyklyuchateli/ustroystva-upravleniya-klimatom-zhalyuzi-zvukom/nakladka-na-termostat-peha-by-honeywell-nova-belyy-940293",
  "category_mismatch": true,
  "overall_confidence": "VERY_LOW",
  "review_reasons": [
    "IDENTITY_WEAK",
    "CRITICAL_MISMATCH",
    "NO_IMAGE_EVIDENCE",
    "TERMINAL_WEAK_NO_PRICE_LINEAGE",
    "NO_PDF_EVIDENCE"
  ]
}
```

## Constraints
- Use public web evidence only
- Do not use xlsx price as market price
- Do not invent specs if not found
- If uncertain, return ambiguity explicitly
- Prefer exact PN evidence over family-level evidence
- Cite specific URLs for any claim