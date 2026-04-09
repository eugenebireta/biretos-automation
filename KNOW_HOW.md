# Know-How Log

Только внешние и неявные знания. Код документирует себя через git log.
Формат: `YYYY-MM-DD | #тег | scope: Суть и почему это важно`
Tags: #platform, #bug, #rule, #data_quirk
Scripts registry: see `scripts/MANIFEST.json` (don't duplicate here)

2026-04-09 | #platform | gemini-dr: SHORT prompts only. Long prompts trigger analytics mode (narrative, ZERO prices/URLs). Table mode and analytics mode are mutually exclusive.
2026-04-09 | #platform | gemini-dr: input = minimal 3-col table (# | PN | Hint). Batch: 20 SKU. Files: deep-research-report*.md
2026-04-09 | #platform | claude-dr: RICH prompts OK. Include Excel descriptions, ref prices, aliases. Batch: 30 SKU.
2026-04-09 | #platform | chatgpt-compass: RICH prompts + role "Gray Market Analyst". Batch: 30 SKU. Files: compass_artifact_wf-*.md
2026-04-09 | #rule | data: trusted fields = seed_name, our_price_raw, brand, product_type, assembled_title
2026-04-09 | #rule | data: UNRELIABLE field = expected_category (wrong for 33+ PEHA items). NEVER use as hint.
2026-04-09 | #rule | data: product hints come ONLY from assembled_title — never invent
2026-04-09 | #rule | pn-suffix: .10=color, -RU=Russian market, -L3=kit, N/U=replacement
2026-04-09 | #rule | research-runner: Haiku-only without web access gives 0 merge candidates — need web grounding
2026-04-09 | #rule | orchestrator: manifest.json itself triggers A4:SCOPE drift because orchestrator writes to it during execution. Known false positive.
2026-04-09 | #rule | orchestrator: A4:SCOPE uses repo-relative paths with basename fallback. Directive scope "guardian.py" matches "orchestrator/guardian.py". Without full path — risk of false drift rejection.
2026-04-09 | #bug | dr_prompt_generator: v6 used expected_category as hint — wrong for 33+ PEHA. Fix: use assembled_title only.
2026-04-09 | #bug | export_pipeline: 5 DR fields (price, currency, title_ru, description_ru, image_url) were not exported. Fix: added all 5 columns.
2026-04-09 | #bug | price_extraction: PN 00020211 fails 37x with RuntimeError, provider=openai model=claude-haiku-4-5 parse_success=false. Needs investigation.
2026-04-09 | #bug | orchestrator: B10 — git reset --soft leaves staged new files on disk. Must git restore --staged before checkout+clean or executor artifacts leak.
2026-04-09 | #bug | tooling: git stash pop puts unstaged files into working tree — they leak into next commit. Always git status + git diff --staged after stash pop BEFORE committing.
