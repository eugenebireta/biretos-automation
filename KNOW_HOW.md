# Know-How Log

Format: `YYYY-MM-DD #tag scope: fact`
Tags: #platform, #bug, #rule, #pipeline
Scripts registry: see `scripts/MANIFEST.json` (don't duplicate here)

2026-04-09 #pipeline core: dr_prompt_generator → (user runs DR) → dr_results_import → merge_research_to_evidence → download_documents → export_pipeline
2026-04-09 #platform gemini-dr: SHORT prompts only. Long prompts trigger analytics mode (narrative, ZERO prices/URLs). Table mode and analytics mode are mutually exclusive.
2026-04-09 #platform gemini-dr: input = minimal 3-col table (# | PN | Hint). Batch: 20 SKU. Files: deep-research-report*.md
2026-04-09 #platform claude-dr: RICH prompts OK. Include Excel descriptions, ref prices, aliases. Batch: 30 SKU.
2026-04-09 #platform chatgpt-compass: RICH prompts + role "Gray Market Analyst". Batch: 30 SKU. Files: compass_artifact_wf-*.md
2026-04-09 #rule data: trusted fields = seed_name, our_price_raw, brand, product_type, assembled_title
2026-04-09 #rule data: UNRELIABLE field = expected_category (wrong for 33+ PEHA items). NEVER use as hint.
2026-04-09 #rule data: product hints come ONLY from assembled_title — never invent
2026-04-09 #rule pn-suffix: .10=color, -RU=Russian market, -L3=kit, N/U=replacement
2026-04-09 #rule research-runner: Haiku-only without web access gives 0 merge candidates — need web grounding
2026-04-09 #bug dr_prompt_generator: v6 used expected_category as hint — wrong for 33+ PEHA. Fix: use assembled_title only.
2026-04-09 #bug export_pipeline: 5 DR fields (price, currency, title_ru, description_ru, image_url) were not exported. Fix: added all 5 columns.
2026-04-09 #bug price_extraction: PN 00020211 fails 37x with RuntimeError, provider=openai model=claude-haiku-4-5 parse_success=false. Needs investigation.
2026-04-09 #rule orchestrator: manifest.json itself triggers A4:SCOPE drift because orchestrator writes to it during execution. Known false positive.
2026-04-09 #rule orchestrator: auto_pytest was FALSE until 2026-04-09 (commit 36eca4e). All executor commits before this date were NOT auto-tested. G4/A3 gates were bypassed.
2026-04-09 #bug orchestrator: B10 revert gap -- git reset --soft left staged new files on disk. Fix: add git restore --staged before checkout+clean. Verified: staged executor files gone after fix, HEAD restored, status clean.
2026-04-09 #rule pre-commit: install with `pip install pre-commit` then `pre-commit install`. Config at .pre-commit-config.yaml — runs ruff check --select E,W,F on every commit.

## Pre-commit Setup

```bash
pip install pre-commit
pre-commit install
```

This installs the Ruff linter hook (`.pre-commit-config.yaml`). On every `git commit`, Ruff runs `ruff check --select E,W,F` over staged files. To run manually: `pre-commit run --all-files`.
