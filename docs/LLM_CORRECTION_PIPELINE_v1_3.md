# LLM Correction Pipeline — Architecture Plan v1.3

**Status:** Draft for external peer review. Supersedes v1.2 (which had an arithmetic error in §2 P5 rationale that cascaded into wrong thresholds).
**Date:** 2026-04-17
**Owner:** Evgeny Bireta (biretos-automation; product catalog enrichment)
**Precondition:** R1 Start Gate green (Iron Fence 5.5.1-5.5.3 stable, CI green, branch protection configured). Until R1 green, only Step 1 hotfix (commit `b5dd281`) is live.

---

## 0. Context for external reviewers

### The system

Enrichment pipeline for a product catalog: ~370 SKUs (industrial: Honeywell, Esser, PEHA, Dell, ABB, Phoenix Contact, DKC, Weidmüller, etc.) targeting InSales + Ozon + Wildberries marketplaces. Each SKU has a per-file JSON evidence record at `downloads/evidence/evidence_<pn>.json` (~40 fields per file, populated by Deep Research via GPT, Gemini PDF parsing, distributor scraping, Excel import).

### The triggering incident (2026-04-16)

An auto-fix pass sent Claude Sonnet a 4-field slice of evidence (`pn`, `current_brand`, `seed_name`, `datasheet_title`) and wrote the LLM's brand proposals to evidence files. 55 SKUs were modified. A post-hoc validator later reverted **19 as wrong**. Canonical example: FX808313 (Honeywell/Esser fire-alarm battery housing) was relabeled "OBO Bettermann" — despite the evidence file already containing `structured_identity.confirmed_manufacturer = "Esser"` and a DR source URL `walde.ee/en/fire-alarm-systems/esser-by-honeywell/flexes`. The LLM never saw those fields.

### Empirical anchor

All 55 incident SKUs had `structured_identity.confirmed_manufacturer` populated. Naively trusted, that one field correctly resolves **41/55 = 75%**. Remaining 14 are parent/sub-brand ambiguities (Esser↔Honeywell, PEHA↔Esser, Cisco↔Honeywell, etc.).

### Step 1 hotfix — already shipped

Commit `b5dd281`: 120-line Python module `scripts/pipeline_v2/t1_brand_guard.py` that blocks the auto-fix code path from proposing brand changes when `confirmed_manufacturer` is populated. 24 tests pass, including parametrized regression on all 19 incident SKUs.

### What this plan is

Defense in depth on top of Step 1. LLM *proposes*, deterministic Python *validates*, review bucket holds ambiguous cases. All outputs are **enrichment decisions**, never truth (see §10).

### Revision history

