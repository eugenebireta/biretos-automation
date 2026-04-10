# Research Brief — 820111

**Priority:** high | **Reason:** category_mismatch
**Goal:** Close unresolved enrichment gaps for PN 820111 (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: D 95.571.02
- Expected Category: Устройство
- Our Price (xlsx): 475,79

## Questions to Resolve
- What is the correct product category for Honeywell 820111 (D 95.571.02)?
- Is the expected category 'Устройство' correct for this product?
- What similar part numbers exist in the same product family?
- Provide any relevant Russian-language product description for Honeywell 820111

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "strong",
  "photo_verdict": "REJECT",
  "price_status": "category_mismatch_only",
  "price_source_url": "https://www.conrad.nl/nl/p/peha-by-honeywell-820111-frame-frame-zuiver-wit-1-stuk-s-2855993.html",
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