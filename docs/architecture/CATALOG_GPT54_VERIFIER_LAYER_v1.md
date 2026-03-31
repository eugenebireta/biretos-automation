# Catalog GPT-5.4 Verifier Layer v1

Status: SHADOW-MODE READY  
Scope: `R1 / Phase A / Tier-3`

## Purpose

Add a narrow GPT-5.4 verification layer on top of the existing deterministic
catalog enrichment pipeline without replacing policy or widening Phase A scope.

The verifier is:

- deterministic-gated
- optional
- traceable
- replayable
- shadow-mode only in v1

## Layered Architecture

### Layer A - Deterministic Bulk Layer

Current bulk source of truth:

- candidate lake
- source-role matrix
- `catalog_evidence_policy_v1`
- `family_photo_policy_v1`
- `card_status_calculator()`
- replayable `review_reasons[]`
- sidecar/export/audit artifacts

This layer still decides the final card status by default.

### Layer B - Risk Router

The router decides whether a SKU should be sent to the verifier. It is
deterministic and evidence-based.

Default trigger family:

- `IDENTITY_NOT_STRONG`
- `PRICE_REVIEW_REQUIRED`
- `PDF_REVIEW_REQUIRED`
- `FAMILY_PHOTO_ONLY`
- `CRITICAL_POLICY_CONFLICT`
- `AMBIGUOUS_EXACTNESS`
- optional explicit `PREPUBLISH_HIGH_VALUE`
- optional explicit `BATCH_AUDIT_SAMPLE`

No routing trigger may be based on search hints or raw supplier data.

### Layer C - GPT-5.4 Verifier

Integration contract:

- OpenAI Responses API only
- primary model target: `gpt-5.4`
- default `reasoning.effort = high`
- `medium` allowed for lighter audits
- structured input packet only
- structured output only
- no built-in tools enabled by default
- no internet or freeform retrieval
- no guessing without evidence

The verifier receives an evidence packet already assembled by the deterministic
pipeline. It does not become a new proof source.

### Layer D - Decision Merger

v1 merger rules:

- mode = `shadow`
- deterministic final decision remains authoritative
- verifier cannot unlock auto-publish
- verifier cannot override deterministic publish/no-publish
- verifier may only log, recommend review routing, or recommend owner escalation

## OpenAI Integration

This layer uses the Responses API because Responses is the current unified
endpoint for text generation and structured output, while Responses structured
output uses `text.format`, not `response_format`.

Runtime contract:

- env-driven feature flag
- timeout and bounded retry
- deterministic request correlation via `trace_id` and `idempotency_key`
- `X-Client-Request-Id` header mirrors `trace_id`
- usage and estimated cost logging
- `store = false` by default

## Input Packet

The verifier packet includes:

- `pn_primary`
- normalized title
- deterministic card status
- field-level statuses
- replayable review reasons
- review buckets
- structured identity flags
- PDF/image/price evidence summaries
- source-role evidence summary
- policy versions
- risk reason codes
- trace and idempotency identifiers

## Output Contract

The verifier returns structured JSON only with:

- model/version
- verdict family
- confidence
- short rationale
- blocking reason codes
- suggested action
- suggested review bucket
- evidence sufficiency
- contradictions found
- `safe_to_autopublish`

Even if the verifier says `CONFIRM_AUTOPUBLISH_ELIGIBLE`, shadow mode does not
change the deterministic card status.

## Safety Boundaries

Preserved invariants:

- search hints are never identity proof
- CSV/raw supplier feed are never identity proof
- `pn_secondary` never auto-promotes to proof
- raw PDF text/spec/url/title are not verifier proof
- GPT-5.4 complements policy; it does not replace policy
- no live publish side-effects are introduced
- no broader/full run is opened by this layer
