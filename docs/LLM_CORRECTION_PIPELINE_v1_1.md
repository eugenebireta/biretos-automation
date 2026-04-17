# LLM Correction Pipeline — Architecture Plan v1.1

**Status:** Draft, supersedes v1.
**Date:** 2026-04-17
**Owner:** Evgeny Bireta (biretos-automation)
**Precondition:** R1 Start Gate (Iron Fence stable, CI green, branch protection).
Until R1 green, only Step 1 hotfix (shipped in `b5dd281`) is active; Phases B-D wait.

## 0. What changed from v1

All deltas driven by 3 AI critiques (see `_scratchpad/llm_pipeline_plan_critiques.md`)
and empirical check that T1-alone resolves 41/55 incident SKUs:

| Area | v1 | v1.1 |
|------|----|------|
| Scope | brand + EAN + specs + category + photo + description | **brand + EAN + specs + category only.** Photo and description deferred (different paradigms: OCR/embeddings). |
| Trust tiers | Flat T0-T5 | T1 and T2 each **split by provenance** (human / URL / DR; official-PDF / third-party-PDF). T-human added above all. Freshness decay >180d. |
| URL Oracle | Near-authoritative | **Strong signal, not final verdict.** Requires source role + exact PN match + no contradiction from stronger tier. Allowlist with `last_verified`. |
| Sibling gate | Authoritative decider (60%) | **Veto/review only**, never decides. 80% threshold + min 3 siblings + T0-T2 brands only (T4 excluded). |
| Confidence | LLM self-assessed | **Computed** from (citations × tier × URL agreement × sibling agreement). LLM self-confidence dropped as gate. |
| Stage 2 validator | Optional LLM call | **Rule-only Python.** LLM escalation only for rule-engine ties. |
| Counterfactual reasoning | Open question | **Mandatory** in Stage 1 prompt (`rejected_alternatives[]`). |
| Sub-brand preservation | Not addressed | New P9: if evidence contains known sub-brand (Esser/Sperian/Notifier/PEHA), proposal must keep it. |
| Rollback | Ad-hoc script | **First-class** — `correction_journal.py` with append-only log + `revert_correction()` API. |
| Success criteria | 95% on same 55 SKUs used for design | **Hold-out ≥50 SKU** mandatory. Precision = primary KPI. Coverage = secondary. No "≥80% auto-decided" target. |
| Phase timing | 8 days total | 3-4 weeks realistic; each phase ×2. |
| DNA compliance | Implicit | Explicit — trace_id, idempotency_key, dry-run, reversible patch manifest on every mutation. |
| Truth layer stance | Ambiguous | Explicit disclaimer: **decision helper for enrichment only, NOT second truth layer.** Core DB remains owner of truth. |
| Review bucket | Never auto-expire | **30-day SLA**, then `review_bucket/archive/` (not deleted, feeds future training). Cluster-size triage. |

## 1. Problem statement (unchanged from v1 §1)

Root-cause analysis unchanged — see `docs/LLM_CORRECTION_PIPELINE_v1.md §1`.
Six architectural defects in `_auto_fix_from_audit.py`, confirmed by
empirical check: 55/55 incident SKUs had T1 populated, T1-alone resolves 41/55.
Step 1 hotfix `b5dd281` closes the acute bleed; v1.1 is defense-in-depth.

## 2. Design Principles

### P1 — Evidence-First Contract (unchanged)
Machine-built `EvidencePack` only. Callers cannot hand-pick fields.

### P2 — Trust Hierarchy (refined)

| Tier | Source                                              | Trust | Notes |
|------|-----------------------------------------------------|-------|-------|
| T-H  | Human-approved value (`review_bucket` → approved)   | 1.00  | Highest; sticky. |
| T1-URL | Exact PN match + manufacturer-domain URL in DR sources | 0.95  | e.g. `peha.de/products/820511` |
| T1-DR | `structured_identity.confirmed_manufacturer` (DR extraction) + `exact_title_pn_match` | 0.90  | Weakens to 0.85 if only `confirmed_manufacturer` without exact match. |
| T2a  | Datasheet parse where PDF came from manufacturer URL | 0.88  | `from_datasheet.*` with `datasheet_source_type == "official"` |
| T2b  | Datasheet parse from third-party PDF                 | 0.75  | e.g. distributor aggregator PDF |
| T3   | DR narrative (`deep_research.description`, `key_findings`) | 0.70  | Text, not structured |
| T4   | Legacy top-level fields (`brand`, `subbrand`)        | 0.50  | Pre-enrichment imports |
| T5   | LLM inference without grounding                      | 0.30  | Never authoritative |

