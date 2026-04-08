# Research Brief — CATALIST

**Priority:** high | **Reason:** no_price_lineage
**Goal:** Close unresolved enrichment gaps for PN CATALIST (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Свитч Honeywell CATALIST
- Expected Category: Свитч
- Our Price (xlsx): 0,00

## Questions to Resolve
- Find a public market price for Honeywell CATALIST from a verifiable distributor
- Is CATALIST RFQ-only or available with published pricing?
- Which authorized distributors carry this part number?
- Provide any relevant Russian-language product description for Honeywell CATALIST

## Current State
```json
{
  "card_status": "REVIEW_REQUIRED",
  "identity_level": "strong",
  "photo_verdict": "KEEP",
  "price_status": "no_price_found",
  "price_source_url": null,
  "category_mismatch": false,
  "overall_confidence": "VERY_LOW",
  "review_reasons": [
    "IDENTITY_WEAK",
    "NO_IMAGE_EVIDENCE",
    "NO_PRICE_EVIDENCE",
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