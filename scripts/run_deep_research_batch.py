"""run_deep_research_batch.py — Automated Deep Research via Gemini grounded search.

Reads pilot manifest, sends each SKU to Gemini with Google Search grounding,
saves raw results alongside prompts.

Usage:
    python scripts/run_deep_research_batch.py [--limit 25]
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
DEEP_DIR = ROOT / "research_results" / "deep"
MANIFEST = DEEP_DIR / "manifest.json"


def run_single_sku(client, pn: str, prompt_text: str, use_grounding: bool = False) -> dict:
    """Run research for one SKU. Returns raw result dict.

    Args:
        use_grounding: If True, use Google Search grounding (requires paid API).
                       Free tier returns empty text with grounding enabled.
    """
    from google.genai import types

    try:
        config_kwargs = {
            "temperature": 0.1,
            "max_output_tokens": 8192,
        }
        if use_grounding:
            config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_text,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        text = response.text or ""

        # Extract grounding URLs
        grounding_urls = []
        try:
            for cand in (getattr(response, "candidates", []) or []):
                gm = getattr(cand, "grounding_metadata", None)
                if not gm:
                    continue
                for chunk in (getattr(gm, "grounding_chunks", []) or []):
                    web = getattr(chunk, "web", None)
                    if web:
                        url = getattr(web, "uri", "")
                        if url:
                            grounding_urls.append(url)
        except Exception:
            pass

        # Try to extract JSON block from response
        json_block = None
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence:
            try:
                json_block = json.loads(fence.group(1))
            except json.JSONDecodeError:
                pass
        if not json_block:
            brace_start = text.rfind("{")
            brace_end = text.rfind("}")
            if brace_start >= 0 and brace_end > brace_start:
                try:
                    candidate = text[brace_start:brace_end + 1]
                    candidate = re.sub(r",\s*}", "}", candidate)
                    json_block = json.loads(candidate)
                except json.JSONDecodeError:
                    pass

        return {
            "status": "ok",
            "raw_text": text,
            "json_block": json_block,
            "grounding_urls": list(dict.fromkeys(grounding_urls)),
            "text_length": len(text),
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "raw_text": "",
            "json_block": None,
            "grounding_urls": [],
        }


def main():
    import argparse
    p = argparse.ArgumentParser(description="Run Deep Research batch via Gemini")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--grounding", action="store_true",
                   help="Enable Google Search grounding (requires paid API tier)")
    args = p.parse_args()

    from dotenv import load_dotenv
    load_dotenv(DOWNLOADS / ".env")

    from google import genai
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        log.error("GEMINI_API_KEY not set")
        sys.exit(1)
    client = genai.Client(api_key=api_key)

    manifest = json.loads(MANIFEST.read_text("utf-8"))
    skus = manifest["skus"][:args.limit]
    log.info(f"Running Deep Research for {len(skus)} SKUs")

    results_summary = []
    prices_found = 0
    confirmed = 0

    for i, sku in enumerate(skus, 1):
        pn = sku["pn"]
        provider = sku["provider"]
        safe_pn = re.sub(r'[\\/:*?"<>|]', "_", pn)

        # Read the prompt
        prompt_path = DEEP_DIR / provider / f"{safe_pn}.md"
        if not prompt_path.exists():
            log.warning(f"  [{i}/{len(skus)}] {pn}: prompt not found, skipping")
            continue

        prompt_text = prompt_path.read_text("utf-8")
        log.info(f"  [{i}/{len(skus)}] {pn} (owner_price={sku['owner_price_rub']:,.0f} RUB)")

        result = run_single_sku(client, pn, prompt_text, use_grounding=args.grounding)

        # Save raw result
        result_path = DEEP_DIR / provider / f"{safe_pn}_result.json"
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Also save raw text as markdown
        if result["raw_text"]:
            md_path = DEEP_DIR / provider / f"{safe_pn}_result.md"
            md_path.write_text(result["raw_text"], encoding="utf-8")

        # Analyze
        jb = result.get("json_block") or {}
        found_price = jb.get("price_per_unit") is not None
        is_confirmed = bool(jb.get("pn_confirmed"))

        if found_price:
            prices_found += 1
            log.info(f"    PRICE: {jb.get('price_currency', '?')} {jb.get('price_per_unit')} "
                     f"from {jb.get('price_source_url', 'unknown')[:50]}")
        if is_confirmed:
            confirmed += 1

        results_summary.append({
            "pn": pn,
            "status": result["status"],
            "pn_confirmed": is_confirmed,
            "price_found": found_price,
            "price": jb.get("price_per_unit"),
            "currency": jb.get("price_currency"),
            "source_url": jb.get("price_source_url"),
            "confidence": jb.get("confidence"),
            "grounding_urls_count": len(result.get("grounding_urls", [])),
            "text_length": result.get("text_length", 0),
        })

        # Rate limiting: ~4s between requests
        if i < len(skus):
            time.sleep(4)

    # Save batch report
    report = {
        "total": len(skus),
        "ok": sum(1 for r in results_summary if r["status"] == "ok"),
        "errors": sum(1 for r in results_summary if r["status"] == "error"),
        "prices_found": prices_found,
        "confirmed": confirmed,
        "results": results_summary,
    }
    report_path = DEEP_DIR / "batch_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n=== Deep Research Batch Report ===")
    print(f"  Total:     {report['total']}")
    print(f"  OK:        {report['ok']}")
    print(f"  Errors:    {report['errors']}")
    print(f"  Confirmed: {report['confirmed']}")
    print(f"  Prices:    {report['prices_found']}")

    if prices_found:
        print(f"\n  Price results:")
        for r in results_summary:
            if r["price_found"]:
                print(f"    {r['pn']:20s} {r['currency'] or '?':>4s} "
                      f"{r['price'] or 0:>10.2f}  {(r['source_url'] or '')[:50]}")


if __name__ == "__main__":
    main()