Resolution rules:
- **Freshness decay:** tier value × max(0.6, 1 − months_since_verified/24). Stale T1-DR (>24mo) can be overridden by fresh multi-source consensus.
- **Consensus lift:** 2+ tiers of ≥T2 agreeing raises effective trust to 0.97.
- **Override path:** if 3 independent T1-URL/T2a sources contradict T1-DR → T1-DR goes to `review_bucket`, does not block. Prevents stale-data lock.

### P3 — URL Brand Oracle (refined)

Format (`config/url_brand_oracle.json`):
```json
{
  "esser-by-honeywell.(com|de|eu)": {
    "brand": "Esser (Honeywell)",
    "role": "manufacturer",
    "last_verified": "2026-04-10"
  },
  "walde.ee": {
    "brand_hint_only": true,
    "comment": "multi-brand distributor; URL path may hint brand but does not certify"
  }
}
```
- Authoritative ONLY when: `role == "manufacturer"` AND exact PN in URL path AND `last_verified` < 180 days AND no higher-tier contradiction.
- Distributor URLs are **hint_only** — feed into Stage 1 prompt as context, never gate the decision.
- Seed: curate ~30 top domains from `config/seed_source_trust.json`. Auto-discovery feeds candidates to review bucket, never self-promotes.

### P4 — Sibling Consistency (refined: veto-only)

Sibling gate **never decides brand**. It only:
- Vetoes a proposal that conflicts with sibling consensus.
- Flags SKU for review if sibling inconsistency is high.

Rules:
- Require **min 3 siblings** (smaller = result ignored).
- Consensus threshold: **80%** of T0-T2 brands (T4 legacy excluded).
- If proposal disagrees with ≥80% T0-T2 sibling brands → proposal rejected → SKU to review bucket.

Series patterns seeded: `FX\d+`, `HVAC\w+C\d`, `3240\d+`, `NE-\w+`, `P[0-9]{4}\w*`, `U[0-9]{4}\w*`, `PCD\d\.\w+`, `FX\d+\.\d+R?`.

### P5 — Two-Stage Correction Protocol (refined)

**Stage 1 (Propose, 1 LLM call):** Prompt includes full EvidencePack + sibling brands. LLM must output:
```json
{
  "proposed_brand": "...",
  "evidence_citations": [{"path": "structured_identity.confirmed_manufacturer", "value": "Esser"}],
  "rejected_alternatives": [{"brand": "OBO Bettermann", "why_rejected": "no evidence for it; URL domain contradicts"}],
  "sub_brand_preserved": true | false | "n/a"
}
```

**Stage 2 (Validate, pure Python):**
- Gate A: ≥1 evidence citation required.
- Gate B: Proposal consistent with Trust Hierarchy (P2) — no lower-tier override of higher tier without consensus lift.
- Gate C: URL Oracle (P3) passes or abstains (not contradicted).
- Gate D: Sibling veto (P4) passes.
- Gate E: Sub-brand preservation (P9) passes.
- Gate F: Computed confidence ≥ threshold.

**Computed confidence (P5 new):**
```
conf = 0.3 × citation_score
     + 0.3 × tier_score
     + 0.2 × url_oracle_agreement
     + 0.2 × sibling_agreement
```
No LLM self-reported confidence is used as a gate input.

Escalation: if Gates A-E pass but F is in [threshold-0.1, threshold] ambiguous band → second LLM call as tiebreaker. Otherwise pure Python.

### P6 — Review Bucket with SLA (refined)

Path: `downloads/staging/review_bucket/<pn>.json`

Lifecycle:
- Created on any gate failure or ambiguous confidence.
- Daily digest emailed to owner: cluster-size triage (top 10 clusters by proposed_brand × series).
- **30-day staleness** → moved to `review_bucket/archive/` (not deleted). Archive feeds training data.
- High-value triage: SKUs tagged by price or sales expectation get priority flag.

### P7 — Observability (refined)

