# Research Brief — 158811

**Priority:** high | **Reason:** category_mismatch
**Goal:** Close unresolved enrichment gaps for PN 158811 (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Термостатический вентиль Honeywell D 20.244.02 JR
- Expected Category: Вентиль
- Our Price (xlsx): 490,60

## Questions to Resolve
- What is the correct product category for Honeywell 158811 (Термостатический вентиль Honeywell D 20.244.02 JR)?
- Is the expected category 'Вентиль' correct for this product?
- What similar part numbers exist in the same product family?
- Provide any relevant Russian-language product description for Honeywell 158811

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "weak",
  "photo_verdict": "REJECT",
  "price_status": "category_mismatch_only",
  "price_source_url": "https://www.conrad.sk/sk/p/peha-by-honeywell-kryt-koliska-biela-158811-2855102.html",
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