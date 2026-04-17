# LLM Correction Pipeline — Architecture Plan v1.2

**Status:** Draft for external peer review. Supersedes v1.1.
**Date:** 2026-04-17
**Owner:** Evgeny Bireta (biretos-automation, Russia; product catalog enrichment)
**Precondition:** R1 Start Gate green (Iron Fence 5.5.1-5.5.3 stable, CI green, branch protection configured). Until then only Step 1 hotfix (`b5dd281`) is live.

---

## 0. Context for external reviewers

If you are reading this cold, here is what you need:

**The system.** An enrichment pipeline that gathers product data (brand, EAN, specs, category, description, photos) from multiple sources — Deep Research (DR) via GPT, Gemini PDF parsing, distributor scraping, local Excel import — and writes to per-SKU JSON files at `downloads/evidence/evidence_<pn>.json`. Each file contains ~40 fields populated by different stages. There are 370 SKUs; the target marketplaces are InSales, Ozon, Wildberries.

**The incident (2026-04-16).** An "auto-fix" stage called Claude Sonnet with a 4-field prompt (`pn`, `current_brand`, `seed_name`, `datasheet_title`) and wrote the LLM's brand proposal into evidence files. 55 SKUs were modified. A post-hoc validator later reverted **19 as wrong**. Example: FX808313, a Honeywell/Esser fire-alarm battery housing, was re-branded as "OBO Bettermann" despite the evidence file already containing `structured_identity.confirmed_manufacturer = "Esser"` and a DR source URL `walde.ee/en/fire-alarm-systems/esser-by-honeywell/flexes`. The LLM never saw those fields.

**Empirical finding.** All 55 incident SKUs had `structured_identity.confirmed_manufacturer` populated. That single field, used naively, resolves 41/55 cases correctly. The remaining 14 are parent/sub-brand ambiguities.

**What's already done.** Step 1 hotfix (`b5dd281`) — a 120-line Python module that blocks the auto-fix code path from proposing brand changes when `confirmed_manufacturer` is populated. 24 tests pass, including a parametrized regression on all 19 incident SKUs.

**What this plan is.** Defense in depth — a correction pipeline where LLM *proposes*, deterministic Python *validates*, and a review bucket holds the ambiguous cases. This v1.2 supersedes v1 and v1.1 after three rounds of AI audit uncovered blockers in both earlier versions. Audit results are appended in §12.

**What this plan is NOT.** Not a second source of truth (see §10). Not a description or photo corrector (different paradigms). Not a replacement for DR or datasheet parsing pipelines.

---

## 1. Six architectural defects in the incident (root cause, unchanged)

1. **Evidence Blind Spot.** 4/40+ fields were sent to the LLM.
2. **Trust Hierarchy Inversion.** `structured_identity.confirmed_manufacturer` (set by DR with URL grounding) treated as equal to legacy top-level `brand`.
3. **No URL Semantic Parsing.** Domains like `esser-by-honeywell.com` are direct brand signals, never extracted.
4. **No Sibling Consistency Check.** FX808324/341/364/397 were correctly tagged Esser in the same batch; FX808313 was the outlier.
5. **No Confidence Gate.** LLM `confidence="medium"` applied identically to `"high"`.
6. **Single-Pass, No Validation.** Stage-1 proposal written immediately to evidence.

---

## 2. Design principles

### P1 — Evidence-First Contract

Every LLM-touching operation reads a machine-built `EvidencePack`, not hand-picked fields. The pack is assembled by `scripts/pipeline_v2/evidence_pack.py`, a single loader; callers cannot override its output. Provenance tags are **computed at load time** from existing fields; existing evidence JSON files are never mutated for provenance.

### P2 — Trust Hierarchy (refined)

Every value in evidence is assigned one of the following tiers by the EvidencePack loader:

| Tier     | Source                                                                      | Base trust | Verification timestamp field              |
|----------|-----------------------------------------------------------------------------|:----------:|-------------------------------------------|
| T-H      | Human-approved in `review_bucket/approved/`                                 | 1.00       | `approved_at`                             |
| T1-URL   | Manufacturer-domain URL + exact PN in URL path + oracle role="manufacturer" | 0.96       | `last_verified` (in oracle config)        |
| T1-DR    | `structured_identity.confirmed_manufacturer` **with** `exact_title_pn_match` or `exact_h1_pn_match` | 0.92       | `structured_identity.ts` (derived from `brand_source`) |
| T1-DR-w  | `structured_identity.confirmed_manufacturer` alone, no exact_match flag     | 0.80       | same                                      |
| T2a      | `from_datasheet.*` parsed from PDF whose URL is in manufacturer domain      | 0.85       | `from_datasheet.merged_at`                |
| T2b      | `from_datasheet.*` parsed from PDF from third-party domain                  | 0.70       | same                                      |
| T3       | `deep_research.description` / `deep_research.key_findings` (text)           | 0.60       | `deep_research.merge_ts`                  |
| T4       | Legacy top-level `brand` / `subbrand` (pre-enrichment import)               | 0.40       | `generated_at` (file-level)               |
| T5       | LLM inference without grounding                                              | 0.20       | now()                                     |

Design properties (checked by unit tests):
- **Monotonic.** T-H > T1-URL > T1-DR > T2a > T1-DR-w > T2b > T3 > T4 > T5. Labels and numeric order agree. (Note the intentional interleave: an official PDF T2a outranks a weak T1-DR with no exact match.)
- **Tier is a property of evidence, not of the field.** Same field name (e.g. `brand`) can be T-H today and T4 tomorrow based on how it got set.
- **No tier is "T0".** Previous plans mentioned T0 — it no longer exists.

**Freshness decay.** Effective trust at age `m` months:

```
effective_trust(tier, m) = base_trust × (0.5 + 0.5 × exp(-m / 18))
```

Values: 0m → 1.00×, 6m → 0.86×, 12m → 0.77×, 24m → 0.65×, 48m → 0.53×, 96m → 0.50× (asymptote at 0.50×).

Rationale: a 4-year-old T1-URL (0.96 × 0.53 = 0.51) drops below a fresh T2a (0.85 × 1.0 = 0.85) but stays above fresh T4 (0.40 × 1.0 = 0.40). Stale data weakens but doesn't die.

**Consensus lift.** Independent multi-tier agreement raises effective trust:
- 2+ agreeing citations, at least one ≥T2a: effective trust of the top-supporting citation × 1.05 (cap at 0.98).
- Lift never exceeds T-H (1.00). Lift never exceeds a higher fresh tier — specifically, two T2b citations cannot lift above a fresh T1-URL.

Precise rule (replaces the v1.1 "two T2b outrank manufacturer URL" bug):

```
effective = max(top_fresh_trust, top_fresh_trust × 1.05 if (≥2 agreeing citations AND ≥1 is T2a/T1-URL))
effective = min(effective, 0.98)
```

**Override path for stale T1-DR.** If `top_fresh_trust` comes from T1-DR older than 24 months, AND there are ≥2 fresh (age < 6m) T1-URL or T2a citations that disagree, T1-DR moves to `review_bucket/stale_contradiction/` and is excluded from this decision. The override is stateful; it is recorded in the correction journal with an `idempotency_key` that includes the fresh-citation set hash, so repeated batch runs produce the same outcome.

### P3 — URL Brand Oracle

File: `config/url_brand_oracle.json`. Entries:

```json
{
  "esser-by-honeywell\\.(com|de|eu)": {
    "brand": "Esser (Honeywell)",
    "role": "manufacturer",
    "last_verified": "2026-04-10",
    "exact_pn_in_path_required": true
  },
  "walde\\.ee": {
    "brand_hint_only": true,
    "role": "distributor",
    "comment": "multi-brand; URL path may hint brand but does not certify"
  }
}
```

Authoritative T1-URL rating ONLY when **all** conditions hold:
- `role == "manufacturer"` AND
- `exact_pn_in_path_required == true` satisfied (PN literally in URL path) AND
- `last_verified` within 180 days AND
- no higher-tier contradiction.

Otherwise entry is hint-only, feeds into Stage-1 prompt as context, never gates.

