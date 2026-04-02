# PHOTO_PLACEHOLDER_POLICY_v1

This document defines a narrow mini-contract for temporary product photos used as storefront placeholders.

It does not replace or override:

- `catalog_evidence_policy_v1`
- `family_photo_policy_v1`
- source-role admissibility rules
- PN-first identity rules

Its purpose is to let the pipeline and operators use temporary merchandising photos without silently upgrading them into identity evidence.

## Core Principle

`placeholder != identity proof`

Temporary placeholder photos are a merchandising layer only. They may improve card completeness and time-to-market, but they must not be treated as exact SKU identity evidence.

## Status Model

Every selected photo should be interpreted in one of these statuses:

1. `exact_evidence`
   Exact or sufficiently exact product photo admissible under existing evidence rules.
2. `family_evidence`
   Family-level photo admissible only as family evidence under existing policy.
3. `placeholder`
   Temporary merchandising photo that is acceptable for storefront presentation but not identity proof.
4. `rejected`
   Photo is unusable due to mismatch, severe ambiguity, or unsafe manipulation.

## Allowed Sources By Status

1. `exact_evidence`
   Must satisfy existing image-evidence admissibility rules.
2. `family_evidence`
   Must satisfy existing family-photo restrictions.
3. `placeholder`
   May come from approximate, family-level, catalog-level, or low-precision sources if:
   - the image is not obviously from a different product class;
   - the image is not known false or misleading;
   - the card keeps strict PN-first identity from non-image evidence;
   - the image is flagged as temporary and replaceable.
4. `rejected`
   Includes images with critical class mismatch, obvious wrong brand/product family, unsafe ambiguity, or AI-generated SKU-specific details not grounded in source imagery.

## Publishability Contract

Evidence and merchandising must remain separate.

1. `exact_evidence`
   Can participate in normal evidence-based publish routing under existing policy.
2. `family_evidence`
   Keeps its existing routing behavior; this document does not promote family evidence to exact evidence.
3. `placeholder`
   May be acceptable for storefront use only as a temporary merchandising asset.
   It must not upgrade image evidence status.
   It must not be counted toward `AUTO_PUBLISH` image requirements.
   If a card is otherwise publishable by business decision, placeholder usage must be explicit and traceable.
4. `rejected`
   Must not be published or used as fallback.

## Required Flags

If a photo is used as `placeholder`, the pipeline or operator record should preserve at least:

- `photo_status=placeholder`
- `photo_is_temporary=true`
- `photo_identity_proof=false`
- `replacement_required=true`
- `source_url` or local origin trace

## Local AI Enhancement Rule

Local AI may be used for cleanup, background normalization, denoise, crop, or upscale of a placeholder image only if:

1. the enhancement does not add SKU-specific details that were not visible in the source image;
2. the result is still marked as `placeholder`;
3. the original source image remains traceable;
4. the enhanced asset does not get promoted to `exact_evidence` without separate admissible proof.

## Replacement Rule

When a real product photo becomes available:

1. keep traceability to the replaced placeholder asset;
2. preserve replacement history rather than silently overwriting lineage;
3. allow promotion from `placeholder` to `exact_evidence` only after the new asset satisfies the normal evidence rules;
4. remove temporary flags only after replacement is confirmed.

## Non-Goals

This policy does not:

- create a second truth model for identity;
- relax exact-PN evidence requirements;
- allow AI-generated product invention;
- convert placeholder images into evidence-grade images by wording alone.
