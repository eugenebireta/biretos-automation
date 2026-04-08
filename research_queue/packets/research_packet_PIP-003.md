# Research Brief — PIP-003

**Priority:** high | **Reason:** identity_weak
**Goal:** Close unresolved enrichment gaps for PN PIP-003 (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Союзное соединение ASD SOCKET UNION 25MM PK10 PIP-003
- Expected Category: Соединение
- Our Price (xlsx): 3083,85

## Questions to Resolve
- Confirm the exact product identity for Honeywell PN=PIP-003
- What is the full product name and product family for Honeywell PIP-003?
- Is PIP-003 a current, discontinued, or superseded part number?
- Provide any relevant Russian-language product description for Honeywell PIP-003

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "strong",
  "photo_verdict": "KEEP",
  "price_status": "ambiguous_offer",
  "price_source_url": "https://www.orbitadigital.com/en/fire/accessories/extintion/37843-pip-003.html?srsltid=AfmBOoqmwcP71luI2lmEbDgc6PTs3UsSuydQ9eps7JTNSwQIgWrkkJm8",
  "category_mismatch": false,
  "overall_confidence": "VERY_LOW",
  "review_reasons": [
    "IDENTITY_WEAK",
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