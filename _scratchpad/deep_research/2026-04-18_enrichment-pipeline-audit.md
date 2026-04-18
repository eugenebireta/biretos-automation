---
source: Claude Deep Research (claude.ai)
date: 2026-04-18
audit_target: Biretos enrichment pipeline at 10k SKU horizon
verdict: SOUND_WITH_CRITICAL_REGULATORY_GAP
scope: Architecture + encoder + Haiku categorization + datasheet sources + EAC/Chestny Znak
---

# Architectural audit of Biretos enrichment pipeline at 10k SKU horizon

## Executive summary

Pipeline is structurally sound but has two categories of mortal risk:
1. **Regulatory stack currently absent** (EAC + brand authorization + Chestny Znak) — BLOCKING for Ozon/Honeywell publication, KoAP 14.43 exposure up to 1M RUB
2. **Embedding fine-tune regression** (correctly rolled back, but reveals brittle domain assumption)

Three §17 / Haiku-authority / datasheet-only design choices encode a bet that the catalog stays homogeneous. 370-SKU batch already violates that (4/370 overlap with shop_data). Six-layer append-only structure is the right chassis; fixes are localized evolutions, not rewrites.

## Five critical findings

### Q1 — §17 single-writer is under-specified, not over-engineered
Replace "exactly one Writer per field" with "exactly one **Resolver** per field, plus N declared Contributors" emitting `(value, source, extractor_version, confidence, timestamp, valid_from)` tuples. Store tuples; materialize current value as derived view. Migration trigger: first `if source == "manual"` branch inside any Writer.

### Q2 — Encoder rollback correct, upgrade path obvious
Observed v2 regression = **catastrophic forgetting + shortcut learning** (Biderman et al. Selective LoRA 2501.15377). Path forward:
- **Phase 0 (this week):** LoRA-adapter over frozen e5-large (rank 8, Q/V only, 2 epochs, LR 1e-4, false-negative-filtered mining).
- **Phase 1 (2-4 weeks):** Upgrade base to **BGE-M3** (568M, XLM-R lineage, hybrid dense+sparse+ColBERT, Apache-2.0, Russian IR leader per arXiv:2504.12879).
- **Phase 2 (if needed):** QLoRA Qwen3-Embedding-4B.
- **Hard guardrails:** v_new vs v_old top-1 agreement on frozen OOD canary set BEFORE ship; rank ≤16 Q/V only; per-domain temperature calibration; version adapters not encoders.

### Q3 — At 10k SKUs, Haiku stays; hybrid is accuracy upgrade not cost
At 10k/month: Haiku ~$30. At 100k/month: $300. Self-hosted Qwen3-Reranker-0.6B breakeven ~120k/month. **Do not self-host on cost grounds.**

Real architecture: encode all 9,232 Ozon types with BGE-M3 into FAISS/pgvector. Query embedding → top-K=20-50 → feed shortlist into Haiku prompt. Lifts match rate 5-10pp. Taxonomy drift: nightly pull `/v1/description-category/tree` + versioned snapshots + fuzzy remap on diff.

Current Haiku↔local-classifier <5% agreement is NOT a defect of local classifier — it's evidence local 63-class model is being used adversarially. Elevate from veto-gate to **soft prior** (multiplicative boost on parent-matching candidates).

### Q4 — Datasheet exhaustion real; Russian distributor stack is next fill source
Free global sources ranked by ROI for brand mix:
- **Open ICEcat** — highest-value free. Bulk-match 370 SKUs by GTIN+brand+MPN. Expect 25-40% lift on Honeywell/Dell/Howard Leight.
- **TraceParts API** — 188M+ parts, CAD-BOM properties for Phoenix/Siemens/ABB/Schneider (future dominant brands).
- **Digi-Key PIA v4 + Mouser Search** — 1k queries/day free each. Register non-RU legal entity.

**Traps to avoid:** Verified by GS1 (license-level only, no weight/dims), Octopart Standard (excludes Tech Specs), EAN-Search (validator only), 1WorldSync/GDSN ($10k+/yr).

**Cost-per-fill breakeven vs Deep Research at $0.30/field:** On 370 SKUs x ~2 missing fields = 740 cells, DR cost ~$222. Paid tiers (ICEcat $375, Nexar Pro $833) break even only at 2-3k SKUs in matching brand universe. **Defer paid subscriptions until SKU count >2,000.**

**Russian distributor stack — highest leverage for physical attributes:**
- **ETM.ru (iPRO)** — critical relationship. Contract + FTP/API. ~90% fill on DKC, 70% on Siemens/ABB, 30-50% on Honeywell security. 2-3 week contract tail.
- **ChipDip.ru** — no API but rich product pages, scrapable.
- **Platan.ru** — documented public REST API, no contract, integrate in 1 day.
- **Vseinstrumenti** — most complete Honeywell/Howard Leight PPE.
- **CommerceML 2.10/3.0 importer** — single importer reusable across ALL Russian distributors. Spec free at v8.1c.ru.

### Q5 — Regulatory stack is the TOP unmitigated risk

