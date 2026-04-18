# LLM Correction Pipeline — Architecture Plan v1

**Status:** Draft for AI peer review
**Date:** 2026-04-17
**Owner:** Evgeny Bireta (biretos-automation)
**Context:** Pipeline v2 catalog enrichment, branch `feat/rev-r1-catalog`

## 1. Problem Statement

### 1.1 The triggering incident

On 2026-04-16 an `auto-fix` pass (Claude Sonnet 4.5) rewrote the brand of
**55 SKUs** in `downloads/evidence/evidence_<pn>.json` files based on
single-shot LLM output. **19/55 changes were wrong.** Examples:

| PN            | Was         | Auto-fix wrote       | Correct          | Why wrong |
|---------------|-------------|----------------------|------------------|-----------|
| FX808313      | Honeywell   | OBO Bettermann       | Esser/Honeywell  | Ignored `confirmed_manufacturer="Esser"` already in evidence, ignored URL `walde.ee/esser-by-honeywell` |
| HVAC46C5      | Honeywell   | Hyundai              | Honeywell        | Ignored HVAC** series convention |
| 1011894-RU    | Sperian     | Honeywell            | Sperian          | Lost sub-brand (Sperian is a Honeywell safety brand) |
| EVCS-HSB      | Notifier    | Honeywell            | Notifier         | Lost sub-brand |
| 2208WFPT      | Dell        | Honeywell            | Dell             | Inverted correct direction |
| NE-NICS02     | NEC         | Honeywell            | NEC              | PN prefix `NE-*` is NEC convention |

### 1.2 Root-cause analysis (six architectural defects)

Reconstructed from `scripts/pipeline_v2/_auto_fix_from_audit.py`, lines 79-95
and the actual evidence content for FX808313:

1. **Evidence Blind Spot.** The prompt sent LLM only 4 fields
   (`pn`, `current_brand`, `seed_name`, `title_from_datasheet`).
   The evidence file already contained 40+ fields with authoritative data:
   - `structured_identity.confirmed_manufacturer = "Esser"` (from DR 2026-04-12)
   - `deep_research.sources[0].url = "walde.ee/en/fire-alarm-systems/esser-by-honeywell/flexes"`
   - `deep_research.description_ru = "ESSER FlexES Control"`
   - `dr_price_source = "...esser-by-honeywell..."`
   None of these were shown to the LLM.

2. **Trust Hierarchy Inversion.** `structured_identity.confirmed_manufacturer`
   is populated by a slow, expensive DR (Deep Research) pipeline with URL
   grounding. Top-level `brand` is populated by a cheap, early import step.
   Auto-fix treated them as equal and picked LLM guess over DR ground-truth.
   No declarative hierarchy existed.

3. **No URL Semantic Parsing.** Domains like `esser-by-honeywell.com`,
   `obo.de`, `peha.de` are **direct brand signals** and don't need LLM at all.
   The code never extracted domains from evidence for use as brand hints.

4. **No Sibling Consistency Check.** For FX808313, 4 sibling PNs
   (FX808324, FX808341, FX808364, FX808397) were all correctly tagged Esser
   by the same pass. A consistency rule "FX\d+ family must agree on brand"
   would have caught the outlier.

5. **No Confidence Gate.** LLM replies with `confidence="medium"` were
   applied identically to `confidence="high"`. No threshold.

6. **Single-Pass, No Validation.** Stage-1 proposal was immediately written
   to evidence. No Stage-2 validator cross-checking proposal against evidence,
   siblings, or URLs.

### 1.3 Why this is a class, not an incident

The same shape appears in other pipeline steps:

| Step                        | Evidence fields ignored             | Risk |
|-----------------------------|-------------------------------------|------|
| EAN extraction              | `documents.datasheet.local_path`    | Wrong EAN attached to SKU |
| Description generation      | `deep_research.key_findings`        | Generic text not about the product |
| Specs extraction            | Existing `from_datasheet.specs`     | Duplicate work, stale override |
| Photo selection             | `deep_research.sources[].url`       | Wrong-product photo |
| Category assignment         | `dr_category`, `expected_category`  | Mismatched InSales category |