Every correction attempt writes to `correction_journal.jsonl`:
```json
{
  "correction_id": "uuid",
  "trace_id": "uuid",
  "idempotency_key": "sha256(pn|stage|inputs_hash)",
  "pn": "FX808313",
  "stage": "brand_correction",
  "before": {...},
  "proposed": {...},
  "gates": {"A": true, "B": true, "C": true, "D": false, "E": true, "F_conf": 0.78},
  "decision": "review",
  "reversible_patch": {"path": "$.brand", "op": "replace", "from": "Esser", "to": "OBO"},
  "cost_usd": 0.004,
  "model": "sonnet-4.5",
  "ts": "2026-04-17T10:00:00Z"
}
```

Append-only. `revert_correction(correction_id)` replays the reverse patch.

### P8 — Training Data by Default (refined with critique #1 Q)

**Critique #1 asked:** how to prevent bad proposals contaminating fine-tune ground truth?

Answer — three-tier labeling:
1. **Gold** — human-approved in review bucket. Used for fine-tune.
2. **Silver** — applied correction that passed all gates AND not reverted in 60 days. Used with lower weight.
3. **Rejected** — any correction that failed a gate, or was reverted. Used as **negative examples** (what NOT to propose), not as positive labels.

`downloads/training_v2/validation_decisions.jsonl` stores all three, tagged. Fine-tune pipeline reads only gold + silver as positives.

### P9 — Sub-brand Preservation (new)

Known sub-brand registry (`config/subbrand_registry.json`):
```json
{
  "Honeywell": ["Esser", "Sperian", "Notifier", "PEHA", "Howard Leight", "Saia-Burgess", "Distech"],
  "Schneider": ["Merten", "Berker"],
  ...
}
```

Gate E rejects proposals where:
- Current `brand` or `subbrand` names a registered sub-brand, AND
- Proposed brand names only the parent, AND
- Evidence still supports the sub-brand context.

(Prevents LLM bias toward famous parent brands.)

### P10 — Decision Helper, Not Truth Layer (new, from critique #3)

This pipeline's outputs are **enrichment decisions**, not ground truth.
Core DB remains source of truth per `docs/PROJECT_DNA.md`. No `rev_*` table
writes from correction gates. Correction results live only in evidence
JSON files and journal; promotion to Core happens via existing approved
ingestion paths.

## 3. Components to Build

### 3.1 `scripts/pipeline_v2/evidence_pack.py`
Single authoritative loader. Pydantic, versioned. Parsed URL domains, sibling index, provenance tags.

### 3.2 `scripts/pipeline_v2/trust_hierarchy.py`
Applies P2 rules. Returns `{brand, effective_tier, supporting_citations[], freshness_factor}`.

### 3.3 `config/url_brand_oracle.json`
30 curated manufacturer domains + distributor hints. `last_verified` date per entry.

### 3.4 `config/subbrand_registry.json`
Parent → sub-brands map. Seeded from project_brand_distribution memory and brand_registry.json.

### 3.5 `scripts/pipeline_v2/sibling_gate.py`
Pure function — no state, no LLM. Returns veto/pass + sibling consensus metadata.

### 3.6 `scripts/pipeline_v2/correction_journal.py`
Append-only JSONL journal + `revert_correction(correction_id)` API + batch rollback by time/criterion.

### 3.7 `scripts/pipeline_v2/brand_correction_gate.py`
P5 orchestrator. Replaces auto-fix brand path. Stage 1 (1 LLM call, counterfactual prompt) + Stage 2 (rule-only Python).

### 3.8 Generalized gates (v1.1 scope)
- `ean_correction_gate.py` — simpler than brand; EAN check is consistency-only (datasheet vs current vs sources).
- `specs_correction_gate.py` — datasheet T2a canonical per `feedback_datasheet_is_king_for_specs`.
- `category_correction_gate.py` — uses `dr_category` + classifier.

**Explicitly NOT v1.1:** photo, description. Different paradigms (OCR + embeddings for photo; semantic similarity for description). Separate design docs required.

### 3.9 `docs/TRUST_HIERARCHY.md`
Living reference listing every evidence field and its tier assignment.

### 3.10 Review bucket CLI
- `review_bucket list --by cluster` — triage view.
- `review_bucket apply <pn> <decision>` — owner approves/rejects.
- `review_bucket digest` — daily email payload.

## 4. Implementation Phases

R1 Start Gate is a precondition. Nothing below Phase A starts until
Iron Fence 5.5.1-5.5.3 stable, CI green on grep-checks, branch protection
configured.

### Phase A — Canonicalize (3 days)
- `evidence_pack.py` + tests
- `correction_journal.py` + tests
- Integrate into existing `_validate_brand_changes.py` (retrofit)
- Hold-out sample construction: 50 SKUs never seen by Pipeline v1 designers

