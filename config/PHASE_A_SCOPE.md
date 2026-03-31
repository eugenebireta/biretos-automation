# Phase A Scope - Enrichment Pipeline v2

Date: 2026-03-26

## In Scope

1. Patch 3 Lite: source backbone.
2. Patch 1 Lite: identity safety.
3. Deterministic status and policy layer.
4. Sanity batch gate.
5. Approved full run subset after gate.

## Phase A Deliverables

1. `catalog_evidence_policy_v1`
2. `family_photo_policy_v1`
3. `source_role_field_matrix_v1`
4. `catalog_enum_contract_v1`
5. replayable review-reason schema
6. candidate sidecar schema and export contract
7. `R1_START_GATE_v1`

## Hard Invariants

1. CSV / Excel / supplier feed are raw input and search seed only.
2. Raw input is never identity proof.
3. Search expansion is never identity proof.
4. Phase A is deterministic for publish/review decisions.
5. Phase A does not open live publish side effects.
6. Tier-1 frozen files and pinned APIs stay untouched.
7. Candidate sidecar uses `pn_primary` as the canonical identity-anchor key; `pn` is legacy alias only.

## Out of Scope

1. AI Judge or any LLM publish arbitration.
2. Patch 2 full.
3. eBay, weak marketplaces, Alibaba, AliExpress, Perplexity.
4. GPU, OCR, VLM, multimodal arbitration.
5. full code-lineage graph or heavy identity graph.

## Run Scope Clarification

1. `370 SKU` is the approved Phase A full-run subset.
2. `500 SKU` remains the broader R1 target in the roadmap/import scope.
3. Phase A does not silently redefine the 500 target to 370.

## R1 Start Gate

Full run stays blocked until all are true:

1. sanity batch passed
2. CI green
3. branch protection OK
4. Iron Fence stable
5. policy frozen for run
6. replayable review reasons working

See [R1_START_GATE_v1.md](/d:/BIRETOS/projects/biretos-automation/docs/howto/R1_START_GATE_v1.md).
