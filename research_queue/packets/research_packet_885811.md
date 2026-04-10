# Research Brief — 885811

**Priority:** high | **Reason:** category_mismatch
**Goal:** Close unresolved enrichment gaps for PN 885811 (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Тепловой извещатель Esser D 95.610.03 KTU
- Expected Category: Извещатель
- Our Price (xlsx): 208,62

## Questions to Resolve
- What is the correct product category for Honeywell 885811 (Тепловой извещатель Esser D 95.610.03 KTU)?
- Is the expected category 'Извещатель' correct for this product?
- What similar part numbers exist in the same product family?
- Provide any relevant Russian-language product description for Honeywell 885811

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "strong",
  "photo_verdict": "REJECT",
  "price_status": "category_mismatch_only",
  "price_source_url": "https://www.conrad.fr/fr/p/peha-by-honeywell-cache-cache-885811-1-pc-s-2855855.html?experience=b2c",
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