**Config sustainability.** Seeded with ~30 manufacturer domains curated by owner from `config/seed_source_trust.json`. Unit-tested against a hand-labeled golden dataset of 200 URLs (200, not 1000 — critique #3 recommendation). Auto-discovery proposes new entries to `review_bucket/oracle_candidates/` but never self-promotes to config. At >200 entries, migrate to SQLite; at >500, per-brand YAML files.

### P4 — Sibling Consistency Gate (veto only)

Siblings = PNs matching the same series regex. Series patterns in `config/series_patterns.json`:

```json
{
  "FX_esser":    {"regex": "^FX\\d+", "expected_brand": "Esser"},
  "PEHA_6digit": {"regex": "^\\d{6}$", "expected_brand": "PEHA", "confidence": 0.6},
  "NE_NEC":      {"regex": "^NE-\\w+", "expected_brand": "NEC"},
  "PCD_saia":    {"regex": "^PCD\\d\\.\\w+", "expected_brand": "Saia-Burgess"},
  "Dell_U":      {"regex": "^U\\d{4}\\w*", "expected_brand": "Dell"},
  "HVAC_C":      {"regex": "^HVAC\\w+C\\d+", "expected_brand": "Honeywell"}
}
```

Gate behavior (decides nothing; only vetoes or flags):

```
siblings = find_siblings(pn, patterns)  # excludes pn itself
effective_siblings = [s for s in siblings if sibling_brand_tier(s) >= T2b]
if len(effective_siblings) < 3:
    return SiblingCheck(decision="abstain", reason="fewer than 3 T2b+ siblings")

majority_brand, majority_fraction = mode_with_fraction(effective_siblings)

if majority_fraction >= 0.80:
    if proposed_brand == majority_brand:
        return SiblingCheck(decision="agree", lift=True, fraction=majority_fraction)
    else:
        return SiblingCheck(decision="veto", reason=f"{majority_fraction:.0%} siblings say {majority_brand}")
if majority_fraction >= 0.60:
    return SiblingCheck(decision="flag_review", reason="mixed family")
return SiblingCheck(decision="abstain", reason="no clear majority")
```

Note: `agree` is reported as a **lift input** for computed confidence, not as a decision. The veto (disagreement with strong majority) is the only way siblings can block a proposal.

Threshold 80% (not 60%). Min 3 **effective** siblings (T2b+), not any siblings (critique #2's "bootstrap problem" — can't trust majority built on T4 legacy data).

### P5 — Two-Stage Correction Protocol

**Stage 1 — Propose (1 LLM call, Claude Sonnet).** Prompt template:

```
Evidence for SKU {pn}:
{full_evidence_pack_json}

Sibling brands (T2b+, same series):
{sibling_list}

URL Oracle matches (manufacturer-role URLs in DR sources):
{oracle_matches}

Known sub-brand registry (parent → sub-brands):
{subbrand_registry_subset_for_parent}

Task: propose the correct brand for this SKU. You MUST:
1. Cite specific evidence JSON paths supporting your proposal
2. List rejected_alternatives with reason each was rejected
3. Preserve sub-brand if evidence supports it (do not collapse Esser to Honeywell)
4. Declare "needs_review" if evidence is insufficient

Return JSON:
{
  "proposed_brand": "<name or 'needs_review'>",
  "evidence_citations": [{"path": "structured_identity.confirmed_manufacturer", "value": "Esser"}, ...],
  "rejected_alternatives": [{"brand": "OBO Bettermann", "why_rejected": "no evidence path supports this"}, ...],
  "sub_brand_preserved": true | false | "n/a"
}
```

**Stage 2 — Validate (pure Python, no LLM).**

All gates are concrete:

- **Gate A — Citation presence.**
  ```
  A_pass = len(proposal.evidence_citations) >= 1 AND every cited path exists in EvidencePack
  ```

- **Gate B — Trust hierarchy respected.**
  ```
  cited_tiers = [tier_of(path) for path in proposal.evidence_citations]
  top_cited = max(effective_trust(t) for t in cited_tiers)
  B_pass = (proposed_brand == tier_value_at(top_cited)) OR
           (proposed_brand matches parent-of(tier_value_at(top_cited)) under subbrand_registry)
  ```

- **Gate C — URL Oracle.**
  ```
  oracle_verdict = evaluate_url_oracle(evidence_pack.dr_source_urls, pn, proposed_brand)
  # returns: "agree" | "disagree" | "abstain"
  C_pass = oracle_verdict != "disagree"
  ```

- **Gate D — Sibling veto.**
  ```
  sibling = sibling_gate(pn, proposed_brand)
  D_pass = sibling.decision != "veto"
  ```

- **Gate E — Sub-brand preservation.**
  Registry at `config/subbrand_registry.json`:
  ```json
  {"Honeywell": ["Esser","Sperian","Notifier","PEHA","Howard Leight","Saia-Burgess","Distech"],
   "Schneider": ["Merten","Berker"]}
  ```
  ```
  current_or_evidence_subbrand = detect_subbrand(evidence_pack)
  if current_or_evidence_subbrand:
      E_pass = (proposed_brand == current_or_evidence_subbrand) OR
               (proposed_brand names the subbrand, not only parent)
  else:
      E_pass = True
  ```

  **Within-family disambiguation (addresses audit #1 P9 gap).** If proposal names sub-brand X of parent Y, require evidence specifically for X: either (a) literal "X" or "by X" in any evidence text field, OR (b) manufacturer-role URL for X in DR sources, OR (c) ≥2 T2b+ siblings with sub-brand X. If none, proposal downgrades to parent-only (a soft failure, records a warning in journal).

- **Gate F — Computed confidence ≥ threshold.** Concrete formula:

  ```
  # Each component returns a value in [0,1] OR "abstain"
  
  citation_score = min(1.0, N_citations / 3)
  # 3+ citations = 1.0; 2 citations = 0.67; 1 citation = 0.33
  
  tier_score = max(effective_trust(tier) for tier in cited_tiers)
  # Already in [0.20, 1.00]; use directly
  
  if oracle_verdict == "abstain":
      url_oracle_score = "abstain"
  else:
      url_oracle_score = 1.0 if oracle_verdict == "agree" else 0.0
  
  if sibling.decision == "abstain":
      sibling_score = "abstain"
  elif sibling.decision == "agree":
      sibling_score = sibling.fraction  # 0.80..1.00
  elif sibling.decision == "veto":
      sibling_score = 0.0
  elif sibling.decision == "flag_review":
      sibling_score = 0.5
  
  # Weight renormalization: drop abstaining components, redistribute weight.
  weights = {"citation": 0.3, "tier": 0.3, "url": 0.2, "sibling": 0.2}
  active = {k: v for k, v in {"citation": citation_score, "tier": tier_score,
                              "url": url_oracle_score, "sibling": sibling_score}.items()
            if v != "abstain"}
  total_weight = sum(weights[k] for k in active)
  confidence = sum(weights[k] * active[k] for k in active) / total_weight
  ```

  **Thresholds:**
  - `confidence >= 0.85` → auto-apply (subject to all other gates passing)
  - `0.70 <= confidence < 0.85` → tiebreaker: one additional LLM call (Claude Sonnet) with the gate traces as input, votes apply/review
  - `confidence < 0.70` → review bucket

  Rationale for 0.85: empirically, all 41/55 T1-resolvable incident cases have citation_score ≥ 0.33, tier_score ≥ 0.80 (T1-DR with exact match), and no veto → minimum confidence ≈ 0.30×0.33 + 0.30×0.80 + 0.20×agree + 0.20×agree ÷ 1.0 = 0.1 + 0.24 + 0.2 + 0.2 = 0.74 when both URL and siblings agree, or 0.34 renormalized if both abstain. Setting 0.85 requires robust evidence; 0.70 threshold for tiebreaker catches the borderline cases.

**Decision matrix:**

| Gates A-E | Confidence | Outcome |
|:---------:|:----------:|---------|
| all pass  | ≥ 0.85     | apply   |
| all pass  | 0.70-0.85  | LLM tiebreaker (1 call) |
| all pass  | < 0.70     | review  |
| any fail  | —          | review with `gate_failed` reason |

Every outcome writes to `correction_journal.jsonl` before any evidence mutation.

### P6 — Review Bucket with SLA

Path: `downloads/staging/review_bucket/{pending,approved,rejected,archive}/`.

Each file `<pn>__<correction_id>.json` contains: proposal, evidence pack snapshot, gate trace, suggested_action, priority (price-derived), cluster_hint (sibling series). Lifecycle:
- `pending/` → `approved/` or `rejected/` via `review_bucket apply <correction_id> <decision>` CLI
- `pending/` items older than 30 days → `archive/`; not deleted; feeds training data
- Daily digest to owner via existing Telegram bot `biretarus_bot.py` (critique #3: no SMTP in repo, use Telegram channel instead)
- CLI: `review_bucket list --cluster` shows top 10 clusters by (proposed_brand × series) for batch review

### P7 — Observability and DNA compliance

Every correction attempt writes to `downloads/staging/correction_journal.jsonl`:

```json
{
  "correction_id": "uuid4",
  "trace_id": "uuid4",
  "idempotency_key": "sha256(pn|stage|evidence_pack_hash|proposal_hash)",
  "pn": "FX808313",
  "stage": "brand_correction",
  "before": {"brand": "Honeywell"},
  "proposed": {"brand": "Esser (Honeywell)"},
  "gates": {
    "A": {"pass": true, "n_citations": 2},
    "B": {"pass": true, "top_tier": "T1-DR", "effective_trust": 0.92},
    "C": {"pass": true, "oracle_verdict": "agree", "matched_domain": "esser-by-honeywell.de"},
    "D": {"pass": true, "sibling_decision": "agree", "fraction": 1.0},
    "E": {"pass": true, "subbrand_preserved": true},
    "F": {"confidence": 0.91, "threshold": 0.85, "components": {"citation": 0.67, "tier": 0.92, "url": 1.0, "sibling": 1.0}}
  },
  "decision": "apply",
  "reversible_patch": {"path": "$.brand", "op": "replace", "from": "Honeywell", "to": "Esser (Honeywell)"},
  "cost_usd": 0.004,
  "model": "claude-sonnet-4-5",
  "ts": "2026-04-17T10:00:00Z",
  "error": null
}
```

**DNA §7 compliance (not §11 — reviewer corrected):**
- Item 1 `trace_id` ✓
- Item 2 `idempotency_key` ✓ (content-addressed; replay produces identical decision unless evidence changed)
- Item 3 single-flush per decision (fsync on each appended line)
- Item 5 **redaction**: `before/proposed/evidence_pack_hash` strip any values matching `[A-Za-z0-9]{32,}` that aren't from a whitelisted field (prevents leaking tokens embedded in URLs)
- Item 6 runnable in isolation: every module has `if __name__ == "__main__"` entry point
- Item 7 deterministic test: incident regression test + hold-out comparison
- Item 8 structured decision log ✓
- Item 9 **error schema**: `error = {class: "TRANSIENT|PERMANENT|POLICY_VIOLATION", severity: "WARNING|ERROR", retriable: bool, message: str}` when any gate or LLM call raises

`revert_correction(correction_id)` replays `reversible_patch` in reverse and appends a new journal entry. Never rewrites history.

### P8 — Training Data, trigger-based (not calendar)

Three tiers, critique-resolved:

- **Gold.** Human-approved in `review_bucket/approved/`. Used as positive labels for fine-tune.
- **Silver.** Applied by gate (not human-approved) AND all of:
  - next enrichment pass re-audits the SKU and agrees
  - no customer complaint linked to the SKU in Core DB (`rev_*` support ticket table) within 90 days
  - no revert via `revert_correction` within 180 days
  Only marked silver when all three triggers fire. No calendar-only silver.
- **Rejected.** Failed any gate, or reverted. Used as **negative examples** (what NOT to propose), never as positive labels.

File: `downloads/training_v2/validation_decisions.jsonl`. Fine-tune pipeline (Phase E, opportunistic) reads only gold + silver with weights 1.0 and 0.5 respectively.

### P9 — Sub-brand Preservation (disambiguating)

Addressed at Gate E above. Key addition over v1.1: if the LLM proposes a sub-brand within a family, it must produce specific evidence for that sub-brand (literal name, manufacturer URL, or sibling support). Absent that, the proposal is downgraded to parent-only and flagged.

This closes the PEHA-vs-Esser case (both Honeywell): the proposal must cite why it's Esser specifically, not just any Honeywell sub-brand.

### P10 — Decision Helper, Not Truth Layer

This pipeline's outputs are enrichment decisions, written only to:
- `downloads/evidence/evidence_<pn>.json` (the pipeline's working data)
- `correction_journal.jsonl` (audit log)
- `review_bucket/**` (pending human decisions)

No writes to Core DB, `rev_*`, `stg_*`, or any adapter (InSales/Shopware/Ozon/WB). No promotion path from this pipeline to Core exists; Core remains the source of truth per `docs/PROJECT_DNA.md` §5b.

The `review_bucket apply` CLI mutates only the three filesystem artifacts above. Explicitly documented in the CLI's `--help` and enforced by a test that grep-checks for forbidden imports (`sqlalchemy`, `requests.post`, etc.).

---

## 3. Components

### 3.1 `scripts/pipeline_v2/evidence_pack.py`
Pydantic model `EvidencePack` with: raw evidence, computed provenance per-field (tier + timestamp), parsed URL domains, cached sibling index for the SKU, derived `dr_source_urls` list. Schema version 1.0. No writes to evidence files.

### 3.2 `scripts/pipeline_v2/trust_hierarchy.py`
Pure functions: `tier_of(evidence_pack, field_path) -> Tier`, `effective_trust(tier, age_months) -> float`, `resolve_proposal(evidence_pack, proposal) -> HierarchyResult`. Stateless.

### 3.3 `config/url_brand_oracle.json` + `scripts/pipeline_v2/url_oracle.py`
30 manufacturer domains + 20 distributor hints. Python loader compiles regex at startup, provides `evaluate(urls, pn, proposed_brand) -> Verdict`.

### 3.4 `config/subbrand_registry.json` + loader in evidence_pack
Parent → subbrand map. Seeded from project memory (`project_brand_distribution`, `brand_registry.json`).

### 3.5 `config/series_patterns.json` + `scripts/pipeline_v2/sibling_gate.py`
Series regex → `SiblingCheck`. Pure.

### 3.6 `scripts/pipeline_v2/correction_journal.py`
Append-only JSONL. `write(entry)`, `revert_correction(correction_id)`, `batch_rollback(since_ts)`. Uses `fsync` per entry. Content-addressed idempotency (same inputs → same `correction_id` → skip write).

### 3.7 `scripts/pipeline_v2/brand_correction_gate.py`
P5 orchestrator. Takes `EvidencePack`, invokes Stage-1 LLM (with structured prompt), runs Gates A-F, writes to journal, returns `CorrectionOutcome`.

### 3.8 Generalized gates, scope-limited
- `ean_correction_gate.py` — checks datasheet EAN vs current vs DR sources for consistency; no trust hierarchy needed (EAN is either right or wrong), only P1 evidence pack + P6 journal.
- `specs_correction_gate.py` — datasheet T2a canonical; merges non-conflicting fields, flags conflicts to review.
- `category_correction_gate.py` — uses `dr_category` + classifier. Trust hierarchy simplified (single-tier).

**NOT in v1.2:** description correction (semantic similarity, different paradigm), photo selection (OCR + embeddings, separate design).

### 3.9 `docs/TRUST_HIERARCHY.md`
Per-field tier assignment reference, filled during Phase B.

### 3.10 Review bucket CLI + Telegram digest
`scripts/pipeline_v2/review_bucket.py`: `list`, `apply`, `digest`. Telegram delivery via existing `orchestrator/biretarus_bot.py` channel `@bireta_code_bot`.

---

## 4. Implementation Phases (batch-split per R1 standard)

Preconditions before **any** phase starts:
- R1 Start Gate green
- Owner authorization recorded (this plan ≠ Stage 8.1; explicit written approval required per DNA §1c)
- Baseline precision measured on hold-out (see §5)

Each phase is a single policy surface per `R1_PHASE_A_BATCH_EXECUTION_STANDARD_v1_0.md`.

**Phase A — Canonicalize (split into A1-A4, 4 days total)**
- A1 (1d): `evidence_pack.py` + unit tests + schema version 1.0
- A2 (1d): `correction_journal.py` + unit tests (append-only invariant, revert round-trip, idempotency collision)
- A3 (0.5d): retrofit `_validate_brand_changes.py` to use evidence_pack + journal
- A4 (1.5d): hold-out sample construction (see §5) + baseline precision measurement

**Phase B — Rule Engines (split into B1-B4, 7 days total)**
- B1 (2d): `trust_hierarchy.py` + freshness decay + consensus lift tests
- B2 (1.5d): `url_oracle.py` + 200-URL golden dataset hand-labeled by owner
- B3 (1.5d): `sibling_gate.py` + `series_patterns.json` + tests per series pattern
- B4 (2d): `subbrand_registry.json` + Gate E within-family disambiguation + tests

**Phase C — Brand Gate (5 days)**
- C1 (2d): `brand_correction_gate.py` + shadow mode (no writes, journal only)
- C2 (1d): review bucket CLI + Telegram digest hook
- C3 (2d): external AUDITOR pass evaluates gate precision on hold-out; if ≥ 95% → promote to write-enabled; if < 95% → apply §5 exit clause

**Phase D — Generalization (3 weeks)**
- D1 (1w): EAN gate
- D2 (1w): specs gate  
- D3 (1w): category gate
- Each includes its own shadow run + AUDITOR pass.

**Phase E — Training data pipeline (opportunistic, non-critical-path)**
- Trigger-based silver labeling (§ P8)
- Fine-tune attempt only at ≥500 gold pairs per field type

**Realistic total wall time:** 5-6 weeks. Comfortable buffer.

---

## 5. Success Criteria and Validation Protocol

### Hold-out construction (stratified, 50 SKUs)

From 374 evidence files, select a stratified sample that no one reviewed during design:

- 15 Honeywell direct (no sub-brand)
- 10 Honeywell sub-brands: 2 Esser + 2 Sperian + 2 Notifier + 2 PEHA + 2 Howard Leight
- 10 non-Honeywell brands: Dell (2) + HP (1) + ABB (2) + Phoenix Contact (2) + DKC (2) + Weidmüller (1)
- 10 T4-legacy only (no T1-DR populated)
- 5 with conflicting T1-URL vs T1-DR (harder cases)

Owner hand-labels correct brand for each. Stored at `tests/pipeline_v2/holdout_brand_50.json`. Never used during design; only during §5 evaluation and Phase C AUDITOR pass.

### Success Criteria

1. **Precision (primary, blocking):** ≥ 95% of applied corrections match hold-out labels. Measured by external AUDITOR, not by gate code.
2. **Incident regression:** parametrized pytest over the 19 incident reverts → all blocked/correctly classified. Shipped with Step 1, maintained here.
3. **Auditability:** 100% of corrections have journal entry with reversible patch + ≥1 citation.
4. **No tier regression:** T-H and T1-URL values never overwritten by proposal without explicit override path.

Coverage (% auto-applied vs review) is reported informationally. No hard target. Optimizing coverage caused the original incident.

### 93% Plateau Exit Clause

If after 2 tuning iterations shadow precision is < 95%:
- **Option α:** raise auto-apply threshold from 0.85 to 0.90, push more borderline to review. Reduces coverage, preserves precision.
- **Option β:** accept 93% with residual risk documented in `docs/TRUST_HIERARCHY.md`, journal a POLICY_VIOLATION entry per SKU that ships below threshold.
- **Option γ:** park the gate, keep Step 1 guard + manual review only.

Owner selects α/β/γ; decision recorded in `docs/autopilot/STATE.md`.

### Operational SLIs (measured post-ship, non-blocking)

- Median age of pending review bucket items < 14 days
- < 5% of silver pairs reverted within 180 days
- Journal size growth < 10 MB / month

---

## 6. Remaining open questions (2)

**Q-FRESH.** Staleness threshold 180 days for URL Oracle `last_verified`: correct, or should it be 365 days for manufacturer domains (they're stable)? Current pick: 180.

**Q-ARCHIVE.** `review_bucket/archive/` retention: infinite (feeds training) vs hard cap at 1000 per field type to avoid repo bloat? Current pick: infinite, but move to separate location outside main repo (`d:/BIRETOS/audit_archive/`).

All other questions are closed. See v1.1 §6 for the decided ones.

---

## 7. What this plan is not

- Not a replacement for Core DB ownership of truth
- Not automated brand discovery (new brands only via review bucket approval)
- Not photo or description correction (separate design, separate doc)
- Not Stage 8.1 governance expansion (requires separate owner authorization if reclassified)
- Not a second AUDITOR (§5 precision evaluation is done by the external AUDITOR role per CLAUDE.md)

---

## 8. §9 Guard / Override Contradiction — Resolved

v1.1 had Step 1 `t1_brand_guard.should_skip_brand_autofix` blocking any SKU with T1 populated AND a new gate claiming it can override T1 via multi-source consensus. These contradict.

Resolution:

- **Guard remains in the OLD code path.** `_auto_fix_from_audit.py` keeps the guard unchanged. This protects all non-v1.2 code paths from regressing.
- **New `brand_correction_gate.py` is NOT guarded.** The gate has its own logic including the P2 stale-T1 override. The gate's first Gate B check enforces trust hierarchy; the override path in §2 is the sanctioned way to overrule T1-DR.
- **At the boundary:** old `_auto_fix_from_audit.py` is deprecated after Phase C ships. Until deprecation, guard remains first line of defense; after, the gate replaces it.
- **Regression protection:** the gate's own test suite includes the same 19-incident parametrized test. If any gate change lets a wrong brand through, test fails.

Concretely: `brand_correction_gate.py` imports from `t1_brand_guard` only to **inspect T1 state** (read-only utility), not to short-circuit the decision.

---

## 9. Pre-flight Checklist (before Phase A)

- [ ] R1 Start Gate green (Iron Fence 5.5.1-5.5.3 stable, CI green, branch protection on)
- [ ] Owner written authorization for this track (not Stage 8.1)
- [ ] Hold-out 50 SKUs constructed per §5; owner-labeled; stored at `tests/pipeline_v2/holdout_brand_50.json`
- [ ] Baseline precision measured on hold-out (CURRENT pipeline before v1.2 changes)
- [ ] `config/url_brand_oracle.json` seeded with 30 manufacturer domains
- [ ] `config/subbrand_registry.json` seeded
- [ ] `config/series_patterns.json` seeded with ≥6 patterns
- [ ] Golden URL dataset (200 URLs) hand-labeled by owner
- [ ] Archive policy decided (Q-ARCHIVE)
- [ ] Staleness policy decided (Q-FRESH)
- [ ] Cost ceiling for Stage-1 LLM calls across 374 SKUs estimated and approved

---

## 10. Test Strategy

Required test files before Phase C ships (critique #3: currently only 1/6 exists):

| File                              | Covers                                                        | Phase |
|-----------------------------------|---------------------------------------------------------------|-------|
| test_t1_brand_guard.py (exists)   | Step 1 hotfix; 19 incident regression                         | done  |
| test_evidence_pack.py             | Loader, provenance assignment, schema version                 | A1    |
| test_correction_journal.py        | Append-only, revert round-trip, idempotency collision         | A2    |
| test_trust_hierarchy.py           | Tier table, freshness decay, consensus lift, override path    | B1    |
| test_url_oracle.py                | Manufacturer vs distributor, stale >180d, regex matching      | B2    |
| test_sibling_gate.py              | <3 siblings abstain, 80% threshold, T2b+ filter               | B3    |
| test_subbrand_registry.py         | Parent→sub preservation, within-family disambiguation         | B4    |
| test_brand_correction_gate.py     | End-to-end on 19 incidents + 41 T1-resolvable + 5 adversarial | C1    |

---

## 11. Risk Classification

Per `CLAUDE.md`: plan is **🟡 SEMI** (new Tier-3 surface, no Core touch, no `rev_*` mutation). Current stage: ARCHITECT post-CRITIC (three rounds of AI audit completed and applied as v1 → v1.1 → v1.2). Next stage: PLANNER, then BUILDER (not jumping directly to BUILDER).

---

## 12. Audit trail

Previous versions and their resolutions:

- **v1 (2026-04-17 early).** Rejected by critique #2: overscoped relative to the actual bug. 3-AI critique log at `_scratchpad/llm_pipeline_plan_critiques.md`. Decision doc at `docs/LLM_CORRECTION_PIPELINE_DECISION.md`.
- **v1.1 (2026-04-17 mid).** Rejected by 3-AI audit: 5 blockers (Gate F threshold undefined, T0 phantom tier, P5 formula symbolic, §9 guard/override contradiction, self-AUDITOR violation) plus ~15 architectural/governance/engineering defects. Audit at `_scratchpad/llm_pipeline_v1_1_ai_audit.md`.
- **v1.2 (this doc).** All 5 blockers resolved:
  1. Gate F threshold = 0.85 apply / 0.70 tiebreaker / < 0.70 review (§2 P5)
  2. T0 removed; hierarchy explicit at T-H through T5 (§2 P2)
  3. All P5 sub-scores formally defined with abstention renormalization (§2 P5)
  4. §9 guard vs override resolved: guard on old path only, gate is unguarded with its own logic (§8)
  5. External AUDITOR pass for precision evaluation in Phase C3 (§4)
  Plus: R1 Phase A Batch Standard respected via A1-A4 split; DNA §7 items 5+9 added; P8 silver is trigger-based not calendar; P9 disambiguates within family; hold-out stratified; 93% plateau exit clause; Telegram digest replaces non-existent SMTP.

---

*End of v1.2. External peer reviewers: please focus on §2 P5 confidence formula edge cases, §2 P2 freshness decay curve, §4 phase timing realism, §5 hold-out stratification adequacy.*
