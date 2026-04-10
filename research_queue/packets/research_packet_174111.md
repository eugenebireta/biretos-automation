# Research Brief — 174111

**Priority:** high | **Reason:** category_mismatch
**Goal:** Close unresolved enrichment gaps for PN 174111 (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Термостатический вентиль Honeywell D 20.571.64 T
- Expected Category: Вентиль
- Our Price (xlsx): 561,58

## Questions to Resolve
- What is the correct product category for Honeywell 174111 (Термостатический вентиль Honeywell D 20.571.64 T)?
- Is the expected category 'Вентиль' correct for this product?
- What similar part numbers exist in the same product family?
- Provide any relevant Russian-language product description for Honeywell 174111

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "strong",
  "photo_verdict": "REJECT",
  "price_status": "category_mismatch_only",
  "price_source_url": "https://www.conrad.fr/fr/p/peha-by-honeywell-cadre-cadre-anthracite-174111-1-pc-s-2855967.html",
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