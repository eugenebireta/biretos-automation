# Research Brief — EVCS-HSB

**Priority:** high | **Reason:** category_mismatch
**Goal:** Close unresolved enrichment gaps for PN EVCS-HSB (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Пульт вызова Honeywell EVCS-HSB
- Expected Category: Пульт
- Our Price (xlsx): 14960,00

## Questions to Resolve
- What is the correct product category for Honeywell EVCS-HSB (Пульт вызова Honeywell EVCS-HSB)?
- Is the expected category 'Пульт' correct for this product?
- What similar part numbers exist in the same product family?
- Provide any relevant Russian-language product description for Honeywell EVCS-HSB

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "strong",
  "photo_verdict": "KEEP",
  "price_status": "category_mismatch_only",
  "price_source_url": "https://www.thesafetycentre.co.uk/honeywell-evcs-hsb-disabled-refuge-intercom-outstation-type-b-red?srsltid=AfmBOopjWQWcZjA5LN9kwBYFx5djFOUF_qj49doaEeOmkynkFblP6nI0",
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