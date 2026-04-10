# Research Brief — CSR

**Priority:** high | **Reason:** identity_weak
**Goal:** Close unresolved enrichment gaps for PN CSR (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Основание неглубокое красное Honeywell CSR
- Expected Category: Основание
- Our Price (xlsx): 1353,15

## Questions to Resolve
- Confirm the exact product identity for Honeywell PN=CSR
- What is the full product name and product family for Honeywell CSR?
- Is CSR a current, discontinued, or superseded part number?
- Provide any relevant Russian-language product description for Honeywell CSR

## Current State
```json
{
  "card_status": "REVIEW_REQUIRED",
  "identity_level": "strong",
  "photo_verdict": "REJECT",
  "price_status": "no_price_found",
  "price_source_url": "https://www.honeywellgroup.com/impact-initiatives",
  "category_mismatch": false,
  "overall_confidence": "VERY_LOW",
  "review_reasons": [
    "IDENTITY_WEAK",
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