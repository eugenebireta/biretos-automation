# AI-Audit v0.5 — Improvement Proposal

**Status:** PROPOSAL — pending owner approval before patching CLAUDE.md §AI-AUDIT + `docs/prompt_library/roles/`.
**Authored:** 2026-04-18
**Trigger:** Real-task comparison between internal AI-Audit (R1+R2 with Claude Sonnet/Haiku + Gemini Flash) and external 3-chat audit (Gemini chat + ChatGPT + Claude chat aggregator) on a CORE-DML amnesty task. External audit produced higher-quality output that cited `docs/PROJECT_DNA.md §7 pattern #9` verbatim, identified atomic-publish bug missed by internal, and named concrete missing directories (`scripts/`, `orchestrator/`, `workers/`). Internal audit failed root-cause synthesis, missed two real bugs, and treated 6 DML tickets uniformly despite one being D4 Financial.

---

## Summary

External 3-chat audit outperformed internal AI-Audit on the same bundle. Root cause: **internal agents are sandboxed from codebase** (bundle-only context), **lack DNA/MASTER_PLAN prelude**, **don't enforce root-cause synthesis**, and **escalation trigger is too narrow**. This proposal patches 9 gaps grouped by impact × effort.

**Non-goals:** preserve R1 parallel-isolation invariant, keep ADVOCATE/CHALLENGER/SECOND_OPINION core roles, hold cost budget at ~$0.12–0.18 per audit. No change to trigger semantics (explicit owner trigger only).

---

## Gap Analysis (9 items)

### 1. Read-access to codebase — **BLOCKING STRUCTURAL GAP**
**Current:** ADVOCATE and SECOND_OPINION use Agent tool which *has* Read/Grep, but role prompts don't instruct usage. CHALLENGER (Gemini via `ai_audit/gemini_call.py`) is a one-shot API call with zero file access.
**Gap:** Agents judge by text-vibes, not by cited policy. External chat AIs got their DNA citations because owner pasted DNA chunks manually. Internal agents couldn't.
**Fix:**
- In `docs/prompt_library/roles/ADVOCATE.md`, `CRITIC.md`, `AUDITOR.md`: add mandatory "Before verdict, use Read on: `docs/PROJECT_DNA.md`, `docs/MASTER_PLAN_v1_9_2.md`, and Grep the affected scope. Cite specific §N or file:line."
- For Gemini CHALLENGER: pre-bake relevant DNA excerpts into the `--system` prompt via a pre-processor that scans bundle for keywords (CORE/tier-3/reconciliation/DML → extracts matching §§ from DNA) and prepends to system prompt.
- Bundle assembly step (§AI-AUDIT step 1) adds `relevant_docs: list[str]` — owner or pre-processor names files. All agents Read them.

### 2. Root-cause synthesis in R2 — **STRUCTURAL PROMPT GAP**
**Current:** R2 debate prompt asks each agent to respond to the other two anonymized auditors. No instruction to zoom-out.
**Gap:** Agents treat N concerns as N independent items. External auditor #3 reformulated 4 concerns as one symptom ("data lineage blackout") by asking the synthesis question.
**Fix:** Add to each R2 role prompt: "After responding to the other auditors, answer one additional question: **Do these concerns share a single root cause? If yes, name it in ≤20 words and cite which concerns are symptoms. If no, state why they are genuinely independent.**"

### 3. Concrete-example requirement — **OUTPUT FORMATTING GAP**
**Current:** Prompts say "конкретика, не воды". Agents interpret loosely ("grep may miss" counts as concrete).
**Gap:** Abstract warnings are non-actionable. External auditor named 3 directories with DNA §8 reference.
**Fix:** In role templates require: "Every concern must include at least one of: (a) N ≥ 2 concrete filenames or directories, (b) a specific DNA §N / MASTER_PLAN section cite, (c) a reproducible command (grep/python call). Vague concerns will be downgraded by the arbiter."

### 4. Cost-decision / unknown-identification — **REASONING GAP**
**Current:** Final recommendation from each R2 agent skips cost-of-being-wrong analysis and doesn't name unknowns that would flip the answer.
**Gap:** External auditor #3: "A+ vs B depends on whether unified rebuild is expensive (Haiku calls) or deterministic (3-way mapping). Brief has no figure — choice is guesswork." Internal agents skipped this entirely.
**Fix:** Add required output section in R2 format: `unknowns_that_would_flip_verdict: list[str]` — each agent names 1–3 concrete unknowns whose answer would flip their APPROVE→REJECT or vice-versa. Arbiter uses these to decide if NEEDS_INFO is warranted.

