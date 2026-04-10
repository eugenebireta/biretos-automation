# Research Brief — 830811

**Priority:** high | **Reason:** category_mismatch
**Goal:** Close unresolved enrichment gaps for PN 830811 (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Детектор пламени Esser D 95.540.03 GLK
- Expected Category: Детектор
- Our Price (xlsx): 448,70

## Questions to Resolve
- What is the correct product category for Honeywell 830811 (Детектор пламени Esser D 95.540.03 GLK)?
- Is the expected category 'Детектор' correct for this product?
- What similar part numbers exist in the same product family?
- Provide any relevant Russian-language product description for Honeywell 830811

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "strong",
  "photo_verdict": "REJECT",
  "price_status": "category_mismatch_only",
  "price_source_url": "https://www.conrad.sk/sk/p/peha-by-honeywell-kryt-koliska-biela-830811-2855256.html",
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