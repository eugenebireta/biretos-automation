# Task Capsule

Task_ID: R1-enrichment-improvements-v2
Risk: SEMI
Date: 2026-04-08

## Summary

Enrichment Improvements Batch v2 — 9 sequential blocks, 9 commits, 767/767 tests PASS.

Key deliverables:
- **Block 1 — response_raw fix:** `shadow_log()` now uses `None` for API failures
  (distinguishable from `""` empty). Adds `response_raw_present` + `response_raw_truncated`
  fields. 10k char truncation cap.
- **Block 2 — JSON-LD expansion:** `extract_full_jsonld()` captures brand, mpn, gtin13, gtin,
  description (truncated 500), image, category, weight, dimensions, availability, seller,
  aggregateRating, additionalProperty, price_valid_until. Stored in `bundle["jsonld_full"]`.
- **Block 3 — Spec extraction:** `spec_extractor.py` — 3-strategy parser (2-col tables,
  dl/dt/dd, spec-class divs). Replaces inline table-only parser. Caps at 100 specs/page.
  Keys normalised to snake_case. `specs_status="found_from_page"` when found.
- **Block 4 — Brand config registry:** YAML files in `config/brands/` for Honeywell, PEHA, Esser.
  `brand_knowledge.py`: `load_brand_config()`, `get_product_family()`, `get_trusted_domains()`,
  `get_datasheet_query()`, `get_search_hints()`. Sub-brand detection: 153711→PEHA, 804950→Esser.
- **Block 5 — Multi-source prices:** `multi_source_prices.py` — optional SerpAPI distributor
  search + cross-validation via price_sanity. Off by default. Never crashes pipeline.
- **Block 6 — Brand experience writer:** `brand_experience_writer.py` — `BrandExperienceRecord`
  dataclass + `write_brand_experience()`. Pipeline calls after save_checkpoint(). Salience:
  correction=9, failed=7, success=4. Summary ≤200 chars.
- **Block 7 — Conditional datasheets:** `find_datasheet()` auto-triggers for
  no_price_found | NO_PHOTO | category_mismatch (not only --datasheets flag).
- **Block 8 — Training dataset export:** `training_dataset_export.py` — 4 datasets:
  price_extraction (723 examples), photo_verdict (146), category_classification (69),
  search_strategy (0 until next enrichment run). 938 total. Output: `training_data/`.
- **Block 9 — Correction logging:** `correction_logger.py` — `log_correction()` (salience=9),
  `log_price_sanity_warning()` (salience=7). Retrospective: 33 PEHA corrections + 11 sanity
  warnings = 44 records in shadow_log/experience_2026-04.jsonl.

Total new tests: 121 (7+14+15+23+13+16+9+15+9). Full suite: 767/767 PASS.

---

## Web Search Integration Block

**research_providers.py** — `GeminiResearchProvider` (gemini-2.5-flash + Google Search grounding,
~$0.004/call), `ClaudeWebSearchProvider` (claude-sonnet-4-6 with web_search_20250305, ~$0.05/call),
`WebSearchResearchOrchestrator` (Gemini first → stop at medium/high → Claude fallback on low only),
`build_research_prompt()`, `_confidence_rank()`, `_parse_json_from_text()`.

**research_runner.py** — Added `--web-search` flag (activates WebSearchResearchOrchestrator),
`--rerun` flag (clears low-confidence results for retry), `use_web_search` param in
`run_research_for_packet()` and `run_batch_research()`.

**test_research_providers.py** — 29 tests covering all providers, orchestrator strategy
(Gemini-high → no Claude, Gemini-low → Claude, both fail → error dict), prompt builder,
JSON extraction, budget propagation.

Budget worst-case: ($0.004 + $0.05) × 50 SKU = $2.70 (well within $10/day limit).

Total suite after web search block: 1173/1173 PASS.

## Next

Enrichment batch continuation (~175 new SKU from honeywell_insales_import.csv, 195 already
checkpointed). After enrichment: research_runner --web-search --rerun for 37 failed high-priority
SKUs, then training_dataset_export.py for updated training data stats.

---

# Task Capsule (previous)

Task_ID: R1-overnight-batch-1-2
Risk: SEMI
Date: 2026-04-08

## Summary
Overnight autonomous batch: price sanity check, enrichment continuation (301 SKU),
self-audit, PEHA category_mismatch batch fix, research queue export, Claude API
deep-research batch.