### 5. Risk-class tagging (D1–D5) — **MISSING CONTEXT INJECTION**
**Current:** `MASTER_PLAN_v1_9_2.md` defines DECISION_CLASSES D1–D5 (D4 = Financial). Bundle doesn't surface this. Agents treat all tickets uniformly.
**Gap:** Uniform amnesty for CORE-DML-04 (INSERT on invoice/payment) is impossible under D4 rules — a fact internal agents missed because they didn't have D-class context.
**Fix:** Bundle assembly adds `decision_class: D1..D5 | mixed` as mandatory field. If `mixed` (e.g. 6 tickets of different classes), bundle includes per-item class breakdown. Role prompts require: "If decision_class is D4/D5, consider amnesty/shortcuts invalid by default — state explicit DNA override needed."

### 6. Meta-check for 5th concern — **STRUCTURAL BLIND SPOT**
**Current:** ADVOCATE steelmans (minimizes concerns), CHALLENGER focuses on biggest concern, SECOND_OPINION runs checklist. Structural bias: a concern that *subsumes* several surface concerns but isn't itself surfaced can be missed by all three.
**Gap:** External auditor found "data lineage blackout" precisely because pasting all 3 chat outputs + asking Claude-chat to synthesize surfaced the umbrella concern. My R2 has no analogous step.
**Fix:** Add mandatory mini-phase after R2, before arbiter: single agent (Haiku) reads all R1+R2 output with prompt: "Name one concern that subsumes two or more raised concerns, or one concern that none of the auditors raised but is obvious in aggregate. If none, say 'none — the field is covered.'"

### 7. Escalation trigger too narrow — **POLICY GAP**
**Current:** Opus escalation triggers only on "superficial/contradictory answers without substance". Quality disagreement (ADVOCATE flip, unanimous REJECT) is not a trigger.
**Gap:** The cases where external-chat Claude aggregator added the most value were exactly these — structured disagreement among cheap auditors that a stronger model could synthesize.
**Fix:** Expand §AI-AUDIT escalation triggers:
- R2 unanimous REJECT → Opus pass.
- ADVOCATE flips APPROVE→REVISE/REJECT → Opus pass.
- R2 verdicts span APPROVE + REJECT (no middle) → Opus pass.
- D4/D5 risk_class + non-unanimous → Opus pass.
In all cases, still confirm with owner before paying ~$1.50 for Opus call.

### 8. External-by-default for durability claims — **NEW POLICY**
**Current:** External audit is manual fallback. Internal is default.
**Gap:** For architectural/"forever" claims (FROZEN FILES, PINNED API, durability invariants), internal audit's cost savings aren't worth the quality risk. Owner's manual external flow is ~2 minutes and already achieves the better result.
**Fix:** Add to §AI-AUDIT: "If the decision-under-audit touches `docs/PROJECT_DNA.md §3 (Frozen Files)`, `§4 (Pinned API)`, `§5 (Absolute Prohibitions)`, or uses words 'forever/irreversible/architectural invariant' — internal audit runs AS USUAL but owner is prompted: 'This claim touches durability. Copy the bundle to 3 external chats (Gemini/ChatGPT/Claude) and paste 3 verdicts back? [y/n]'. If owner says yes, arbiter waits for external verdicts before final recommendation."

### 9. LINEAGE-TRACER role for data pipelines — **MISSING SPECIALIST**
**Current:** Three generic roles (ADVOCATE/CHALLENGER/SECOND_OPINION) work on all topic types.
**Gap:** For data-pipeline topics (the failing case: "249 records dropped to 0 over weeks"), a specialist role that *traces output fields back through transformations* produces higher-signal findings than a generic critic.
**Fix:** Add new role in `docs/prompt_library/roles/LINEAGE_TRACER.md`. Invoked conditionally when bundle contains: `topic_type: data_pipeline | etl | ingest | data_drift | data_loss`. Replaces SECOND_OPINION for that class. Prompt template:
> "For each output field in the claim, trace back: which step writes it, which upstream inputs it depends on, at which point it could silently drop to null/empty. List blind spots in the data lineage. If the claim is about data loss, name the specific transformation where loss could occur, and how to verify (SQL or grep)."

