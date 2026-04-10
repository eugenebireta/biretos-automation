# Research Brief — 887111

**Priority:** high | **Reason:** category_mismatch
**Goal:** Close unresolved enrichment gaps for PN 887111 (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Тепловой извещатель Esser D 95.244.02 T
- Expected Category: Извещатель
- Our Price (xlsx): 490,50

## Questions to Resolve
- What is the correct product category for Honeywell 887111 (Тепловой извещатель Esser D 95.244.02 T)?
- Is the expected category 'Извещатель' correct for this product?
- What similar part numbers exist in the same product family?
- Provide any relevant Russian-language product description for Honeywell 887111

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "strong",
  "photo_verdict": "REJECT",
  "price_status": "category_mismatch_only",
  "price_source_url": "https://www.conrad.nl/nl/p/peha-by-honeywell-887111-wipschakelaar-afdekking-wit-1-stuk-s-2855106.html",
  "category_mismatch": true,
  "overall_confidence": "VERY_LOW",
  "review_reasons": [
    "IDENTITY_WEAK",
    "CRITICAL_MISMATCH",
    "NO_IMAGE_EVIDENCE",
    "ADMISSIBLE_SOURCE_NO_PRICE_EXACT_LINEAGE",
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