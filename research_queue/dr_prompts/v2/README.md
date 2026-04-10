# Deep Research v2 Prompts

Improved prompts incorporating critique of v1 results (16+9=19 prices from 210 SKUs).

## Changes from v1

| Issue | v1 | v2 |
|-------|----|----|
| Role | Formal procurement | Gray Market Analyst |
| Batch size | 210 at once | 40 per session |
| Sources | Official distributors only | Surplus, eBay, Radwell, IndiaMart |
| Alias search | Not mentioned | Mandatory 5-step search strategy |
| Price labeling | Single type | distributor/surplus/gray_market/list_price |

## Files

- `chatgpt_batch{1-5}_*.txt` -- for ChatGPT Deep Research
- `gemini_batch{1-5}_*.txt` -- for Gemini Advanced Deep Research
- 188 remaining SKUs (22 already have prices from v1)

## Workflow

1. Copy-paste one batch file into DR web UI
2. Wait for results (5-30 min per batch)
3. Save response to `research_queue/dr_responses/v2/`
4. Import: `python scripts/dr_result_importer.py research_queue/dr_responses/v2/<file>`
5. Repeat for next batch

Start with batch 1 in both platforms simultaneously.