- v1.0 — Rejected: overscoped, built a cathedral for a latch problem (3-critique log at `_scratchpad/llm_pipeline_plan_critiques.md`).
- v1.1 — Rejected by 3-AI audit: 5 blockers (Gate F threshold undefined; T0 phantom tier; P5 formula symbolic; §9 guard/override contradiction; self-AUDITOR violation). Audit at `_scratchpad/llm_pipeline_v1_1_ai_audit.md`.
- v1.2 — Rejected by 3 external AI reviewers: arithmetic error in rationale (wrote "0.34 renormalized" when correct value is 0.565 — the 0.85 threshold was calibrated against that wrong number); auto-apply rate claim 41/55 unreachable (one abstaining external signal dropped strong T1-DR to tiebreaker); hold-out n=50 statistically insufficient (Wilson CI [86.5%, 99.5%] can't distinguish 93% from 95%); Gate E soft-fail overwrote sub-brand; citation stacking via low-quality citations; silent consensus risk from renormalization; guard-vs-gate handshake during Phase A-C unspecified; single freshness curve wrong for B2B industrial. Audit at `_scratchpad/llm_pipeline_v1_2_external_audit.md`.
- **v1.3 (this doc)** — All v1.2 blockers resolved (see §12 delta table).

---

## 1. Root cause (unchanged)

Six architectural defects in the incident pass `_auto_fix_from_audit.py`:
1. **Evidence Blind Spot.** 4 of 40+ fields sent to LLM.
2. **Trust Hierarchy Inversion.** DR-grounded `confirmed_manufacturer` treated as equal to legacy top-level `brand`.
3. **No URL Semantic Parsing.** `esser-by-honeywell.com` in DR sources never extracted.
4. **No Sibling Consistency Check.** FX-series siblings correctly Esser; FX808313 left as outlier.
5. **No Confidence Gate.** LLM self-assessed confidence applied without threshold.
6. **Single-Pass, No Validation.** Stage-1 proposal written straight to evidence.

---

## 2. Design principles

### P1 — Evidence-First Contract
Every LLM-touching operation reads a machine-built `EvidencePack` from the single loader `scripts/pipeline_v2/evidence_pack.py`. Callers cannot hand-pick fields. Provenance tags are **computed at load time** from existing evidence fields; source files are never mutated for provenance.

### P2 — Trust Hierarchy

Every value is assigned one of the following tiers:

| Tier     | Source                                                                      | Base trust | Verification timestamp field              |
|----------|-----------------------------------------------------------------------------|:----------:|-------------------------------------------|
| T-H      | Human-approved via `review_bucket/approved/`                                | 1.00       | `approved_at`                             |
| T1-URL   | Manufacturer-domain URL + exact PN in URL path + oracle role="manufacturer" | 0.96       | `last_verified` (oracle config)           |
| T1-DR    | `structured_identity.confirmed_manufacturer` + at least one `exact_*_pn_match` flag | 0.92 | derived from `brand_source` date    |
| T2a      | `from_datasheet.*` parsed from PDF on manufacturer domain                   | 0.85       | `from_datasheet.merged_at`                |
| T1-DR-w  | `confirmed_manufacturer` alone, no exact_match                              | 0.80       | same as T1-DR                             |
| T2b      | `from_datasheet.*` parsed from third-party PDF                              | 0.70       | same as T2a                               |
| T3       | `deep_research.description` / `key_findings` (text)                         | 0.60       | `deep_research.merge_ts`                  |
| T4       | Legacy top-level `brand`/`subbrand` (pre-enrichment import)                 | 0.40       | `generated_at` (file-level)               |
| T5       | LLM inference without grounding                                             | 0.20       | now()                                     |

Strict ordering, enforced by unit test: `T-H > T1-URL > T1-DR > T2a > T1-DR-w > T2b > T3 > T4 > T5`.

**No tier is "T0".** v1.1 had a phantom T0 reference; removed.

#### Per-tier freshness decay (CHANGED from v1.2 single curve)

Decay divisors vary by source stability:

```python
DECAY_HALFLIFE = {
    "T-H":      None,  # no decay
    "T1-URL":   None,  # own 180d re-verification cycle covers it
    "T1-DR":    12,    # web research ages fastest
    "T1-DR-w":  12,
    "T2a":      60,    # official datasheet = physical specs, rarely change
    "T2b":      48,
    "T3":       18,
    "T4":       36,
    "T5":       None,  # already lowest, no further decay
}

def effective_trust(tier, months_old):
    halflife = DECAY_HALFLIFE[tier]
    if halflife is None:
        return BASE[tier]
    return BASE[tier] * (0.5 + 0.5 * exp(-months_old / halflife))
```

Rationale: datasheets describe physics (tier T2a halflife 60mo ≈ industrial component lifetime); web research ages in 1-2 years as companies rebrand/acquire; legacy imports are low-base-trust so decay matters less. Values anchored against critic feedback on B2B industrial domain characteristics.

#### Consensus lift (tightened)

```
effective = top_fresh_trust
if ≥2 independent agreeing citations AND at least one is T2a or T1-URL:
    effective = min(0.98, top_fresh_trust * 1.05)
# never exceeds fresh T1-URL unless lift cites T1-URL itself
```

Two T2b citations cannot exceed fresh T1-URL (the v1.1/v1.2 bug).

#### Override path for stale T1-DR

If `top_fresh_trust` is T1-DR older than 24 months AND ≥2 fresh (age <6mo) T1-URL or T2a citations disagree with it: T1-DR moves to `review_bucket/stale_contradiction/` and is excluded from this decision. Override records `idempotency_key` that includes the fresh-citation set hash — repeated batch runs produce identical results.

### P3 — URL Brand Oracle

File: `config/url_brand_oracle.json`.
- Entries with `role: "manufacturer"` rate T1-URL only if ALL: domain regex matches, PN literally in URL path, `last_verified` <180 days, no higher-tier contradiction.
- Entries with `brand_hint_only: true` feed Stage-1 prompt context but don't gate.
- Seed: 30 curated manufacturer domains hand-labeled by owner. Golden dataset 200 URLs (reduced from v1.1's 1000 per critique).
- Auto-discovered candidates go to `review_bucket/oracle_candidates/`, never self-promote.

### P4 — Sibling Consistency Gate (veto only)

Series patterns in `config/series_patterns.json`. Gate returns decision only:

```python
siblings = find_siblings(pn, patterns)
effective = [s for s in siblings if sibling_tier(s) >= T2b]  # no T4 legacy
if len(effective) < 3:
    return abstain("fewer than 3 T2b+ siblings")

majority, fraction = mode_with_fraction(effective)
if fraction >= 0.80:
    return agree(fraction) if proposed == majority else veto(f"{fraction:.0%} say {majority}")
if fraction >= 0.60:
    return flag_review("mixed family")
return abstain("no clear majority")
```

Siblings never decide the brand. Their only negative power is `veto` (Gate D failure); their positive contribution is as a weighted input to confidence (P5). Threshold 80% (not 60%); minimum 3 **effective** siblings (T2b+ only, to avoid T4 legacy bootstrap).

### P5 — Two-Stage Correction Protocol (REWRITTEN from v1.2)

#### Stage 1 — Propose (1 LLM call)

Prompt includes full `EvidencePack` + sibling brands + URL oracle matches + relevant subbrand registry. LLM must return JSON:

```json
{
  "proposed_brand": "<name> or 'needs_review'",
  "evidence_citations": [
    {"path": "structured_identity.confirmed_manufacturer", "value": "Esser", "supports_brand": "Esser"}
  ],
  "rejected_alternatives": [
    {"brand": "OBO Bettermann", "why_rejected": "no evidence path supports this"}
  ],
  "sub_brand_preserved": true | false | "n/a"
}
```

Each citation must name `path`, `value` at that path in pack, and `supports_brand` claim. Rejected alternatives must include a reason.

#### Stage 2 — Validate (pure Python; no LLM unless tiebreaker)

Gates A-F, all deterministic:

- **Gate A — Citation presence and integrity.**
  ```
  A_pass = len(citations) ≥ 1
         AND every cited path exists in pack
         AND every cited value matches pack[path]
  ```

- **Gate B — Trust hierarchy respected; no collision.** (CHANGED from v1.2 — adds coherence + T4 exclusion + collision check)
  ```
  # Exclude T4 (legacy top-level brand/subbrand) from citation weight
  eligible = [c for c in citations if tier_of(c.path) != "T4"]
  if not eligible:
      B_pass = False; reason = "all citations are T4 legacy (target, not evidence)"
  else:
      top_trust = max(effective_trust(tier_of(c.path), age_of(c.path)) for c in eligible)
      top_cites = [c for c in eligible if effective_trust(...) == top_trust]

      # Coherence: all top-tier values must be consistent with proposed brand
      # (either equal or parent/sub-brand of proposed per subbrand_registry)
      for c in top_cites:
          if c.value not brand-consistent-with proposed_brand:
              B_pass = False; reason = f"citation at {c.path}={c.value} contradicts proposed {proposed_brand}"
              break
      # Collision: top_cites disagree among themselves → explicit fail
      if not all same_brand_family(c.value for c in top_cites):
          B_pass = False; reason = "top-tier citations disagree (tier collision)"
      else:
          B_pass = True
  ```

- **Gate C — URL Oracle.**
  ```
  oracle = evaluate(pack.dr_source_urls, pn, proposed_brand)
  # returns "agree" | "disagree" | "abstain"
  C_pass = oracle != "disagree"
  ```

- **Gate D — Sibling veto.**
  ```
  D_pass = sibling_check.decision != "veto"
  ```

- **Gate E — Sub-brand preservation.** (CHANGED from v1.2 — soft-fail goes to review, not parent downgrade)
  ```
  existing_sub = detect_subbrand(pack)  # from current brand/subbrand fields or evidence text
  if existing_sub:
      # Proposal must name the sub-brand or its direct parent with sub-brand context preserved
      E_pass = (proposed == existing_sub) OR
               (parent_of(existing_sub) == proposed AND proposal explicitly acknowledges sub-brand in response)

  if proposes_new_subbrand X (not in pack):
      # Require specific evidence for X: literal X in any evidence text,
      # OR manufacturer URL for X in DR sources, OR ≥2 T2b+ siblings with X
      if no such evidence:
          E_pass = False; route = "review_bucket/insufficient_subbrand_evidence/"
          # NEVER silently downgrade to parent (that was v1.2 regression)
  ```

- **Gate F — Computed confidence ≥ threshold.**

  Component formulas:
  ```python
  # Each returns [0.0, 1.0] or "abstain"

  # Citation score: count of NON-T4 citations (coherent ones, Gate B already filtered)
  citation_score = min(1.0, N_non_T4_citations / 3)

  # Tier score: effective trust of top non-T4 citation
  tier_score = max(effective_trust(tier, age) for each non-T4 citation)

  # URL Oracle verdict
  url_oracle_score = 1.0 if agree, 0.0 if disagree, "abstain" if neither

  # Sibling verdict
  if sibling.decision == "agree":       sibling_score = sibling.fraction  # 0.80..1.00
  elif sibling.decision == "flag_review": sibling_score = 0.5
  elif sibling.decision == "veto":      sibling_score = 0.0
  else:                                 sibling_score = "abstain"

  weights = {"citation": 0.3, "tier": 0.3, "url": 0.2, "sibling": 0.2}
  active = {k: v for k, v in scores.items() if v != "abstain"}
  total_weight = sum(weights[k] for k in active)
  confidence = sum(weights[k] * active[k] for k in active) / total_weight

  # Abstention cap (NEW in v1.3): if both external signals abstain,
  # text-only citations cannot artificially inflate past this cap.
  if url_oracle_score == "abstain" and sibling_score == "abstain":
      confidence = min(confidence, 0.78)
  ```

  **Thresholds (recalibrated from v1.2 with correct arithmetic):**
  ```
  confidence ≥ 0.80  → auto-apply
  0.65 ≤ confidence < 0.80 → LLM tiebreaker (1 additional call, votes apply/review)
  confidence < 0.65  → review bucket
  ```

  Sensitivity table (all with Gate A-E passing):

  | Scenario                                       | Confidence | Outcome    |
  |------------------------------------------------|-----------:|------------|
  | T1-URL fresh + both agree                      |      0.988 | apply      |
  | T1-DR exact + both agree                       |      0.877 | apply      |
  | T1-DR exact + one external abstain             |      0.846 | apply      |
  | T1-DR exact + both abstain (capped)            |      0.780 | tiebreaker |
  | T2a + both agree                               |      0.856 | apply      |
  | T1-DR weak + both agree                        |      0.841 | apply      |
  | T2b×3 stacking attack (both abstain, capped)   |      0.780 | tiebreaker |
  | T1-DR exact + URL disagree                     |         — | Gate C fails → review |
  | T1-DR exact + sibling veto                     |         — | Gate D fails → review |

  This calibration is the main fix over v1.2. Every scenario's number was computed, not estimated.

**Decision matrix:**

| Gates A-E | Confidence | Outcome |
|:---------:|:----------:|---------|
| all pass  | ≥ 0.80     | apply   |
| all pass  | 0.65-0.80  | LLM tiebreaker |
| all pass  | < 0.65     | review  |
| any fail  | —          | review with `gate_failed` reason |

All outcomes log to `correction_journal.jsonl` BEFORE any evidence mutation.

### P6 — Review Bucket with SLA + explicit expiry journal

Path: `downloads/staging/review_bucket/{pending, approved, rejected, archive, stale_contradiction, insufficient_subbrand_evidence, oracle_candidates}/`

Lifecycle:
- Items in `pending/` → `approved/` or `rejected/` via CLI `review_bucket apply <correction_id> <decision>`
- Items older than **30 days in pending** → **move to `archive/` AND journal an explicit `decision: "expired"` entry** (critic #3: silent archive was silent failure — fixed). Archive feeds training data.
- Telegram digest (via existing `orchestrator/biretarus_bot.py`) sends daily: top 10 clusters by (proposed_brand × series) + counter of items aging past 21 days.
- No SMTP needed (critic #3).

Archive policy: **infinite retention**, cap only the active queue. Archive files moved outside main repo to `d:/BIRETOS/audit_archive/` to avoid repo bloat (per critic #1 Q-ARCHIVE answer).

### P7 — Observability, DNA §7 compliance

Journal entry at `downloads/staging/correction_journal.jsonl`:

```json
{
  "correction_id": "uuid4",
  "trace_id": "uuid4",
  "idempotency_key": "sha256(pn|stage|evidence_pack_hash|proposal_hash)",
  "pn": "FX808313",
  "stage": "brand_correction",
  "mode": "shadow" | "live",
  "before": {"brand": "Honeywell"},
  "proposed": {"brand": "Esser (Honeywell)"},
  "gates": {
    "A": {"pass": true, "n_citations": 2, "coherence_ok": true},
    "B": {"pass": true, "top_tier": "T1-DR", "top_tier_age_months": 5, "effective_trust": 0.88, "t4_excluded_count": 1, "collision": false},
    "C": {"pass": true, "oracle_verdict": "agree", "matched_domain": "esser-by-honeywell.de"},
    "D": {"pass": true, "sibling_decision": "agree", "fraction": 1.0, "reason": "5 FX-series siblings all Esser"},
    "E": {"pass": true, "subbrand_preserved": "Esser", "parent": "Honeywell"},
    "F": {
      "confidence": 0.91,
      "threshold_apply": 0.80,
      "threshold_tiebreak": 0.65,
      "abstention_cap_active": false,
      "components": {"citation": 0.67, "tier": 0.88, "url": 1.0, "sibling": 1.0}
    }
  },
  "decision": "apply" | "tiebreak" | "review" | "expired",
  "reversible_patch": {"path": "$.brand", "op": "replace", "from": "Honeywell", "to": "Esser (Honeywell)"},
  "cost_usd": 0.004,
  "model": "claude-sonnet-4-5",
  "ts": "2026-04-17T10:00:00Z",
  "error": null
}
```

**DNA §7 compliance (reviewer-corrected reference):**
- Item 1 `trace_id` ✓
- Item 2 `idempotency_key` — content-addressed; replay produces identical decision unless evidence changed
- Item 3 append-only JSONL, single `fsync` per entry (journal flush discipline)
- Item 4 **N/A** — no commit inside domain ops; pipeline is file-based, no DB
- Item 5 **Redaction**: `before/proposed` and citation `value` fields strip any substring matching `[A-Za-z0-9]{32,}` (32+ alphanumeric = likely token/key), unless the field is whitelisted as safe (e.g. `pn`, `brand`). Same applies to URLs in citations — query-string stripped before logging.
- Item 6 Every module has `if __name__ == "__main__"` CLI entry for isolation testing
- Item 7 Deterministic test per module (no live APIs in unit tests; LLM mocked)
- Item 8 ✓ (the journal)
- Item 9 **Error schema:** when any gate or LLM call raises:
  ```json
  "error": {
    "class": "TRANSIENT" | "PERMANENT" | "POLICY_VIOLATION",
    "severity": "WARNING" | "ERROR",
    "retriable": true | false,
    "message": "...",
    "where": "gate_B" | "llm_call" | ...
  }
  ```

`revert_correction(correction_id)` replays `reversible_patch` in reverse, appends a new journal entry (never rewrites history).

### P8 — Training data, trigger-based

Three tiers:
- **Gold.** Human-approved in `review_bucket/approved/`. Used as positive labels.
- **Silver.** Applied by gate AND all of:
  - Next enrichment pass re-audits the SKU and agrees, AND
  - No customer complaint in support ticket (Core DB `rev_*` tables) within 90 days, AND
  - No `revert_correction` within 180 days.
  Silver activates only after **all three triggers** fire. Weight 0.5 vs gold's 1.0.
- **Rejected.** Failed any gate, or reverted. Used only as negative labels (what NOT to propose).

File: `downloads/training_v2/validation_decisions.jsonl`. Fine-tune pipeline reads gold+silver only.

### P9 — Sub-brand preservation + within-family disambiguation

Registry at `config/subbrand_registry.json`:
```json
{"Honeywell": ["Esser","Sperian","Notifier","PEHA","Howard Leight","Saia-Burgess","Distech"],
 "Schneider": ["Merten","Berker"]}
```

Two rules:
1. **Preserve existing sub-brand.** If current `brand/subbrand` or evidence text contains a registered sub-brand, proposal must keep it (Gate E).
2. **Within-family disambiguation** (for same-parent sub-brands like Esser vs PEHA, both Honeywell): proposal naming sub-brand X of parent Y must cite specific evidence for X — (a) literal "X" or "by X" in evidence text, OR (b) manufacturer URL for X, OR (c) ≥2 T2b+ siblings with X. Absent that: Gate E fails, proposal → `review_bucket/insufficient_subbrand_evidence/`. **No silent downgrade to parent** (v1.2 regression).

### P10 — Decision Helper, Not Truth Layer

Pipeline outputs write only to:
- `downloads/evidence/evidence_<pn>.json` (pipeline working data)
- `correction_journal.jsonl` (audit log)
- `review_bucket/**` (human decision queue)

No Core DB writes. No `rev_*` / `stg_*` / `core/` table mutations. No adapter calls (InSales / Shopware / Ozon / WB). Enforced by test `test_no_forbidden_imports.py` that greps gate modules for `sqlalchemy`, `requests.post`, adapter module imports.

Core remains source of truth per `docs/PROJECT_DNA.md` §5b.

---

## 3. Components

### 3.1 `scripts/pipeline_v2/evidence_pack.py`
Pydantic model `EvidencePack v1.0`, canonical loader. Computes provenance at load time from raw evidence fields. Handles schema variations across 370 legacy files via **field-level defaults and missing-field fallbacks** — never mutates source JSON. Schema variations documented per-field with a `legacy_handler` note (critic #2 schema variation question). Exports: raw evidence, provenance-tagged fields, sibling index, `dr_source_urls`, `context_language` (for Stage-1 prompt anchoring).

### 3.2 `scripts/pipeline_v2/trust_hierarchy.py`
Pure functions: `tier_of(pack, path)`, `effective_trust(tier, age_months)`, `resolve_proposal(pack, proposal)`. Stateless. Per-tier decay divisors from §2 P2.

### 3.3 `config/url_brand_oracle.json` + `scripts/pipeline_v2/url_oracle.py`
~30 manufacturer entries + ~20 distributor hints. Compiled-regex loader. Unit-tested against 200-URL golden dataset.

### 3.4 `config/subbrand_registry.json` + loader
Parent → sub-brand map. Seeded from existing memory (`project_brand_distribution`, `brand_registry.json`).

### 3.5 `config/series_patterns.json` + `scripts/pipeline_v2/sibling_gate.py`
Pure function returning `SiblingCheck`.

### 3.6 `scripts/pipeline_v2/correction_journal.py`
Append-only JSONL. API: `write(entry)`, `revert_correction(correction_id)`, `batch_rollback(since_ts)`. Content-addressed idempotency — identical inputs → identical `correction_id` → no duplicate writes. Per-entry `fsync`.

### 3.7 `scripts/pipeline_v2/brand_correction_gate.py`
P5 orchestrator. Takes `EvidencePack`, runs Stage-1 LLM with structured prompt (includes `rejected_alternatives` requirement), runs Gates A-F, writes journal, returns `CorrectionOutcome`. **Never calls `t1_brand_guard` to short-circuit** (fixed from v1.2 §8 contradiction).

### 3.8 Generalized gates (scope-limited)
- `ean_correction_gate.py` — consistency check (datasheet vs current vs DR sources). Simpler than brand; no Trust Hierarchy needed.
- `specs_correction_gate.py` — datasheet T2a canonical per `feedback_datasheet_is_king_for_specs`; merges non-conflicting fields, conflicts → review.
- `category_correction_gate.py` — simplest; uses `dr_category` + classifier.

**Explicitly NOT in v1.3:** description correction (embedding similarity paradigm), photo selection (OCR + embeddings). Separate design docs required.

### 3.9 `docs/TRUST_HIERARCHY.md`
Per-field tier assignment reference, filled during Phase B.

### 3.10 Review bucket CLI + Telegram digest
`scripts/pipeline_v2/review_bucket.py`: `list`, `apply`, `digest`. Delivery via existing `biretarus_bot.py` Telegram channel.

---

## 4. Implementation Phases (realistic timing, batch-split)

Preconditions: R1 Start Gate green. Owner written authorization for this track (not Stage 8.1 expansion).

Each phase is one policy surface per `R1_PHASE_A_BATCH_EXECUTION_STANDARD_v1_0.md`.

**Phase A — Canonicalize (A1-A4 split, ~5 days total)**
- A1 (1d): `evidence_pack.py` + unit tests + schema version 1.0 + legacy-field fallbacks
- A2 (1d): `correction_journal.py` + unit tests (append-only, revert round-trip, idempotency collision)
- A3 (0.5d): retrofit `_validate_brand_changes.py` to use evidence_pack + journal
- A4 (**2.5d calendar**, ~10h owner labor): hold-out sample construction (150 SKUs — see §5) + baseline precision measurement

**Phase B — Rule Engines (B1-B4, ~9 days total)**
- B1 (2d): `trust_hierarchy.py` + per-tier decay + consensus lift + override path tests
- B2 (**3d calendar**, ~6h owner labor): `url_oracle.py` + 200-URL hand-labeled golden dataset
- B3 (1.5d): `sibling_gate.py` + `series_patterns.json` + per-pattern tests
- B4 (2.5d): `subbrand_registry.json` + Gate E within-family disambiguation + tests

**Phase C — Brand Gate (shadow-first, ~6 days total)**
- C1 (**3d**, +1d from v1.2 per critic #2): `brand_correction_gate.py` — wires LLM + evidence_pack + trust_hierarchy + oracle + sibling_gate + journal. **Runs in shadow mode only, no evidence writes.** Guard `t1_brand_guard` remains active on old path.
- C2 (1d): review bucket CLI + Telegram digest hook
- C3 (2d): **external AUDITOR pass** evaluates shadow-journal verdicts against hold-out. **Precision computed by AUDITOR role, not by gate code** (governance critic #2 of v1.1).
  - If precision ≥ 95% AND CI lower bound ≥ 90% → promote to write-enabled: same PR removes Step 1 guard and flips gate mode from shadow to live.
  - If below threshold → §5 exit clause.

**Tuning buffer: +3-5 days** if Phase C3 fails first try (v1.2 omitted this per critic #3).

**Phase D — Generalization (~3 weeks)**
- D1 (1w): EAN gate
- D2 (1w): specs gate
- D3 (1w): category gate
- Each gets own shadow run + AUDITOR pass.

**Phase E — Training data (opportunistic, not critical path)**
- Trigger-based silver labeling per P8.
- Fine-tune attempt only at ≥500 gold pairs per field type.

**Realistic total wall time: 7-8 weeks** (v1.2 said 5-6 — critic #3 pushed this to reality).

### Cost ceiling

- Stage-1 LLM per SKU: ~$0.004 Sonnet.
- Tiebreaker expected for ~20% of SKUs: +$0.004 × 0.2.
- Full brand pass 370 SKUs: ≈ $1.80.
- Across 4 gate types (brand/EAN/specs/category): ≈ $7.20 per full run.
- Development + shadow + regression prism: **~$50 total budget**.

Recorded in `downloads/autopilot/STATE.md` under `llm_correction_pipeline_dev_budget`.

---

## 5. Success Criteria and Validation Protocol

### Hold-out construction (stratified, n=150)

Critic #3: n=50 is statistically insufficient for 95% precision target (Wilson CI too wide to distinguish 93% from 95%). **v1.3 increases to n=150** with the following stratification:

| Stratum                                         | Count | Rationale |
|-------------------------------------------------|-------|-----------|
| Honeywell direct (no sub-brand)                 |    30 | main body of catalog |
| Honeywell sub-brands (5 per: Esser/Sperian/Notifier/PEHA/Howard Leight) | 25 | Gate E preservation |
| Non-Honeywell major brands (Dell/HP/ABB/Phoenix/DKC/Weidmüller/Saia-Burgess) | 30 | cross-brand |
| T4-legacy only (no T1-DR populated)             |    25 | incident class |
| Conflicting signals (T1-URL vs T1-DR disagree)  |    15 | override-path validation |
| Implicit sub-brand (sub-brand correct but not in evidence)  |    15 | disambiguation harder mode |
| Pathological / UNRESOLVABLE-candidates          |    10 | system robustness |

**Disjoint guarantee:** `holdout_150 ∩ incident_19 = ∅`. Documented in `tests/pipeline_v2/holdout_brand_150.json` header.

### Labeling protocol (NEW — addresses critic #3 labeling bias)

Option chosen: **owner labels hold-out BEFORE reading v1.3's P-rules**, with a separate spreadsheet. Labels time-stamped and committed before any Phase B coding begins. If owner cannot pre-label (timeline constraint), second human labeler (anyone outside the pipeline design conversation) resolves disputes.

### Success Criteria

1. **Precision (primary, blocking):** Point estimate ≥ 95% AND Wilson CI lower bound ≥ 90%, measured by external AUDITOR on hold-out 150. With n=150 and 143/150 correct, CI lower bound ≈ 91.2% → passes. Verified by critic #3 statistical reasoning.
2. **Incident regression:** Parametrized pytest on all 19 incident SKUs — must pass. Shipped already with Step 1, maintained here.
3. **Auditability:** 100% of corrections have journal entry with reversible patch + ≥1 non-T4 citation.
4. **No tier regression:** T-H / T1-URL values never overwritten by proposal without the explicit P2 override path being triggered.
5. **Coverage (secondary, informative):** report `% auto-applied` vs `% tiebreaker` vs `% review`. No hard target. Critic #3 explicitly warned against "≥80% auto-decided" as optimization target (caused the original incident).

### 93% Plateau Exit Clause

If after 2 tuning iterations shadow precision is below threshold:
- **α:** Raise auto-apply threshold from 0.80 to 0.85 (tighten) — reduces coverage, preserves precision.
- **β:** Accept documented lower precision; log POLICY_VIOLATION entry per shipped SKU below threshold.
- **γ:** Park the gate; keep Step 1 guard + manual review only.

Owner selects. Decision recorded in `docs/autopilot/STATE.md`.

### Operational SLIs (post-ship, non-blocking)

- Median age of pending review bucket items < 14 days
- < 5% silver pairs reverted within 180 days
- Journal size growth < 10 MB / month
- Pending items >21 days: count < 5 (Telegram digest)

---

## 6. Remaining open questions (2)

**Q-FRESH.** T1-URL `last_verified` hard threshold: 180d triggers re-verification, downgrades to hint-only if not re-verified. Critic #1 suggested 365d hard + soft decay starting at 180d. v1.3 picks: **180d re-verify trigger + tier-specific decay per §2 P2 (already accounts for B2B industrial)**. Open for reviewer input.

**Q-ARCHIVE.** v1.3 picks: **infinite archive at `d:/BIRETOS/audit_archive/`** (outside repo), active queue capped only. Open for reviewer input.

---

## 7. Non-goals (unchanged)

- Not replacing DR or Core Backbone
- Not writing to Core `rev_*` tables
- Not automated brand discovery (new brands only via review bucket approval)
- Not photo or description correction (separate design)
- Not Stage 8.1 governance expansion
- Not self-AUDITOR (§5 precision computed externally)

---

## 8. §9 Guard / Override handshake (EXPLICIT from v1.2)

Critic #3 flagged that during Phase A-C both guard and new gate are active. Resolution:

- **Throughout Phase A, B, C1, C2:** Step 1 guard (`t1_brand_guard.should_skip_brand_autofix`) remains active on old path `_auto_fix_from_audit.py`. New `brand_correction_gate.py` runs in **shadow mode only** — writes to journal, never to evidence. Zero write conflict.
- **At Phase C3 promotion (same PR):** `_auto_fix_from_audit.py` is deleted, `t1_brand_guard.py` retained only as a utility library for evidence inspection, `brand_correction_gate.py` mode flag flips from shadow to live, first live batch runs.
- **Regression protection:** gate's test suite includes the parametrized 19-incident SKU test. Any gate change allowing a wrong brand through → test fails → PR blocked.

Concretely: `brand_correction_gate.py` imports from `t1_brand_guard` for **read-only T1 inspection only**, never to short-circuit decisions.

---

## 9. Pre-flight checklist (before Phase A)

- [ ] R1 Start Gate green (Iron Fence 5.5.1-5.5.3 stable, CI green, branch protection)
- [ ] Owner written authorization for this track (not Stage 8.1)
- [ ] Hold-out 150 SKUs constructed + owner pre-labeled (pre-design or second labeler) + `tests/pipeline_v2/holdout_brand_150.json` committed
- [ ] Disjoint check: holdout ∩ incident_19 = ∅ verified by script
- [ ] Baseline precision on hold-out measured BEFORE v1.3 changes (baseline estimate, then delta)
- [ ] `config/url_brand_oracle.json` seeded 30 manufacturer domains
- [ ] `config/subbrand_registry.json` seeded
- [ ] `config/series_patterns.json` seeded (≥6 patterns)
- [ ] Golden URL dataset (200) hand-labeled by owner
- [ ] Archive policy (Q-ARCHIVE) confirmed
- [ ] Staleness policy (Q-FRESH) confirmed
- [ ] Dev budget $50 recorded in STATE.md

---

## 10. Test strategy

Required test files (currently 1/8 exists):

| File                                | Covers                                                      | Phase |
|-------------------------------------|-------------------------------------------------------------|-------|
| test_t1_brand_guard.py (exists)     | Step 1 hotfix; 19 incident regression                       | done  |
| test_evidence_pack.py               | Loader, provenance assignment, schema variation handling    | A1    |
| test_correction_journal.py          | Append-only, revert round-trip, idempotency collision       | A2    |
| test_trust_hierarchy.py             | Per-tier decay, consensus lift (no T2b>T1-URL), override path | B1    |
| test_url_oracle.py                  | Manufacturer vs distributor, stale >180d, regex, 200-URL golden | B2    |
| test_sibling_gate.py                | <3 abstain, 80% threshold, T2b+ filter, T4 exclusion        | B3    |
| test_subbrand_registry.py           | Parent→sub preservation, within-family disambiguation        | B4    |
| test_brand_correction_gate.py       | End-to-end: 19 incidents + stratified hold-out sample + 10 adversarial | C1 |
| test_no_forbidden_imports.py        | P10 — gate modules don't import Core DB / adapter libraries  | C1   |

---

## 11. Risk classification

Per `CLAUDE.md`: plan is **🟡 SEMI** (new Tier-3 surface, no Core touch, no `rev_*` mutation). Current stage: ARCHITECT post multiple CRITIC rounds (three internal audits + three external audits of v1.2). Next stage: PLANNER, then BUILDER.

---

## 12. Delta from v1.2 (audit fixes)

| v1.2 issue                                              | v1.3 fix                                           | Where |
|---------------------------------------------------------|----------------------------------------------------|-------|
| Arithmetic error in rationale (0.34 instead of 0.565)   | Full sensitivity table with computed values       | §2 P5 table |
| Threshold 0.85 built on wrong math                      | Recalibrated to 0.80 apply / 0.65 tiebreak        | §2 P5 |
| Auto-apply drops to tiebreak when one external abstains | 0.80 apply now covers T1-DR-exact with one abstain | §2 P5 sensitivity |
| Silent Consensus Risk via renormalization               | Abstention cap 0.78 when both externals abstain    | §2 P5 |
| T2b×3 stacking attack achieves 0.85                      | Capped at 0.78 → tiebreak                          | §2 P5 |
| Citation stacking with low-quality citations            | Gate B excludes T4; Gate A requires value coherence; collision check | §2 P5 Gate A/B |
| Gate B `max()` non-determinism on equal tiers           | Explicit collision check: all top-tier values must agree | §2 P5 Gate B |
| Gate E soft-fail regresses sub-brand → parent           | Soft-fail → review_bucket/insufficient_subbrand_evidence/ | §2 P5 Gate E, §2 P9 |
| Single freshness curve wrong for B2B industrial         | Per-tier decay halflives (T2a=60mo, T1-DR=12mo, etc.) | §2 P2 |
| Hold-out n=50 statistically insufficient                | n=150 with Wilson CI lower bound ≥90% gate        | §5 |
| Hold-out 2 per sub-brand = pyl                          | 5 per sub-brand × 5 = 25; T4-legacy 25; adversarial 15 | §5 |
| Labeling bias (owner designs + labels)                  | Pre-design labels OR second labeler               | §5 |
| No disjoint guarantee from incident 19                  | Explicit `holdout ∩ incident = ∅` check            | §5 |
| §8 guard/override handshake unclear during A-C          | New gate shadow-only throughout A-C; flip + delete old in C3 PR | §8 |
| Review bucket 30-day archive = silent failure           | Journal `decision: "expired"` + 21-day counter in digest | §2 P6 |
| DNA §7 item 4 not addressed                             | Marked N/A with rationale                          | §2 P7 |
| Cost ceiling without number                             | ~$50 dev budget, $1.80 per full brand pass         | §4 |
| Phase A4 1.5d / B2 1.5d / C1 2d unrealistic             | A4=2.5d, B2=3d, C1=3d, +3-5d tuning buffer, total 7-8w | §4 |
| No tuning buffer after failed precision                 | Explicit 3-5d buffer in Phase C timing            | §4 |
| Schema variations across 370 legacy files unhandled     | `evidence_pack.py` legacy fallbacks at load time   | §3.1 |

All 7 blockers and 7 serious issues from external audit addressed.

---

*End of v1.3. External peer reviewers: please focus on §2 P5 sensitivity table (are the computed numbers correct?), §2 P2 per-tier decay halflife values (are they right for B2B industrial?), §5 n=150 stratification (sufficient for 95% claim?), §8 handshake protocol (any residual race conditions?).*
