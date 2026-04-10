# Research Brief — SMB500

**Priority:** high | **Reason:** identity_weak
**Goal:** Close unresolved enrichment gaps for PN SMB500 (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Монтажный корпус Honeywell SMB500
- Expected Category: Монтажный корпус
- Our Price (xlsx): 218,25

## Questions to Resolve
- Confirm the exact product identity for Honeywell PN=SMB500
- What is the full product name and product family for Honeywell SMB500?
- Is SMB500 a current, discontinued, or superseded part number?
- Provide any relevant Russian-language product description for Honeywell SMB500

## Current State
```json
{
  "card_status": "REVIEW_REQUIRED",
  "identity_level": "strong",
  "photo_verdict": "KEEP",
  "price_status": "no_price_found",
  "price_source_url": "https://www.alldataresource.com/Honeywell-Silent-Knight-SMB500-WH-White-Backbox_p_499961.html?srsltid=AfmBOoqe_zasmyno4NAye_9wcEg658sj_1p0HIb8UqqSwNGb4ARIzWmv",
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