---

## Priority Matrix

| # | Gap | Impact | Effort | Order |
|---|---|---|---|---|
| 1 | Read-access to codebase | HIGH | MEDIUM (role prompts + pre-processor) | 1 |
| 7 | Escalation trigger expansion | HIGH | LOW (policy text) | 2 |
| 5 | Risk-class tagging (D1-D5) | MEDIUM | LOW (bundle field + prompt) | 3 |
| 8 | External-by-default for durability | MEDIUM | ZERO (policy only) | 4 |
| 2 | Root-cause synthesis in R2 | MEDIUM | LOW (prompt line) | 5 |
| 6 | Meta-check 5th concern | MEDIUM | LOW (new mini-phase) | 5 |
| 9 | LINEAGE-TRACER role | MEDIUM | MEDIUM (new template + router) | 5 |
| 3 | Concrete example requirement | LOW | LOW (output format) | 7 |
| 4 | Cost-decision / unknowns | LOW | LOW (output format) | 7 |

---

## Non-Goals (do NOT change)

- **R1 parallel-isolation invariant.** Three R1 auditors still run in isolation — no seeing each other. Anti-conformity intact.
- **ADVOCATE / CHALLENGER / SECOND_OPINION core identities.** These remain; LINEAGE-TRACER is conditional substitute for SECOND_OPINION only.
- **Cost budget ceiling.** Remain at ~$0.12–0.18 default; ~$1.50 with Opus escalation.
- **Explicit-trigger-only semantics.** AI-Audit still fires only on explicit owner trigger. Never automatic on every decision.
- **External audit remains OPTIONAL for non-durability.** #8 adds a prompt for durability claims; doesn't mandate external for every audit.

---

## Implementation Plan (after owner approval)

1. **Patch `CLAUDE.md §AI-AUDIT`** with new escalation triggers (#7), durability-external prompt (#8), risk-class requirement (#5).
2. **Patch `docs/prompt_library/roles/`:**
   - `ADVOCATE.md`, `CRITIC.md`, `AUDITOR.md`: add Read/Grep mandate (#1), concrete-example requirement (#3), unknowns section (#4), root-cause question for R2 (#2).
   - Create `LINEAGE_TRACER.md` (#9).
3. **Write `ai_audit/bundle_builder.py`** helper that:
   - Accepts raw bundle + scope hints.
   - Scans bundle text for keywords → pulls matching DNA/MASTER_PLAN §§ into `relevant_docs_excerpts`.
   - Auto-tags `decision_class` based on keywords (DML + reconciliation → D4, frozen file mention → D5, etc.).
   - Outputs enriched bundle JSON for both Claude agents and Gemini call.
4. **Add meta-check mini-phase to AI-Audit procedure** — one more Agent call after R2, before arbiter (#6).
5. **Arbiter instruction update** — integrate unknowns-list (#4) and root-cause synthesis (#2) into final verdict.

**Each step is a separate commit.** Steps 1-2 are prompt/policy, LOW risk. Step 3 is new code, LOW risk. Steps 4-5 touch the AI-Audit runtime contract, SEMI risk (affects future audits of CORE work). Recommend step 3 also runs a self-audit on the failing case to verify it would now produce a non-inconclusive verdict.

---

## Validation (acceptance criterion)

After implementation, re-run AI-Audit on the original failing case (CORE-DML amnesty). Acceptance = audit must:
- Cite at least one specific `docs/PROJECT_DNA.md §N` reference.
- Flag CORE-DML-04 as D4 Financial with amnesty-invalid verdict.
- Either independently identify the "data lineage blackout" umbrella concern OR the meta-check mini-phase (#6) surfaces it.
- Give a final verdict that is NOT inconclusive (APPROVE / REVISE / REJECT, not NEEDS_INFO-equivalent).

If acceptance fails, escalate to Opus arbiter (#7 new trigger) as final safety net.

---

## Owner Decision

- [ ] APPROVE — proceed with step 1 (CLAUDE.md patch) as separate commit
- [ ] REVISE — specify which of the 9 to drop/modify
- [ ] REJECT — keep AI-Audit v0.4, use external-chat flow for high-stakes cases
