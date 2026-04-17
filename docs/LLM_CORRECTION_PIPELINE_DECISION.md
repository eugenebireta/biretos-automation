# Decision Log: Plan v1 → Action

**Status:** Plan v1 rejected as-is. MVP proceeds. v1.1 to follow.
**Date:** 2026-04-17
**Inputs:** 3 AI critiques + empirical check of incident data.

## Empirical ground truth

All 55 incident SKUs had `structured_identity.confirmed_manufacturer` (T1) populated.
T1 value alone correctly resolves **41/55 = 75%** of cases.
The remaining 14 are parent/sub-brand ambiguities (Esser↔Honeywell, PEHA↔Esser, Cisco↔Honeywell, Distech↔Honeywell).

→ Critique #2 was right: a single T1 guard would have prevented 75% of the incident at 20 lines of code. v1 plan built a 3-week cathedral to solve a problem that needed a latch.

## What all 3 critiques agree on

- Root-cause diagnosis (§1) is correct, keep as-is
- Stage 2 must be **rule-only Python**, not second LLM call (Q8)
- Counterfactual reasoning in Stage 1 prompt (Q6)
- Scope must shrink — photo/description don't fit the frame
- Rollback/audit trail is first-class, not ad-hoc
- Hold-out sample required; can't validate on design data

## Decision: 3-day MVP, then v1.1 for the rest

### MVP (ship this week, in order)

**Step 1 — T1 Sync Guard** (0.5 day)
- Rule: if `structured_identity.confirmed_manufacturer` filled AND `identity_confirmed=true` → **auto-fix does not propose brand for this SKU**. Instead, sync top-level `brand` to T1 value (deterministic, no LLM).
- Blocks 75% of incident class. Trivial to implement.
- Exception path: T1 empty/low-confidence → proceed to Step 3.

**Step 2 — `evidence_pack.py`** (1 day)
- Canonical loader; every LLM-touching script consumes this instead of hand-picked fields.
- Exports: typed Pydantic pack with all 40+ fields incl. parsed URL domains, sibling PNs, tier-tagged provenance.
- Covers general architectural defect #1 (Evidence Blind Spot) for all future pipeline steps, not just brand.

**Step 3 — URL Oracle minimal + Sibling veto** (1 day)
- Oracle: 20-30 curated domains from `seed_source_trust.json` (esser-by-honeywell, peha.de, obo.de, dkc.ru, phoenixcontact, weidmueller, notifier, dell.com, saia-burgess, etc.).
- NOT authoritative. Strong signal only.
- Sibling check as **veto/review flag**, never as decision maker (critique #3 — cannot be source of truth). Min 3 siblings, uses T0-T2 fields only.

**Step 4 — `correction_journal.py`** (0.5 day)
- Append-only JSONL: `{correction_id, pn, before, after, sources[], trace_id, ts, reversible_patch}`
- `revert_correction(correction_id)` API.
- Every evidence mutation passes through journal.

**Step 5 — Shadow mode + hold-out** (0.5 day)
- Run MVP against 50 never-before-reviewed SKUs; compare decisions to human verification.
- Block ship if precision <95%.

### v1.1 (after MVP, not before)

Plan to rewrite doc with these changes:

| §   | Change |
|-----|--------|
| 1 | Keep as-is (all critiques praise it) |
| 2 P2 | Split T1 into T1-Human / T1-URL / T1-DR. Split T2 by `extraction_method` (T2a official / T2b third-party). Add freshness decay (>180d → downgrade). Add T-human tier above all. |
| 2 P3 | URL Oracle = strong signal, NOT final verdict. Requires source role + exact PN match + no stronger contradiction. Allowlist with `last_verified` dates. |
| 2 P4 | Sibling gate: **veto/review only**, never authoritative. Threshold 80% + min 3 siblings + count only T0-T2 siblings (not T4 legacy). |
| 2 P5 | Confidence = **computed** function of (evidence citations × tier × URL agreement × sibling agreement). Drop LLM self-assessed confidence as gate. |
| 2 P5 | Stage 2 = rule-only Python. LLM escalation only for rule-engine ties. |
| 2 P9 | NEW: sub-brand preservation rule. If evidence contains known sub-brand (Esser, Sperian, Notifier, PEHA) — proposal MUST keep it or auto-fails. |
| 3 | Add `correction_journal.py` as core component. |
| 3.8 | **Scope v1.1: brand + EAN + specs + category only.** Remove photo and description. |
| 4 | All phase timings × 2 (B: 5-7d, C: 4-5d, D: 2w). |
| 5 | Add hold-out ≥50 SKU mandatory. Precision = primary KPI, coverage = secondary. Drop the "≥80% auto-decided" hard target (critique #3: dangerous optimization target). |
| 5 | Override mechanism: if 3 independent T0/T2 sources contradict T1 → T1 goes to review, does NOT block. |
| 6 | Close Q2, Q3, Q5, Q6, Q7, Q8 with decisions. Keep only Q1 (URL authority scope) and Q4 (review bucket SLA) open. |
| 7 | NEW: DNA compliance — trace_id, idempotency_key, dry-run, reversible patch manifest (mandatory from PROJECT_DNA §11). |
| 8 | NEW: "Decision helpers for enrichment only, NOT second truth layer" disclaimer. Core DB remains owner of truth. |
| 9 | NEW: Review bucket SLA — 30-day staleness → `review_bucket/archive/` (not deleted, feeds future training). Cluster-size triage. |
| 10 | NEW: R1 start gate precondition (Iron Fence stable, CI green, branch protection). Explicit blocker acknowledgement. |

### Deferred (NOT in v1.1, separate design later)

- Description/photo generalization (different paradigms — embedding similarity, OCR respectively)
- Training data pipeline Phase E
- Local validator fine-tune
- LLM Stage-2 validator

### Hard "never"

- Brand auto-fix without T1 guard
- Single-shot LLM → evidence without journal
- Declaring enrichment a truth layer

## Rationale for not doing v1.1 first

Three critiques took ~60 min to produce. A v1.1 doc takes ~2 hours. The MVP takes 3 days and closes 75%+ of the risk. Writing v1.1 before MVP delays the fix for zero incremental safety. v1.1 is needed for long-term defense in depth, and will be written while MVP is running in shadow mode.

## Outstanding questions for owner

Two questions only (rest converged across critiques):

**OQ1.** Should MVP ship only on T1 guard (Step 1) and defer Steps 2-4 until after shadow run? Faster to deploy. Less architectural value.

**OQ2.** Is R1 start gate (critique #3) currently open? If not, MVP Steps 2-4 may have to wait; Step 1 as hotfix can still ship.

## Next action

Pending owner decision on OQ1/OQ2:
- If "go full MVP" → Step 1 implementation starts.
- If "Step 1 only, hotfix mode" → T1 guard committed and shadow-tested, v1.1 doc paralleled.
