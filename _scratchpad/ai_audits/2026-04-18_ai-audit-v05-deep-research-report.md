---
audit_id: 2026-04-18_ai-audit-v05-tier4
date: 2026-04-18
tier_used: 4
source: Claude Deep Research (claude.ai)
brief_ref: 2026-04-18_ai-audit-v05-deep-research-brief.md
executive_verdict: SOUND_WITH_EDGES
effort_total: 7-9 engineering days
cost_delta_per_audit: +$0.03 default / +$0.05 on D4/D5
---

# AI-Audit v0.5 Tier 4 Deep Research report

**Source:** Claude Deep Research returned by owner 2026-04-18.
**Scope:** Architecture critique of v0.5 against multi-LLM deliberation, calibration, and high-stakes-governance literature.

## Executive verdict: SOUND-WITH-EDGES

v0.5 is materially better than v0.4 (post-R1 discovery gate, pre-R1 arbiter numeric check, LINEAGE_TRACER, hard-abort on provider substitution). Four structural edges remain, each patchable:

1. Cross-provider independence weaker than architecture assumes (Kim et al. 2025 — 60% co-error on reasoning)
2. Bundle assembly = live indirect-prompt-injection surface (OWASP LLM01:2025)
3. Role prompts have asymmetric confabulation profile (Nemeth 2001, Sharma 2023)
4. Artifact schema insufficient for T+6mo forensic replay (Atil 2024)

## Top 5 vulnerabilities

| # | Title | Severity×Likelihood | Core patch |
|---|---|---|---|
| V1 | Correlated-errors across "diverse" providers | HIGH×HIGH | Patch 1: PRECEDENT_SCANNER role (historical near-miss injection) |
| V2 | Indirect prompt injection via auto-injected bundle excerpts | **CRITICAL×MEDIUM** | Patch 2: sanitization + delimiter discipline + `possible_injection_attempts` field |
| V3 | ADVOCATE confabulation + CHALLENGER over-reject asymmetry | MEDIUM×HIGH | Patches 3a-c: role prompt rewrites; 3d: arbiter downgrade for unverifiable concerns |
| V4 | Forensic replay impossible at T+6mo | HIGH×HIGH | Patch 8: extended artifact schema (hashes, system_fingerprint, tool log, semantic replay) |
| V5 | Modal-confidence collapse (7-anchor) destroys calibration | MEDIUM×VERY_HIGH | Patch 5a: verbal IPCC ladder; 5b: entropy/stdev monitor |

## Vulnerability NOT addressed in v0.5 (Deep Research answer to §3)

**V2 — Indirect prompt injection via auto-injected excerpts.** `bundle_builder.py` auto-inject is an adversarial-input channel. v0.5 pre-R1 sanity check verifies numeric correctness, role templates require concrete cites, but no layer treats bundle as adversarial input. OWASP LLM01 is #1 LLM risk for 2 consecutive editions.

## Cosmetic fix in v0.5 (Deep Research answer to §4)

**Anti-conformity R2 rule "change only on new argument" is counter-productive.** Liang et al. 2023 (Degeneration-of-Thought): once an agent commits R1, strict-novelty rule LOCKS IN initial errors. Patch 6: two-dimensional update with classes {new_evidence / new_argument / recalibration / identified_my_own_r1_error} — weight differently.

## Calibration recommendations (§6)

- **Primary IRR: Gwet's AC1, not Cohen/Fleiss κ** (prevalence-skewed APPROVE distribution → kappa paradox).
- ~500 audits for first pooled AC1 + ECE read.
- ~2,000 audits for per-class Brier stability.
- Horizon-stratified outcomes at T+7/T+30/T+90, blinded labeler (PROBAST).

## Governance durability (§7)

- Sonnet 4.5 snapshot risk window: **6-12 months** from 2026-04-18.
- Gemini 2.5 earliest shutdown: **2026-06-17** (~2 months).
- Current schema does NOT enable forensic replay. Patch 8 adds hashes, system_fingerprint, tool_log, semantic-replay anchor.

## Missing roles worth adding (§9)

