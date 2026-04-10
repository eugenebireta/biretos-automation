# Research Brief — 171111

**Priority:** high | **Reason:** category_mismatch
**Goal:** Close unresolved enrichment gaps for PN 171111 (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Термостатический вентиль Honeywell D 20.571.02 T
- Expected Category: Вентиль
- Our Price (xlsx): 598,00

## Questions to Resolve
- What is the correct product category for Honeywell 171111 (Термостатический вентиль Honeywell D 20.571.02 T)?
- Is the expected category 'Вентиль' correct for this product?
- What similar part numbers exist in the same product family?
- Provide any relevant Russian-language product description for Honeywell 171111

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "strong",
  "photo_verdict": "REJECT",
  "price_status": "category_mismatch_only",
  "price_source_url": "https://cdon.se/produkt/peha-by-honeywell-171111-ram-ram-ram-klar-vit-63ddf5282dae5f3f/",
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