Each will produce its own incident unless the pattern is fixed at the
architectural layer.

## 2. Design Principles

### P1 — Evidence-First Contract (EFC)

Every LLM-touching operation MUST receive a machine-built `EvidencePack`,
not a hand-picked subset. The pack is assembled by a single helper from
the evidence file; callers cannot override which fields to include.

### P2 — Trust Hierarchy (explicit, declarative)

Data sources ranked by trust, highest wins on conflict:

| Tier | Source                                              | Trust |
|------|-----------------------------------------------------|-------|
| T0   | Manufacturer URL match in DR `sources[].url`        | 1.00  |
| T1   | `structured_identity.confirmed_manufacturer` + `identity_confirmed=true` + `exact_title_pn_match=true` | 0.95 |
| T2   | `from_datasheet.*` (parsed from official PDF)       | 0.90  |
| T3   | DR narrative (`deep_research.description`, `key_findings`) | 0.80  |
| T4   | Legacy top-level fields (`brand`, `subbrand`)       | 0.50  |
| T5   | LLM inference without evidence                      | 0.30  |

Correction logic:
- If T0-T2 agree → LLM cannot override, SKU is locked from auto-fix.
- If T1 and T4 disagree → trust T1, sync T4 to it.
- Cross-tier consensus raises effective trust; disagreement lowers it.

### P3 — URL Brand Oracle (rule-based, no LLM)

Static dictionary of domain regex → brand. Applied BEFORE any LLM call.
Any SKU whose DR sources contain a matched domain has brand set from the
oracle; LLM is never asked.

### P4 — Sibling Consistency Invariant

Siblings = PNs matching the same series regex (FX\d+, HVAC\w+, PEHA 6-digit,
etc.). Rule: proposed brand for PN X must match ≥60% of its siblings'
brands. Violations → review bucket, no auto-apply.

### P5 — Two-Stage Correction Protocol

- **Stage 1 (Propose):** LLM suggests `{new_brand, confidence, evidence_citations[]}`
- **Stage 2 (Validate):** Rule engine checks:
  - Proposal cites ≥1 evidence field (by JSON path)
  - Proposal doesn't violate Trust Hierarchy (P2)
  - Proposal passes URL Oracle if URLs exist (P3)
  - Proposal passes Sibling Consistency (P4)
  - Confidence == "high"
- Pass all five → apply. Else → review bucket (`downloads/staging/review_bucket/`)

### P6 — Review Bucket, Not Silent Failure

Never "apply and hope." Every rejected proposal becomes a reviewable JSON
record with: proposal, evidence pack, which gate failed, reasoning. Batch
review by owner (or later, by a stronger LLM pass).

### P7 — Observability per Correction

Every correction writes a log record containing:
- Input evidence fields (by path)
- LLM output verbatim
- Each validation gate result
- Final decision: apply / review / reject
- Cost, latency, model

Enables audit, training data, and regression detection.

### P8 — Training Data by Default

Every Stage-1 proposal + Stage-2 verdict = one labeled pair for local
validator training. This is how we eventually replace cloud Sonnet with
a local model.

## 3. Components to Build

### 3.1 `scripts/pipeline_v2/evidence_pack.py`

```python
def build_evidence_pack(pn: str) -> EvidencePack: ...
```

- Single authoritative loader. Reads `evidence_<pn>.json`, constructs
  a typed `EvidencePack` with all relevant fields extracted, including
  parsed URL domains, sibling PNs, trust-tier assignments.
- Pydantic model, versioned schema.
- Used by every LLM-touching script.

### 3.2 `scripts/pipeline_v2/trust_hierarchy.py`

```python
def resolve_brand(pack: EvidencePack) -> BrandResolution:
    """Returns best-guess brand with trust tier + cited evidence."""
```

- Applies P2 rules deterministically.
- Returns `{brand, trust_tier, supporting_evidence_paths[]}`.
- Used as both the trust oracle and as Stage-1 prior for LLM.

