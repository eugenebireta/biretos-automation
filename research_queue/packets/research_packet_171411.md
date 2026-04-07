# Research Brief — 171411

**Priority:** high | **Reason:** category_mismatch
**Goal:** Close unresolved enrichment gaps for PN 171411 (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Термостатический вентиль Honeywell D 20.574.02 T
- Expected Category: Вентиль
- Our Price (xlsx): 2018,40

## Questions to Resolve
- What is the correct product category for Honeywell 171411 (Термостатический вентиль Honeywell D 20.574.02 T)?
- Is the expected category 'Вентиль' correct for this product?
- What similar part numbers exist in the same product family?
- Provide any relevant Russian-language product description for Honeywell 171411

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "weak",
  "photo_verdict": "REJECT",
  "price_status": "category_mismatch_only",
  "price_source_url": "https://liveinlight.ru/ramki/ramki-4-posta/ramka-4-posta-peha-by-honeywell-aura-belyy",
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