Key deliverables:
- **price_sanity.py**: 5-rule price validator (REJECT/WARNING/PASS) — AED/exotic
  currency flag, high piece price, cross-reference 5× median, extreme bounds, round
  number detection. 26 deterministic tests PASS. Integrated into photo_pipeline.py.
- **Retrospective sanity audit**: 69 existing SKU — PASS=31, WARNING=11, REJECT=0.
  Results in shadow_log/price_sanity_audit_2026-04.jsonl.
- **Enrichment batch**: running background, ~79/370 at snapshot time (~1 SKU/min).
- **Category fix**: 33 PEHA items corrected (Вентиль/Детектор/Датчик →
  Рамки/Клавиши/Диммеры/Накладки PEHA). 30 SKU: price_now_admissible.
  shadow_log/category_fix_2026-04.jsonl.
- **research_queue.py**: emits JSON+MD research packets for DRAFT/REVIEW_REQUIRED SKU.
  69 packets generated (37 high, 32 low priority). Category breakdown: category_mismatch=34,
  identity_weak=28, no_price_lineage=5, specs_gap=2.
- **research_runner.py**: Claude API deep-research with budget guard, MockProvider for
  tests, audit, merge candidates, overnight report. 23 tests PASS.
- **Batch research**: 37 high-priority packets sent to claude-haiku (running background).
  Results go to research_results/ — NOT merged without owner review.

After category fix: DRAFT_ONLY=58, REVIEW_REQUIRED=11 (from initial 69 SKU).
Total new tests: 69 (26+20+23), full suite 646/646 PASS.

---

# Task Capsule (previous)

Task_ID: R1-revenue-price-scout-batch2
Risk: LOW
Date: 2026-04-07

## Summary
Price scout batch2 — 17 new SKUs (Esser fire safety, HVAC actuators, barcode printers) from authorized/industrial distributors.

Key deliverables:
- **trust.py**: 7 new domains — walde.ee (authorized, Esser official distributor Estonia), firealarmmax.com, globaltestsupply.com, bolasystems.com, shop.peaktech.com, barcodefactory.com, logiscenter.us (all industrial)
- **price_manual_seed_batch2.jsonl**: 17 manually seeded prices, all from verified distributor pages
- **price_manual_manifest_batch2.jsonl**: 11 admissible_public_price, 6 ambiguous_offer
- **test fix**: test_access_denied_page_stays_non_lineage URL corrected — url_path_pn_match feature fires on embedded PNs by design; test URL must not include PN

Result: 11 new admissible prices for future catalog expansion. Evidence bundles not yet created (new SKUs not in current 25-SKU local catalog — expected TRANSIENT skips).

849/849 tests PASS.

---

Task_ID: R1-revenue-price-scout-resolution
Risk: LOW
Date: 2026-04-07

## Summary
Resolved 5 of 11 previously ambiguous price seeds. Key deliverables:
- **pn_match.py**: suffix-variant fallback (strip -RU/-L3/N/U before lineage match)
- **trust.py**: 7 new industrial domains for RU PPE + US safety suppliers  
- **Seeds**: 4 updated with accessible URLs; 129464N/U newly admissible ($640 DM Supply)
- **Honeywell PN conventions** documented in memory (base PN + color/region/kit suffixes)
- **Evaluation report** (honeywell.xlsx) identified as reference price source for all 17 SKU

Final state: 6 admissible_public_price, 5 review_required (surface_conflict or rfq/no-url)

## Remaining Gaps
- 8 PEHA items: catalog says "sensors" but products are electrical switch covers → needs reclassification
- 1011893-RU / 1011894-RU: lineage=True, surface_conflict (new URLs, will stabilize)
- 129625-L3: distributor uses GA-USB1-IR code, manufacturer PN not in page HTML
- 1015021 / 121679-L3: no public price found (rfq_only or no accessible page)

---

Task_ID: R1-revenue-photo-price-recovery-attempt
Risk: LOW
Date: 2026-04-07
Branch: feat/rev-r1-catalog
PR: https://github.com/eugenebireta/biretos-automation/pull/38
Status: COMPLETED — structural gap confirmed, no new admissible data

## What was done

Attempted photo recovery (14 SKU) and price scout (10 SKU) from followup queues.