### 3.3 `config/url_brand_oracle.json`

```json
{
  "esser-by-honeywell": "Esser (Honeywell)",
  "obo.de|obogroup": "OBO Bettermann",
  "peha.de|peha.com": "PEHA (Honeywell)",
  "dkc.ru": "DKC",
  "phoenixcontact": "Phoenix Contact",
  ...
}
```

- Hand-curated plus auto-discovered from `config/seed_source_trust.json`.
- Compiled to regex at load.

### 3.4 `scripts/pipeline_v2/sibling_gate.py`

```python
def sibling_check(pn: str, proposed_brand: str) -> SiblingCheck:
    """Find PNs in same series; check proposal against majority brand."""
```

- Series patterns: `FX\d+`, `HVAC\w+C\d`, `3240\d+`, `NE-\w+`, `P[0-9]{4}\w*`, etc.
- Returns `{siblings_found, majority_brand, agrees: bool, confidence}`.

### 3.5 `scripts/pipeline_v2/brand_correction_gate.py`

```python
def propose_and_validate(pn: str) -> CorrectionOutcome:
    """Full P5 Two-Stage Correction Protocol."""
```

- Orchestrator. Replaces `_auto_fix_from_audit.py`'s brand logic.
- Emits: `apply` | `review` | `reject` with full audit trail.

### 3.6 `scripts/pipeline_v2/review_bucket.py`

```python
def send_to_review(pn: str, proposal: dict, reason: str): ...
def list_review_bucket() -> list[ReviewItem]: ...
def apply_review_decision(pn: str, decision: str): ...
```

- Writes to `downloads/staging/review_bucket/<pn>.json`.
- CLI for batch review.

### 3.7 `docs/TRUST_HIERARCHY.md`

Living document listing every evidence field and its trust tier.
Reviewed when adding new fields.

### 3.8 Generalization hooks

Same Stage-1/Stage-2 pattern applied to:
- `ean_correction_gate.py` (uses `from_datasheet.ean`, sources URLs)
- `description_correction_gate.py` (uses DR description vs generated)
- `specs_correction_gate.py` (datasheet is canonical per existing rule)
- `category_correction_gate.py` (uses `dr_category` + classifier)

Each gate reuses `evidence_pack.py`, `trust_hierarchy.py`, and
`review_bucket.py`.

## 4. Implementation Phases

### Phase A — Rollback + Canonicalize (1 day)

- [x] Already done: `_validate_brand_changes.py` reverted 19 wrong changes.
- [ ] Build `evidence_pack.py` (no logic change, just canonical loader).
- [ ] Rewrite `_validate_brand_changes.py` to use `evidence_pack.py`.
- [ ] Add tests: deterministic input → deterministic pack.

### Phase B — Rule Engines (2 days)

- [ ] `trust_hierarchy.py` with unit tests for each tier rule.
- [ ] `config/url_brand_oracle.json` seeded from `seed_source_trust.json` + hand-curation.
- [ ] `sibling_gate.py` with tests for known series (FX, HVAC, 3240, NE-).

### Phase C — Gates (2 days)

- [ ] `brand_correction_gate.py` orchestrator.
- [ ] `review_bucket.py` + CLI.
- [ ] Replace `_auto_fix_from_audit.py` brand path with new gate.
- [ ] Shadow-mode run: compute decisions without applying, compare to
  human-verified ground-truth on the 55 SKUs that already have reviewed verdicts.

### Phase D — Generalize (3 days)

- [ ] Apply same pattern to EAN, description, specs, category gates.
- [ ] `docs/TRUST_HIERARCHY.md` filled in.
- [ ] Update `scripts/MANIFEST.json` entries.

### Phase E — Training Data (ongoing)

- [ ] Every gate logs proposal + verdict to `downloads/training_v2/validation_decisions.jsonl`.
- [ ] When ≥500 pairs: first local validator fine-tune attempt.

## 5. Success Criteria

