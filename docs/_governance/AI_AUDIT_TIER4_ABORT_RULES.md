# AI-Audit Tier 4 — Abort Rules

**Scope:** When to SKIP Tier 4 Deep Research escalation despite the trigger condition being met.
**Origin:** Deep Research v0.5.1 audit §8 (Zhan et al. 2026 "Why Your Deep Research Agent Fails?", OpenAI BrowseComp caveats, Mata v. Avianca 678 F.Supp.3d 443).
**Version:** 0.5.1 / Patch 10

---

## Default behavior

Tier 4 triggers (per CLAUDE.md §AI-AUDIT):
- Tier 3 Opus arbiter returned contradictory / still-inconclusive verdict
- Decision touches `docs/PROJECT_DNA.md §3 (FROZEN)` / `§4 (PINNED)` / `§5 (prohibitions)`
- Owner explicitly says "deep research" / "глубокое исследование"

These are **necessary** for Tier 4, not **sufficient**. Arbiter (Opus) MUST check abort rules before preparing Deep Research brief.

---

## Five abort conditions (any one triggers skip)

### A1 — Single canonical authoritative source

Query reduces to a single-document lookup.

Examples:
- "Does Anthropic's deprecation policy require 60 days notice?" → fetch `docs.claude.com` directly.
- "What does §3 of PROJECT_DNA list as frozen files?" → Read the section.

Action: use `WebFetch` tool or `Read` directly. Deep Research adds noise by synthesizing when synthesis is not needed.

### A2 — Closed-ended binary query, no candidate sources pre-identified

Queries like "is this safe yes/no" without domain sources to check cause DeepHalluBench-style cascading Action-Hallucination (Zhan 2026 arXiv:2601.22984).

Action: route to Tier 3 Opus with explicit uncertainty flag. Binary queries need a verifier, not a researcher.

### A3 — Long-tail niche domain AND no RAG grounding available

Hallucination-selection rate up to **75%** in Geography / rare-biomed / obscure-legal categories on DeepHalluBench.

Examples of long-tail for Biretos:
- Obscure Russian industrial-electronics distributor with no public API and no published contract terms
- Specific ГОСТ certification edge cases not covered by FSA registry

Action: require owner to produce 2+ pre-identified authoritative sources before Tier 4 runs.

### A4 — Every output claim must be legally admissible

Mata v. Avianca precedent: fabricated-case LLM output = sanctioned litigation.

Domains with this property:
- Court filings
- Regulatory submissions (Rospotrebnadzor, FSA)
- Contractual representations
- Financial audit reports to external auditors

Action: Tier 4 output treated as **unverified draft**. Every cite re-fetched and content-hashed against the claim it supports before any external submission. A post-hoc citation-verification sweep is mandatory (see §Post-sweep).

### A5 — Ambiguous success criteria AND no verifier

Agents confabulate to satisfy implicit answer-pressure when "good output" is not pre-defined.

Action: before Tier 4, owner must specify in brief:
- What a correct answer looks like (shape, not content)
- Who verifies: golden-set, second LLM, human domain expert
- Stop condition (e.g. "finds 2+ mutually-citing sources")

If these are not specified → Tier 4 skipped, return to Tier 3 with "CRITERIA_NOT_DEFINED" tag.

---

## Post-hoc citation-verification sweep

**Mandatory for any Tier 4 output containing >3 citations per 1000 words** that will inform a D4/D5 decision.

Process:
1. Extract every URL / DOI / file:line cite from the Deep Research report.
2. For each URL: `WebFetch` content, compute `sha256`, compare against the claim it supports (semantic match, not string match).
3. For DOIs: verify paper exists via DOI registrar API; fetch abstract; match claim context.
4. For file:line: `Read` actual file, verify line exists and matches context.
5. Failed verifications → flag in arbiter synthesis with `unverified_cite: [...]` list. Arbiter treats unverified cites as weight 0.

Helper: `ai_audit/citation_sweep.py` (to be written; plain-text grep-and-fetch script, <100 LOC).

---

## When in doubt: run Tier 3 first

Tier 3 Opus arbiter is cheaper (~$1.50, ~30s), often sufficient, and has the virtue of being bounded. If Tier 3 produces a clean verdict, you didn't need Tier 4. Tier 4 is ONLY for cases where Tier 3 explicitly returns contradictory / inconclusive AND at least one of the primary Tier 4 triggers fires.

---

## Recorded in artifact frontmatter

```yaml
tier_4_considered: true
tier_4_aborted: false   # or true
tier_4_abort_reason: null
# if aborted: "A1_single_source" | "A2_binary_no_sources" | "A3_longtail_no_rag"
#             | "A4_legally_admissible" | "A5_undefined_criteria"
tier_4_citation_sweep_passed: null | true | false
tier_4_unverified_cites: []
```
