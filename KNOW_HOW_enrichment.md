# Know-How: Enrichment / DR Pipeline

<!-- Sub-file of KNOW_HOW.md. Same format: YYYY-MM-DD | #тег | scope: Суть -->
<!-- Records here are DUPLICATED from KNOW_HOW.md (not moved) per CLAUDE.md rule. -->

2026-04-09 | #platform | gemini-dr: SHORT prompts only. Long prompts trigger analytics mode (narrative, ZERO prices/URLs). Table mode and analytics mode are mutually exclusive.
2026-04-09 | #platform | gemini-dr: input = minimal 3-col table (# | PN | Hint). Batch: 20 SKU. Files: deep-research-report*.md
2026-04-09 | #platform | claude-dr: RICH prompts OK. Include Excel descriptions, ref prices, aliases. Batch: 30 SKU.
2026-04-09 | #platform | chatgpt-compass: RICH prompts + role "Gray Market Analyst". Batch: 30 SKU. Files: compass_artifact_wf-*.md
2026-04-10 | #platform | gemini-dr: batch4 went into analytics/narrative mode despite short table prompt — produced full narrative report + summary table. Prices intact, Russian mojibake, some Price Source URLs are domain-only (not full URLs).
2026-04-10 | #platform | gemini-dr: analytics mode now confirmed 3/3 mixed batches (batch4, batch5, batch6). Mixed PEHA+Honeywell content triggers narrative regardless of prompt format. Not reliable for parseable catalog data on this SKU set.
2026-04-10 | #bug | gemini-dr: Russian text double-encoded — UTF-8 bytes stored as Unicode Latin supplement codepoints. Fix: detect fields with chars in 0x80-0xFF range but no Cyrillic (0x400-0x4FF) and clear them.
2026-04-10 | #platform | gemini non-DR alias substitution: PEHA NOVA Elements regularly returns close-but-wrong PN aliases. 179433 (radio frame €101) → 00020311 (basic white Nova €14). Silent wrong data. Use Claude DR for PEHA.
2026-04-10 | #platform | gemini price fabrication confirmed: 4 proofs on 19-SKU batch. Mechanism: training-data interpolation, NOT closed database access. Proof: fake URLs cannot come from a real database. NEVER use Gemini for price lookup on this catalog.
2026-04-10 | #platform | claude-dr A/B result: rich prompt (v11) > minimal. Δ: +2 prices (14 vs 12), +4 photos (12 vs 8). Use v11 (rich) as standard for Claude DR.
2026-04-10 | #platform | claude non-DR (Haiku/Sonnet/Opus) без web search: только 2-5/19 цен — не годится для price lookup. Но честнее Gemini: никогда не подставляет неправильный PN.
2026-04-10 | #platform | 12-model benchmark (19 SKUs, price lookup без DR): Google AI браузер=18/19; GPT 5.4 Think=18/19; GPT 5.4 Ext Think=18/19 (0 ошибок); Gemini Fast=17/19 (3+ ошибки); Claude DR=14/19, 0 ошибок — лучшее качество.
2026-04-12 | #platform | model-selection: for PN grammar research — GPT Extended Think or GPT Think+web significantly better than regular GPT Think. Use Extended Think or Think+web for any brand grammar batch.
2026-04-12 | #platform | model-selection: for PN pattern research (brand catalog structure) — Claude DR + Opus extended is best.
2026-04-09 | #rule | data: trusted fields = seed_name, our_price_raw, brand, product_type, assembled_title
2026-04-09 | #rule | data: UNRELIABLE field = expected_category (wrong in 92% of evidence — 344/374 files). NEVER use as hint.
2026-04-09 | #rule | data: product hints come ONLY from assembled_title — never invent
2026-04-09 | #rule | research-runner: Haiku-only without web access gives 0 merge candidates — need web grounding
2026-04-13 | #rule | dr-ops: Every AI batch MUST be logged in downloads/DR_BATCH_LOG.json before sending.
2026-04-15 | #rule | model-assignment-pipeline: Phase 1+2=Haiku, Phase 3A=GPT Think, Phase 3B=Opus ext. Gemini permanently banned.

## Data quirks — DR batches

2026-04-13 | #data_quirk | dr-coverage: 30 SKUs no DR at all (mostly PEHA), 59 no specs, 106 no description_ru, 21 old RUB price only.
2026-04-10 | #data_quirk | gemini_pro_batch1: 20 OT/networking SKUs. 11/20 prices, 0 photos, 42 training URLs. Russian text permanently garbled.
2026-04-10 | #data_quirk | claude_opus_batch1: 30 SKUs. 22/30 prices (73%), 12/30 photos, 86 training URLs.
2026-04-10 | #data_quirk | claude_haiku_batch2: 4 Dell UltraSharp monitors. Narrative format. 3/4 prices, 18 training URLs.
2026-04-10 | #data_quirk | claude_sonnet_batch3: 30 SKUs. 22/30 prices (73%), 4/30 photos, 84 training URLs.
2026-04-10 | #data_quirk | claude_sonnet_batch4: 30 SKUs. 29/30 updated, 111 training URLs. Merge: 8.
2026-04-10 | #data_quirk | gemini_pro_batch4: 20 SKUs. 19/20 updated. Russian text mojibake again. Analytics/narrative mode.
2026-04-10 | #data_quirk | gemini_pro_batch5: 14 SKUs. 13/14 prices. Russian text mojibake.
2026-04-10 | #data_quirk | claude_compass_batch5_variantA: 19 SKUs. 14/19 prices, 12/19 photos (A/B Variant A rich prompt v11).
2026-04-10 | #data_quirk | claude_compass_batch5_variantB: 19 SKUs. 12/19 prices, 8/19 photos (A/B Variant B minimal prompt).
2026-04-10 | #data_quirk | claude_vs_gemini batch19: Claude=14/19 correct, 80 URLs. Gemini=12/19 but 4 wrong. Claude wins.
