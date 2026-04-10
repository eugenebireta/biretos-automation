"""AI-assisted price scout using Gemini (Google Search grounding) or Claude (web search).

Queries an LLM with real-time web search for product pages with prices.
Output is JSONL compatible with price_manual_scout.py --manual-seed format.

Usage:
    python gemini_price_scout.py --queue downloads/scout_cache/price_followup_queue.jsonl
    python gemini_price_scout.py --queue ... --provider claude
    python gemini_price_scout.py --queue ... --provider gemini --limit 5
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SECRETS_PATH = ROOT / "auditor_system" / "config" / ".env.auditors"
SCOUT_CACHE_DIR = ROOT / "downloads" / "scout_cache"

GEMINI_MODEL = "gemini-2.5-flash"
CLAUDE_MODEL = "claude-sonnet-4-6-20250514"

QUEUE_SCHEMA_VERSION = "followup_queue_v2"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_secrets() -> dict[str, str]:
    """Load API keys from .env.auditors via dotenv_values (no env pollution)."""
    from dotenv import dotenv_values
    if not SECRETS_PATH.exists():
        raise RuntimeError(f"Secrets file not found: {SECRETS_PATH}")
    return dict(dotenv_values(str(SECRETS_PATH)))


def _build_prompt(item: dict[str, Any]) -> str:
    pn = item.get("pn") or item.get("part_number", "")
    brand = item.get("brand", "Honeywell")
    name = item.get("product_name", "")
    category = item.get("product_type", "")
    placement = item.get("site_placement", "")

    return f"""Find the exact product page with a price for this industrial product:

- Part Number: {pn}
- Brand: {brand}
- Product Name: {name}
- Product Type/Category: {category}
- Catalog Placement: {placement}

IMPORTANT:
- Search for the EXACT part number "{pn}" by brand "{brand}".
- The product must be an industrial/commercial product, NOT a home automation switch/outlet/frame.
- If "{brand}" makes both home products and industrial products with similar part numbers, find the INDUSTRIAL one matching the category "{category}".
- Look at authorized distributors, industrial suppliers, manufacturer catalogs.
- If the product has a different common name or alias, try those too.

Return a JSON object with these fields:
{{
  "found": true/false,
  "part_number": "{pn}",
  "page_url": "URL of the exact product page",
  "price_per_unit": 123.45,
  "currency": "EUR/USD/GBP/RUB/etc",
  "price_status": "public_price" or "rfq_only" or "no_price_found",
  "stock_status": "in_stock" / "backorder" / "out_of_stock" / "unknown",
  "offer_qty": 1,
  "offer_unit_basis": "piece" / "box" / "pack",
  "source_name": "name of the website/store",
  "confidence_note": "brief explanation of why this is the right product"
}}

If you cannot find this exact product with a price, return {{"found": false, "part_number": "{pn}", "reason": "explanation"}}.
Return ONLY the JSON object, no other text."""


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    """Extract JSON object from LLM response text."""
    text = text.strip()

    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    elif not text.startswith("{"):
        brace = text.find("{")
        if brace >= 0:
            text = text[brace:]

    last_brace = text.rfind("}")
    if last_brace >= 0:
        text = text[: last_brace + 1]

    # Fix trailing commas before closing brace
    text = re.sub(r",\s*}", "}", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def query_gemini(item: dict[str, Any], api_key: str) -> dict[str, Any] | None:
    """Query Gemini with Google Search grounding."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    prompt = _build_prompt(item)

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
                max_output_tokens=2048,
            ),
        )
        text = response.text or ""
        log.info("  Gemini response length: %d chars", len(text))
        return _extract_json_from_text(text)
    except Exception as e:
        log.warning("  Gemini error: %s", e)
        return None