1. **Correctness:** On the 55 SKUs from the incident, new gate's verdicts
   match the human-verified ground-truth (from `brand_validation_log.jsonl`)
   with ≥95% precision. Shadow-mode comparison before rollout.

2. **Coverage:** ≥80% of brand corrections decided automatically (high
   confidence, all gates pass); ≤20% sent to review bucket.

3. **Auditability:** Every applied correction has ≥1 evidence citation
   (JSON path) and a trust-tier trace in the log.

4. **No regressions:** Existing T1/T2 values (`confirmed_manufacturer`,
   `from_datasheet.*`) are never overwritten by an LLM proposal at lower tier.

5. **Observability:** 100% of corrections produce a training pair.

## 6. Open Questions for Reviewers

**Q1.** Should the URL Oracle be authoritative (overrides LLM even with
"high" confidence), or just another weighted signal? Risk of authoritative:
stale domain → wrong brand. Risk of weighted: LLM hallucination wins.

**Q2.** Sibling gate threshold: 60% agreement, 80%, or require unanimity?
Tradeoff: unanimity may freeze all corrections in heterogeneous series;
60% may let a minority pattern sneak through.

**Q3.** Is Trust Hierarchy P2 too rigid? Some `from_datasheet.*` fields
are themselves extracted by LLM (Gemini PDF parse) — should they really
outrank a fresh Sonnet call with web access?

**Q4.** Review Bucket: should rejected proposals auto-expire, or sit
forever? How to prevent review-bucket starvation?

**Q5.** Should the gate be language-aware? Esser datasheets are German,
OBO datasheets are also German — in the FX808313 case, German language
was a confound. Does the gate need a `datasheet_language` signal?

**Q6.** For LLM proposals, should we require the LLM to also output which
*competing* brand it considered and why it rejected them? Explicit
alternative-hypothesis reasoning might reduce hallucination.

**Q7.** Generalization: does this same pattern work for **photo selection**?
Photos don't have clean domain signals the same way text does. What's the
analog of Trust Hierarchy there?

**Q8.** Cost envelope: current incident cost $1.40 to create, $0.27 to
fix. Projected gate overhead: 2× LLM calls (propose + validate) = roughly
2× cost. Is that acceptable, or should Stage-2 validation be rule-only
(no second LLM call)?

## 7. What I am NOT proposing

- Not rewriting the pipeline from scratch. This adds guardrails around
  existing components.
- Not removing LLM from the loop. LLM still proposes; rules validate.
- Not blocking all auto-apply. High-confidence, multi-tier-consensus
  proposals still apply automatically.
- Not replacing `structured_identity` or DR. Those remain canonical
  sources; this work just makes downstream steps respect them.

## 8. Appendix — The FX808313 case walked through the new pipeline

**Input evidence (actual file):**
- `structured_identity.confirmed_manufacturer = "Esser"` (T1, trust 0.95)
- `deep_research.sources[0].url = "walde.ee/.../esser-by-honeywell/..."` (T0 signal)
- `from_datasheet.title = "Akku-Erweiterungsgehäuse..."` (T2, German)
- `brand = "Honeywell"` (T4, trust 0.50)

**Trust Hierarchy output:**
- T0 URL Oracle match: `esser-by-honeywell` → "Esser (Honeywell)"
- T1 structured_identity: "Esser"
- T0 + T1 consensus → locked brand = "Esser (Honeywell)". SKU removed
  from auto-fix candidate list.

**If auto-fix were still triggered (it wouldn't be):**
- LLM proposes "OBO Bettermann".
- Stage-2 validator:
  - Evidence citation? No field supports OBO.  **FAIL**
  - Trust Hierarchy? Proposal contradicts T0+T1.  **FAIL**
  - URL Oracle? Matched domain says Esser.  **FAIL**
  - Sibling Gate? FX808324/341/364/397 all Esser, proposal is outlier.  **FAIL**
- Decision: reject. Not even review — outright reject.

**Net effect:** the exact incident becomes impossible by construction.

---

*End of plan. Reviewers: please focus on Questions Q1-Q8 in §6, and
whether Phase B's rule engines are over- or under-specified.*