Key setup actions completed:
- `config/.env.providers` created with ANTHROPIC_API_KEY (providers.py step2b now functional)
- `.claude/settings.local.json` created with SERPAPI_KEY + OPENAI_API_KEY (persistent across sessions)
- `.gitignore` updated to protect `settings.local.json`

## Results

Photo recovery: 14/14 REJECT — no improvement.
Price scout: 0/8 new admissible prices found.

Root cause: Structural PN collision. 7 SKU (101411, 104011, 105411, 106511, 109411, 125711, 127411)
have Honeywell part numbers that are shared with Peha by Honeywell home automation products
(switches, outlets, cover frames). Automated search always returns the wrong product category.
No automated recovery path exists for these SKU.

Catalog state after refresh: 0 auto_publish, 13 review_required, 12 draft_only, 25 total.
849/849 tests PASS.

## Known Gap (structural)

7 PN-collision SKU need manual photo sourcing or catalog cleanup.
3 genuinely unseeded SKU (not in catalog CSV or no web presence).
3 admissibility_review SKU need owner judgment (pack ambiguity, component flags).
price_followup=17, photo_recovery=14.

## Previous Capsule (R1 price-evidence-integrator — seq 63)

Task_ID: R1-revenue-price-evidence-integrator
Risk: SEMI
Date: 2026-04-07
Branch: feat/rev-r1-catalog
PR: https://github.com/eugenebireta/biretos-automation/pull/38
Status: COMPLETED — committed, pushed to feat/rev-r1-catalog

## What was built

`price_evidence_integrator.py` closes the gap between `price_manual_scout.py` output
(manifests) and the canonical evidence bundles read by `local_catalog_refresh.py`.

Key components:
- `scripts/price_evidence_integrator.py` — reads price manifest JSONL, applies
  `price_admissibility.materialize_price_admissibility()` per row; for rows classified
  `offer_admissibility_status == "admissible_public_price"` writes the price section
  into `evidence_<pn>.json`, sets `field_statuses_v2["price_status"] = "ACCEPTED"` and
  `policy_decision_v2["price_status"] = "ACCEPTED"`, records integration trace in
  `refresh_trace["price_integration"]`. Does NOT touch `card_status`.
- `tests/enrichment/test_price_evidence_integrator.py` — 32 deterministic tests covering
  build_price_section, evidence_path lookup, success, skips, dry_run, idempotency.

DNA compliance:
- trace_id generated per run (pi_<ts>_<hex>), injectable _now_fn for deterministic tests
- idempotent: overwriting price section + trace with same trace_id is safe
- error_class/severity/retriable on all error paths
- no Core DML, no domain.reconciliation_* imports
- explicit field allowlist (_PRICE_FIELD_MAP) to prevent schema drift

## Real integration result

Run against `downloads/scout_cache/price_manual_manifest.jsonl` (20 rows):
- 5 rows classified `admissible_public_price` → integrated
- 15 rows skipped (offer_status != admissible_public_price)
- Evidence bundles updated: 027913.10 (EUR 467→44365 RUB), 1000106 (AED 68.25→1638 RUB),
  1006186 (TWD 1794, rub_price=None — FX gap), 1003012, 1030000000

Post-integration `local_catalog_refresh.py` result:
- review_required=15 (up from 9), draft_only=10, auto_publish=0, promote_canonical=false

Post-integration `build_catalog_followup_queues.py`:
- price_followup_count=14, photo_recovery_count=14

## Governance

SEMI risk. Two-round audit via auditor_system API (Gemini 3.1 Pro CRITIC + Opus 4.6 JUDGE).
Result: **BATCH_APPROVAL** (quality gate passed).
Post-audit fixes: sys.path.insert moved to module level; trace_id timestamp sourced from now_fn().

## Coverage

798/798 tests PASS (zero regression). 32/32 integrator tests PASS.

## Previous Capsule (M4 Executor Bridge — seq 60)

M4 Executor Bridge closes the automation loop for the Meta Orchestrator.
When `auto_execute: true` in config.yaml, `python orchestrator/main.py` now
runs end-to-end: intake → classify → advisor → synthesizer → directive → claude --print → collect_packet.
New: `orchestrator/executor_bridge.py` (run()+run_with_collect()), 43 tests.
SEMI BATCH_APPROVAL. 308/308 orchestrator tests PASS.

## Next

Revenue R1 track: photo pipeline recovery (14 SKU) or next price scout batch (14 SKU).