**Publishing Honeywell to Ozon without EAC + brand authorization → ALL THREE happen simultaneously:**
1. Moderation rejection (Ozon blocks "Honeywell" brand selection without authorized letter)
2. Post-publication takedown within 3 business days
3. Rospotrebnadzor exposure KoAP 14.43: 100-300k RUB first case, up to 1M RUB repeat/harm, 90-day activity suspension

**Esser/Honeywell Fire: TR EAEU 043/2017 requires MANDATORY CERTIFICATION (not declaration), 80-300k RUB, 1-3 months. Without it, sale prohibited under 123-FZ with NO marketplace discretion.**

**EAC regulatory map for 370-SKU batch:**
- TR CU 004/2011 (LV equipment): PEHA, Honeywell controllers, DKC, Dell/Optcom
- TR CU 020/2011 (EMC): all electronics
- TR EAEU 037/2016 (RoHS): all electronics, declared separately
- TR TS 019/2011: Howard Leight earplugs (PPE)
- TR EAEU 043/2017: Esser + Honeywell Fire (mandatory certification, not declaration)
- TR TS 012/2011: Ex-versions (if any)

Reseller with existing series declaration + supply chain docs (contract/invoice/UPD) can use it. If importing directly (parallel from EU), seller = importer and MUST hold own declaration. TR CU 004+020 combined: 25-60k RUB / 7-21 days at Serkons/Rostest/PromMashTest/Novotest. TR EAEU 037 adds 15-25k RUB. Valid 5 years on series.

**Chestny Znak as of April 2026 (ПП №1954 от 28.11.2025):**
- Radio-electronics under mandatory Data Matrix from 1 May 2026 (manufacturers/importers).
- Until 30 Nov 2026: legacy stock sell-through allowed.
- From 1 Dec 2026: turnover reporting.
- PEHA switches/sockets, Dell, parts of Honeywell/Optcom controllers subject starting 1 May 2026.
- DKC cable management mostly outside but terminals/connectors partially in — check honestsign.org per SKU.
- Howard Leight hearing protection NOT yet captured April 2026 but expected under HS 6307 90 or 9020 00.
- Marking codes: 60 kopeks + VAT each. Onboarding 2-4 weeks.
- KoAP 15.12 penalties: 50-300k RUB for legal entities, confiscation; >2.25M RUB wholesale = criminal UK 171.1.

**Prerequisites before first Honeywell SKU on Ozon:**
1. Legal entity + RKO active (ООО OSNO recommended for B2B VAT buyers)
2. УКЭП for director (3-7 days via FNS/VTB/Sberbank)
3. EDO contract (Diadoc/SBIS, 2-5 days)
4. **Brand authorization letter from Russian distributor — LONGEST TAIL at 2-6 weeks** (Honeywell distributor chain contracted since 2022). Explicit "право продажи на площадке Ozon/Wildberries на территории РФ".
5. EAC audit per SKU: FSA registry check, gaps → TR CU 004+020+037 combined (25-60k, 10-15 days); Esser/Honeywell Fire → TR EAEU 043 certification (80-300k, 1-3 months); Howard Leight → TR CU 019 (15-25k, 7-14 days)
6. Chestny Znak registration (1-3 days) + hardware (~18k RUB one-time) + marking codes
7. Content per marketplace specs
8. Upload + moderation (3-10 days)

**Step 4 is THE bottleneck. Start brand authorization processes today, in parallel with technical work.**

## Top-5 architectural weaknesses at 10k horizon

1. **Zero EAC + zero brand authorization + unresolved Chestny Znak** = 100% rejection + up to 1M RUB KoAP exposure. **Start distributor-letter and Esser/Honeywell Fire TR EAEU 043 certification today.**
2. §17 single-writer is under-specified for LLM/OCR confidence values. Evolve to Resolver+Contributors.
3. multilingual-e5-large is 2023 vintage. Institutionalize v_new vs v_old OOD canary as CI check. Upgrade base to BGE-M3 within 4 weeks.
4. Haiku-as-authority with <5% local-classifier agreement. Move to retrieval-over-9232-types → Haiku-on-shortlist. Versioned taxonomy-snapshot diff with auto-remap proposals.
5. Datasheet exhaustion at 22%/26%/33% weight/dims/EAN. Next sources: Open ICEcat + TraceParts + Platan public API + CommerceML 3.0 importer. ETM.ru iPRO relationship for DKC/Schneider/ABB goldmine — 2-3 week contract tail.

## Top-3 simplifications

1. **Kill local 63-class classifier as veto gate** → soft prior OR delete entirely.
2. **Stop additional Gemini parse passes on 293 already-attempted PDFs** (1-5% marginal fill on 2nd pass = saturation). Redirect budget to ICEcat + TraceParts.
3. **Defer paid product-data subscriptions** (Nexar Pro, ICEcat paid, EAN-Search) until SKU count >2,000.

## Bottom line

Pipeline chassis is correct and scales. Encoder rollback was right, BGE-M3 migration with LoRA-per-shop is the 2026-appropriate upgrade. §17 evolves to attribute-level provenance without rewrites. Haiku stays at 10k scale; hybrid is accuracy upgrade.

**But none of this matters if EAC + brand authorization + Chestny Znak is not started TODAY — regulatory stack has 4-12 week critical path that dominates every technical timeline.**
