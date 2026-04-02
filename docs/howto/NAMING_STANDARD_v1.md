# Naming Standard v1

This document defines the short working title standard for product-card naming and the practical batch workflow for applying it across a SKU slice.

## Goal

Produce a self-contained RU storefront title that identifies the product without forcing the operator or buyer to decode the part number alone.

## Core Rules

1. Start with the exact product type in Russian.
2. Keep the brand and preserve important commercial signals such as family, series, subbrand, or model.
3. Add only confirmed differentiating attributes that materially help identify the SKU.
4. Keep the part number at the end of the title; PN supplements the title and never replaces product wording.
5. Do not leak unconfirmed attributes, color, finish, or guessed subtype into the final title.
6. If the exact product type, family/model signal, or critical differentiator cannot be confirmed, route the card to review instead of publishing a weak title.

## Title Pattern

`[product type RU] [brand] [family/series/model], [confirmed differentiators], [part number]`

## Good Outcomes

- Self-contained title: the buyer can understand what the item is without decoding PN only.
- No generic fallback when a more precise product type is known.
- No loss of a confirmed family or model signal.
- No speculative attributes.

## Review Triggers

Route to review when any of the following is true:

1. Exact product type is still generic when a more specific type probably exists.
2. Family, series, model, or subbrand is known from trusted evidence but missing from the final title.
3. The title depends on a guessed translation or weak source wording.
4. The SKU has conflicting attributes across sources.
5. The title contains unconfirmed color, size, interface, packaging, or configuration details.

## Batch Workflow

1. Build the work table with `brand`, `part_number`, `raw_title`, and any supplier `source_name`.
2. Resolve exact product type and family/model signal from trusted exact-PN evidence.
3. Extract only confirmed differentiators that help disambiguate the SKU.
4. Assemble the new title with the standard pattern.
5. Run validation checks before acceptance.
6. Send any failed card to `review_required` with the failed rule recorded.
7. Export a diff table: `old_title | new_title | source | failed_rules_or_reason`.

## Validation Checks

Accept the title only if all checks pass:

1. `has_ru_product_type`
2. `has_brand`
3. `has_part_number_suffix`
4. `preserves_family_or_model_signal_when_confirmed`
5. `uses_only_confirmed_differentiators`
6. `not_generic_when_specific_type_is_known`

## Operator Checklist

For a quick manual pass, the operator should ask:

1. Can I understand what the product is without decoding PN only?
2. Is the first noun the exact RU product type?
3. Did the title keep the brand and any confirmed family/model/subbrand?
4. Are the added characteristics really useful for disambiguation?
5. Is every added characteristic confirmed by a trusted exact-PN source?
6. Is the PN still present at the end?
7. If I am unsure about any of the above, did I route the card to review?