- **PREMORTEM_PHASE** (Klein 2007) — for D3/D4/D5, between bundle and R1. ~$0.01/audit.
- **RED_TEAMER** (Nemeth 2001 authentic-dissent) — D4/D5 only, DIFFERENT model family than ADVOCATE+CHALLENGER. ~$0.05/audit on D4/D5.
- Stopping-rule monitor (Haybittle-Peto) — if R1 unanimous REJECT ≥"highly likely", short-circuit arbiter.

## Tier-4 abort rules (§8)

Skip Tier 4 even if trigger fires when: single canonical source exists / binary closed-ended / long-tail niche without RAG / legally-admissible output / no verifier for success criterion. Post-hoc citation-verification sweep required for D4/D5 outputs with >3 cites/1000 words.

## Full patch inventory

| # | Patch | File(s) | Effort | Runtime Δ | Priority |
|---|---|---|---|---|---|
| 2 | Injection sanitization + delimiter discipline | `bundle_builder.py`, roles, schema | 1 day | 0 | **CRITICAL** |
| 8 | Forensic replay schema | YAML frontmatter | 1-2 days | 0 | **CRITICAL** |
| 3a-c | ADVOCATE/CHALLENGER/SECOND_OPINION rewrites | `roles/*.md` | 0.5 day | 0 | **HIGH** |
| 5a-b | Verbal confidence ladder + modal collapse monitor | roles, `calibration_monitor.py` | 0.5 day | 0 | **HIGH** |
| 1 | PRECEDENT_SCANNER role | new role + `bundle_builder.py` | 0.5 day + corpus | +$0.02 | HIGH |
| 11 | PREMORTEM_PHASE | new role + `bundle_builder.py` | 2h | +$0.01 | HIGH |
| 9 | Snapshot-deprecation monitor + golden-set SOP | new script + docs | 2 days | 0 | MEDIUM |
| 6 | Two-dim R2 update rule | roles + arbiter | 2h | 0 | MEDIUM |
| 7 | Horizon-stratified outcome labeling + blinding | schema + UI | 1 day | 0 | MEDIUM |
| 10 | Tier-4 abort rules doc | new doc | 2h | 0 | MEDIUM |

Total: 7-9 engineering days. Runtime: +$0.03/audit default, +$0.05 D4/D5. Within v0.5 cost envelope.

## Open questions DR could not resolve (§10)

1. Sonnet-vs-Gemini residual independence on Biretos engineering tasks (seeded 30-case benchmark recommended).
2. Khan 2024 debate generalization (QuALITY → engineering decisions) unverified.
3. Anti-conformity rule's actual DoT-prevention rate.
4. Whether post-2023 sycophancy mitigation is effective on Sonnet 4.5 / Gemini 2.5.
5. Shumailov 2024 model-collapse drift — annual re-measurement of cross-provider correlation recommended.
6. Outcome-labeling confirmation bias even with Patch 7 blinding.

## Deep Research self-disclosed limits

- Correlated-errors apply to this audit (all subagents were Claude instances).
- 4 citations flagged with uncertainty (Towards Data Science summary, 2 post-cutoff arXiv, DeepHalluBench not peer-reviewed).
- Minority literature view: multi-agent debate doesn't reliably beat self-consistency + verifier at equal compute (Parrish 2022, Smit 2024). Patches are incremental per brief non-goal; v1.0 redesign should benchmark vs self-consistency baseline.

## Arbiter synthesis (me)

**Accept verdict: SOUND-WITH-EDGES.** Matches internal assessment. DR produced 3 genuinely novel findings we did NOT cover in v0.5:
1. **V2 prompt-injection surface** (critical, we didn't consider bundle as adversarial input)
2. **V5 modal-confidence collapse** (integer 1-10 ladder is structurally broken; IPCC verbal ladder is standard)
3. **Patch 6 anti-conformity rule is counter-productive** (Liang 2023 DoT — we had this wrong)

Cross-check against v0.5 non-goals: all patches compatible (R1 isolation preserved, core roles preserved, cost within envelope, explicit-trigger semantics preserved).

Recommended implementation order (requires owner approval):
- **Sprint A (critical, ~3 days):** Patch 2 + Patch 8 + Patches 3a-c
- **Sprint B (high, ~2 days):** Patches 5a-b + 1 + 11
- **Sprint C (medium, ~2 days):** Patches 9 + 6 + 7 + 10

Artifact saved to: `_scratchpad/ai_audits/2026-04-18_ai-audit-v05-deep-research-report.md`
