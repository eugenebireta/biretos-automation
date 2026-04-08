# Research Brief — IP

**Priority:** high | **Reason:** photo_mismatch
**Goal:** Close unresolved enrichment gaps for PN IP (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: IP-телефон
- Expected Category: Телефон
- Our Price (xlsx): 0,00

## Questions to Resolve
- Find the official product image for Honeywell IP
- Is there a manufacturer page with product images?
- What does Honeywell IP physically look like?
- Provide any relevant Russian-language product description for Honeywell IP

## Current State
```json
{
  "card_status": "REVIEW_REQUIRED",
  "identity_level": "strong",
  "photo_verdict": "REJECT",
  "price_status": "no_price_found",
  "price_source_url": "https://www.alarmgrid.com/products/honeywell-home-prowifi",
  "category_mismatch": false,
  "overall_confidence": "VERY_LOW",
  "review_reasons": [
    "NO_IMAGE_EVIDENCE",
    "ADMISSIBLE_SOURCE_NO_PRICE_EXACT_LINEAGE",
    "PDF_NOT_EXACT_CONFIRMED"
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