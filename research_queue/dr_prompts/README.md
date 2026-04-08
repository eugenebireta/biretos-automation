# Deep Research Prompts

Three prompts for manual Deep Research via web UI subscriptions.
Each contains all 210 DRAFT SKUs sorted by revenue priority.

## Workflow

### Step 1 — Run DR (one copy-paste per platform)

**Gemini Advanced** (priority):
1. Open [gemini.google.com](https://gemini.google.com)
2. Click "Deep Research" mode
3. Paste contents of `gemini_dr_prompt.txt`
4. Wait 5-15 min for results
5. Copy the full response to `research_queue/dr_responses/gemini_response.txt`

**ChatGPT Plus** (cross-validation):
1. Open [chatgpt.com](https://chatgpt.com)
2. Select "Deep Research" mode
3. Paste contents of `chatgpt_dr_prompt.txt`
4. Copy response to `research_queue/dr_responses/chatgpt_response.txt`

**Claude Projects** (optional, batch analysis):
1. Open [claude.ai](https://claude.ai) with a Project
2. Paste contents of `claude_projects_prompt.txt`
3. Copy response to `research_queue/dr_responses/claude_response.txt`

### Step 2 — Import results

```bash
# Import Gemini results
python scripts/dr_result_importer.py research_queue/dr_responses/gemini_response.txt

# Import ChatGPT results
python scripts/dr_result_importer.py research_queue/dr_responses/chatgpt_response.txt

# Import Claude results
python scripts/dr_result_importer.py research_queue/dr_responses/claude_response.txt
```

Use `--dry-run` to preview without writing:
```bash
python scripts/dr_result_importer.py research_queue/dr_responses/gemini_response.txt --dry-run
```

### Step 3 — Results

The importer writes to:
- `downloads/evidence/evidence_<PN>.json` — per-SKU evidence bundles
- `research_queue/dr_responses/import_report_<source>_<timestamp>.json` — import summary

## Files

| File | Platform | Format |
|------|----------|--------|
| `gemini_dr_prompt.txt` | Gemini Advanced DR | Markdown table output |
| `chatgpt_dr_prompt.txt` | ChatGPT Plus DR | Table or JSON output |
| `claude_projects_prompt.txt` | Claude Projects | JSON array output |

## Notes

- Prompts intentionally omit owner prices to prevent LLM parroting bias
- 210 SKUs, ~16K chars per prompt — fits all platforms
- DR may not research all 210 in one session — if truncated, re-run with remaining