### Phase B — Rule Engines (5-7 days)
- `trust_hierarchy.py`, `sibling_gate.py`, `url_brand_oracle.json`, `subbrand_registry.json` + unit test golden dataset (1000 known URLs)
- Freshness decay tested
- Override path tested

### Phase C — Brand Gate (4-5 days)
- `brand_correction_gate.py` with P5 protocol
- Shadow-mode against hold-out 50 SKUs → precision ≥95% blocking criterion
- If shadow precision <95% → stop, tune, re-shadow before ship
- Review bucket CLI + digest

### Phase D — Generalize (2 weeks)
- `ean_correction_gate.py`
- `specs_correction_gate.py`
- `category_correction_gate.py`
- Each gets its own shadow run on hold-out
- `docs/TRUST_HIERARCHY.md` filled in

### Phase E — Training Data (ongoing, not critical path)
- Three-tier labeling per P8
- Fine-tune attempt only when ≥500 gold pairs per field type
- Local validator is optional optimization, not v1.1 requirement

**Total v1.1 realistic:** 4-5 weeks wall time (×2 of v1 estimate, per critique consensus).

## 5. Success Criteria

1. **Precision (primary):** ≥95% of applied corrections agree with human ground truth on **hold-out 50 SKUs** (never used for design). Blocking criterion.
2. **Coverage (secondary, informative only):** report % auto-applied vs review. No hard target — optimizing coverage over precision caused the original incident.
3. **Auditability:** 100% of corrections have a journal entry with reversible patch + evidence citations.
4. **No Trust Hierarchy regression:** no T1-H or T1-URL values ever overwritten by LLM proposal without explicit override path.
5. **Review bucket non-starvation:** median age of pending items <14 days after 30 days of operation.
6. **Incident regression test:** parametrized pytest on all 19 2026-04-16 incident SKUs must pass (same as current hotfix).

## 6. Open Questions

Most v1 questions resolved. Remaining:

**Q1 (open).** URL Oracle decay: is 180-day stale threshold right? Manufacturer
sites are stable but do occasionally rename/reorg. Maybe 365d?

**Q4 (open).** Review bucket archive policy: 30-day active + infinite archive,
or hard-cap archive at N=1000 per field to avoid disk bloat?

All other v1 open questions (Q2, Q3, Q5, Q6, Q7, Q8) are decided:
- Q2 sibling threshold: **80% + min 3 + T0-T2 only**
- Q3 T2 rigidity: **split T2a/T2b by extraction origin; freshness decay**
- Q5 language: **confidence modifier, not gate**
- Q6 counterfactual reasoning: **mandatory in Stage 1 prompt**
- Q7 photo generalization: **deferred to separate design**
- Q8 Stage 2 cost: **rule-only Python; LLM only for ties**

## 7. Explicit Non-Goals

- Replacing DR or Core Backbone pipelines
- Writing to Core DB (`rev_*` tables) from gates
- Automated brand discovery (new brands added only via review bucket)
- Photo or description correction (separate design)
- Local model fine-tune as a v1.1 deliverable (Phase E is opportunistic)
- Cross-pipeline identity resolution (that's `identity_gate.py` territory)

## 8. Pre-flight Checklist

Before Phase A begins:
- [ ] R1 Start Gate green (Iron Fence stable, CI green, branch protection on)
- [ ] Hold-out 50 SKUs selected; manual brand ground truth recorded
- [ ] `config/url_brand_oracle.json` seeded with 30 curated domains (manual review)
- [ ] `config/subbrand_registry.json` seeded
- [ ] Golden URL dataset (1000 known URLs → known brand) prepared for oracle unit tests
- [ ] Archive policy decided (Q4)
- [ ] Staleness policy decided (Q1)

## 9. Step 1 Hotfix Relationship

Step 1 T1 Sync Guard (commit `b5dd281`) remains active through all phases.
v1.1 does not remove the guard. The guard becomes redundant once the full
brand_correction_gate is live in shadow → production, but we keep the guard
as defense-in-depth belt-and-suspenders.

Phase A integration: guard wraps the gate's entry, so even if a future
gate change accidentally re-introduces the class of bug, the guard still
blocks the bad path.

---

*End of v1.1. Peer reviewers: focus on §2 P2 tier assignments, §2 P5
computed confidence formula, §5 hold-out size, §6 remaining Q1/Q4.*