def query_claude(item: dict[str, Any], api_key: str) -> dict[str, Any] | None:
    """Query Claude with web search tool."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _build_prompt(item)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
            messages=[{"role": "user", "content": prompt}],
        )
        # Extract text from response content blocks
        text_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        text = "\n".join(text_parts)
        log.info("  Claude response length: %d chars", len(text))
        return _extract_json_from_text(text)
    except Exception as e:
        log.warning("  Claude error: %s", e)
        return None


def _to_manual_seed(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    """Convert LLM result to price_manual_seed.jsonl format."""
    if not result or not result.get("found"):
        return None

    page_url = str(result.get("page_url") or "").strip()
    if not page_url:
        return None

    price_per_unit = result.get("price_per_unit")
    currency = result.get("currency")
    price_status = result.get("price_status", "public_price")

    if price_per_unit is None and price_status not in ("rfq_only", "no_price_found"):
        price_status = "no_price_found"

    try:
        price_per_unit = float(price_per_unit) if price_per_unit is not None else None
    except (ValueError, TypeError):
        price_per_unit = None

    return {
        "part_number": item.get("pn") or item.get("part_number", ""),
        "brand": item.get("brand", "Honeywell"),
        "product_name": item.get("product_name", ""),
        "expected_category": item.get("product_type", ""),
        "page_url": page_url,
        "source_provider": "gemini_search",
        "price_status": price_status,
        "price_per_unit": price_per_unit,
        "currency": currency,
        "offer_qty": result.get("offer_qty", 1),
        "offer_unit_basis": result.get("offer_unit_basis", "piece"),
        "stock_status": result.get("stock_status", "unknown"),
        "lead_time_detected": False,
        "price_confidence": 80,
        "source_price_value": price_per_unit,
        "source_price_currency": currency,
        "source_offer_qty": result.get("offer_qty", 1),
        "source_offer_unit_basis": result.get("offer_unit_basis", "piece"),
        "price_basis_note": result.get("confidence_note", ""),
        "notes": f"AI-assisted search via {result.get('source_name', 'web')}",
    }


def load_queue(queue_path: Path) -> list[dict[str, Any]]:
    """Load price followup queue, filtering for actionable items."""
    rows = []
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows.append(row)
    return rows


def run(
    queue_path: Path,
    *,
    provider: str = "gemini",
    limit: int | None = None,
    output_path: Path | None = None,
    delay: float = 2.0,
) -> dict[str, Any]:
    """Run AI-assisted price scout and produce manual_seed JSONL."""
    secrets = _load_secrets()

    if provider == "gemini":
        api_key = secrets.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY missing in secrets")
        query_fn = lambda item: query_gemini(item, api_key)
    elif provider == "claude":
        api_key = secrets.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY missing in secrets")
        query_fn = lambda item: query_claude(item, api_key)
    else:
        raise ValueError(f"Unknown provider: {provider}")

    items = load_queue(queue_path)
    if limit:
        items = items[:limit]

    stamp = _utc_stamp()
    if output_path is None:
        output_path = SCOUT_CACHE_DIR / f"ai_price_seed_{provider}_{stamp}.jsonl"

    results: list[dict[str, Any]] = []
    found_count = 0
    not_found_count = 0

    for i, item in enumerate(items, 1):
        pn = item.get("pn") or item.get("part_number", "")
        name = item.get("product_name", "")[:50]
        log.info("[%d/%d] %s — %s", i, len(items), pn, name)

        result = query_fn(item)

        if result and result.get("found"):
            seed = _to_manual_seed(item, result)
            if seed:
                results.append(seed)
                found_count += 1
                url = result.get("page_url", "")[:60]
                price = result.get("price_per_unit", "?")
                currency = result.get("currency", "?")
                log.info("  FOUND: %s %s @ %s", price, currency, url)
            else:
                not_found_count += 1
                log.info("  found=true but no valid URL/price")
        else:
            not_found_count += 1
            reason = (result or {}).get("reason", "no response")
            log.info("  NOT FOUND: %s", reason[:80])

        if i < len(items):
            time.sleep(delay)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        for row in results:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "provider": provider,
        "model": GEMINI_MODEL if provider == "gemini" else CLAUDE_MODEL,
        "queue_path": str(queue_path),
        "total_queried": len(items),
        "found_count": found_count,
        "not_found_count": not_found_count,
        "output_path": str(output_path),
        "timestamp": stamp,
    }

    log.info("Done: found=%d not_found=%d output=%s", found_count, not_found_count, output_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI-assisted price scout using Gemini or Claude with web search.",
    )
    parser.add_argument("--queue", required=True, help="Price followup queue JSONL")
    parser.add_argument("--provider", default="gemini", choices=["gemini", "claude"],
                        help="LLM provider (default: gemini)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of SKUs")
    parser.add_argument("--output", default="", help="Output JSONL path (default: auto)")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between API calls (seconds)")
    args = parser.parse_args()

    summary = run(
        queue_path=Path(args.queue),
        provider=args.provider,
        limit=args.limit,
        output_path=Path(args.output) if args.output else None,
        delay=args.delay,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
