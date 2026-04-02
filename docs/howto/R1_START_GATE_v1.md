# R1 Start Gate v1

R1 full run remains blocked until every item below is explicit and green.

## Preconditions

1. Sanity batch passed.
2. CI green.
3. Branch protection OK.
4. Iron Fence stable.
5. `catalog_evidence_policy_v1` frozen for run.
6. `family_photo_policy_v1` frozen for run.
7. `source_role_field_matrix_v1` frozen for run.
8. Replayable review reasons working end-to-end.

## Operational guardrails

1. `trace_id` present for each SKU execution path.
2. `idempotency_key` present for side effects and export writes.
3. Retry policy bounded and classed as transient/permanent.
4. Structured audit log enabled.
5. Structured review bucket output enabled.
6. Checkpoint/resume integrity verified.

## Explicit non-goal

Passing this gate does not grant live publish approval by itself.
Owner approval is still required before opening live publish side effects.
