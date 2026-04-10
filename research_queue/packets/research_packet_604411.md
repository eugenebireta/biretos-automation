# Research Brief — 604411

**Priority:** high | **Reason:** category_mismatch
**Goal:** Close unresolved enrichment gaps for PN 604411 (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Датчик D 701 DO F
- Expected Category: Датчик
- Our Price (xlsx): 238,33

## Questions to Resolve
- What is the correct product category for Honeywell 604411 (Датчик D 701 DO F)?
- Is the expected category 'Датчик' correct for this product?
- What similar part numbers exist in the same product family?
- Provide any relevant Russian-language product description for Honeywell 604411

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "strong",
  "photo_verdict": "REJECT",
  "price_status": "category_mismatch_only",
  "price_source_url": "https://www.conrad.fr/fr/p/peha-by-honeywell-604411-boitier-d-interrupteur-1-pc-s-2854740.html",
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