"""dr_result_importer.py — Import Deep Research results into evidence bundles.

Parses text output from DR sessions (Gemini, ChatGPT, Claude) and writes
structured results to evidence files + updates research_results.

Supports:
- Markdown table format
- JSON array format
- Mixed text with embedded JSON

Usage:
    python scripts/dr_result_importer.py <response_file> [--source gemini|chatgpt|claude] [--dry-run]

Workflow:
    1. User pastes DR prompt into Gemini/ChatGPT/Claude web UI
    2. Copies response text into a file (e.g. research_queue/dr_responses/gemini_response.txt)
    3. Runs: python scripts/dr_result_importer.py research_queue/dr_responses/gemini_response.txt
    4. Script parses results and updates evidence bundles
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = ROOT / "downloads" / "evidence"
RESULTS_DIR = ROOT / "research_results"
DEEP_DIR = RESULTS_DIR / "deep"


def parse_json_array(text: str) -> list[dict] | None:
    """Try to extract a JSON array from text."""
    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in text
    # Look for [...] block
    match = re.search(r'\[\s*\{.*?\}\s*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Try to find fenced JSON block
    fence = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    # Try to collect individual JSON objects
    objects = []
    for m in re.finditer(r'\{[^{}]*"pn"\s*:\s*"[^"]+?"[^{}]*\}', text, re.DOTALL):
        try:
            obj = json.loads(m.group(0))
            if "pn" in obj:
                objects.append(obj)
        except json.JSONDecodeError:
            # Try fixing trailing commas
            fixed = re.sub(r',\s*}', '}', m.group(0))
            try:
                obj = json.loads(fixed)
                if "pn" in obj:
                    objects.append(obj)
            except json.JSONDecodeError:
                pass

    return objects if objects else None


def _parse_single_table(lines: list[str], header_idx: int) -> tuple[list[dict], dict, int]:
    """Parse one markdown table starting at header_idx.
    Returns (rows, header_map, end_line_idx)."""
    header_line = lines[header_idx]
    headers = [h.strip().lower().replace(' ', '_') for h in header_line.split('|') if h.strip()]

    header_map = {}
    for i, h in enumerate(headers):
        if h in ('#', 'no', 'num', 'row'):
            header_map[i] = '_row'
        elif 'pn' in h or 'part' in h:
            header_map[i] = 'pn'
        elif h in ('price', 'price_per_unit'):
            header_map[i] = 'price'
        elif 'curr' in h:
            header_map[i] = 'currency'
        elif 'source' in h or 'url' == h:
            header_map[i] = 'source_url'
        elif 'categ' in h:
            header_map[i] = 'category'
        elif 'image' in h or 'photo' in h:
            header_map[i] = 'image_url'
        elif 'price_type' in h or 'type' == h:
            header_map[i] = 'price_type'
        elif 'alias' in h:
            header_map[i] = 'alias_found'
        elif 'spec' in h:
            header_map[i] = 'specs'
        elif 'note' in h:
            header_map[i] = 'notes'
        elif 'page_type' in h or 'page' in h:
            header_map[i] = 'page_type'
        elif 'has_price' in h:
            header_map[i] = 'has_price'
        elif 'has_spec' in h:
            header_map[i] = 'has_specs'
        elif 'has_photo' in h:
            header_map[i] = 'has_photo'
        elif 'domain' in h:
            header_map[i] = 'domain'
        else:
            header_map[i] = h

    # Skip separator line (|---|---|...)
    data_start = header_idx + 1
    if data_start < len(lines) and re.match(r'\s*\|[\s\-:|]+\|', lines[data_start]):
        data_start += 1

    results = []
    end_idx = data_start
    for idx in range(data_start, len(lines)):
        line = lines[idx]
        # Stop at blank line or next heading (signals a new table)
        if not line.strip() or line.strip().startswith('#'):
            end_idx = idx
            break
        if '|' not in line:
            end_idx = idx
            break
        cells = [c.strip() for c in line.split('|') if c.strip() != '']
        if not cells:
            end_idx = idx
            break
        # Stop if this looks like a new table header (separator follows)
        if idx + 1 < len(lines) and re.match(r'\s*\|[\s\-:|]+\|', lines[idx + 1]):
            end_idx = idx
            break

        row = {}
        for i, cell in enumerate(cells):
            if i in header_map:
                key = header_map[i]
                if key == '_row':
                    continue
                row[key] = cell
        if 'pn' in row and row['pn']:
            results.append(row)
        end_idx = idx + 1
    else:
        end_idx = len(lines)

    return results, header_map, end_idx


def parse_markdown_table(text: str) -> list[dict] | None:
    """Parse markdown tables into list of dicts.

    Detects two tables: Table 1 (prices) and Table 2 (sources).
    Returns price rows. Sources are attached as 'dr_sources' on matching PNs.
    """
    lines = text.strip().split('\n')

    # Find ALL table headers with PN column
    table_headers = []
    for i, line in enumerate(lines):
        if '|' in line and ('PN' in line.upper() or 'PART' in line.upper()):
            # Make sure next line is a separator (confirms it's a real header)
            if i + 1 < len(lines) and re.match(r'\s*\|[\s\-:|]+\|', lines[i + 1]):
                table_headers.append(i)

    if not table_headers:
        return None

    # Parse first table (prices)
    price_rows, price_headers, end1 = _parse_single_table(lines, table_headers[0])

    # Check if the first table is actually a price table (has 'price' column)
    is_price_table = 'price' in price_headers.values()

    # Parse second table (sources) if it exists
    sources_by_pn = {}
    if len(table_headers) >= 2:
        source_rows, source_headers, _ = _parse_single_table(lines, table_headers[1])
        is_source_table = 'page_type' in source_headers.values() or 'has_price' in source_headers.values()

        if is_source_table:
            for row in source_rows:
                pn = row.get('pn', '')
                if pn:
                    if pn not in sources_by_pn:
                        sources_by_pn[pn] = []
                    sources_by_pn[pn].append({
                        "url": row.get("source_url", row.get("url", "")),
                        "page_type": row.get("page_type", ""),
                        "has_price": row.get("has_price", ""),
                        "has_specs": row.get("has_specs", ""),
                        "has_photo": row.get("has_photo", ""),
                        "domain": row.get("domain", ""),
                    })
        elif not is_price_table:
            # First table wasn't prices, second isn't sources — just concat
            price_rows.extend(source_rows)

    # Attach sources to price rows
    if sources_by_pn:
        for row in price_rows:
            pn = row.get('pn', '')
            if pn in sources_by_pn:
                row['_sources'] = sources_by_pn[pn]

    return price_rows if price_rows else None


def normalize_result(raw: dict) -> dict:
    """Normalize a parsed result into standard format."""
    pn = raw.get('pn', '').strip()
    if not pn:
        return {}

    # Parse price
    price_raw = raw.get('price', '')
    price = None
    currency = raw.get('currency', '')

    if isinstance(price_raw, (int, float)):
        price = float(price_raw)
    elif isinstance(price_raw, str):
        price_str = price_raw.strip()
        if price_str and price_str.lower() not in ('not found', 'n/a', 'null', '-', 'poa', 'на запрос'):
            # Extract number
            # Handle formats like "€627.00", "$459", "627 EUR", etc.
            currency_match = re.match(r'^([€$£₽])\s*([\d.,]+)', price_str)
            if currency_match:
                symbol_map = {'€': 'EUR', '$': 'USD', '£': 'GBP', '₽': 'RUB'}
                if not currency:
                    currency = symbol_map.get(currency_match.group(1), '')
                num_str = currency_match.group(2).replace(',', '')
                try:
                    price = float(num_str)
                except ValueError:
                    pass
            else:
                # Try plain number
                num_match = re.search(r'([\d.,]+)', price_str)
                if num_match:
                    num_str = num_match.group(1).replace(',', '')
                    try:
                        price = float(num_str)
                    except ValueError:
                        pass

    if isinstance(currency, str):
        currency = currency.strip().upper()
        if currency in ('NOT FOUND', 'N/A', 'NULL', '-', ''):
            currency = None
    else:
        currency = None

    source_url = raw.get('source_url', '')
    if isinstance(source_url, str):
        source_url = source_url.strip()
        if source_url.lower() in ('not found', 'n/a', 'null', '-', ''):
            source_url = None
    else:
        source_url = None

    image_url = raw.get('image_url', '')
    if isinstance(image_url, str):
        image_url = image_url.strip()
        if image_url.lower() in ('not found', 'n/a', 'null', '-', ''):
            image_url = None
    else:
        image_url = None

    category = raw.get('category', '')
    if isinstance(category, str):
        category = category.strip()
        if category.lower() in ('not found', 'n/a', 'null', '-', ''):
            category = None
    else:
        category = None

    price_type = raw.get('price_type', '')
    if isinstance(price_type, str):
        price_type = price_type.strip().lower()
        if price_type in ('not found', 'n/a', 'null', '-', ''):
            price_type = None
    else:
        price_type = None

    alias_found = raw.get('alias_found', '')
    if isinstance(alias_found, str):
        alias_found = alias_found.strip()
        if alias_found.lower() in ('not found', 'n/a', 'null', '-', '', 'none'):
            alias_found = None
    else:
        alias_found = None

    return {
        "pn": pn,
        "price": price,
        "currency": currency,
        "source_url": source_url,
        "category": category,
        "image_url": image_url,
        "price_type": price_type,
        "alias_found": alias_found,
        "specs": raw.get('specs'),
        "notes": raw.get('notes', ''),
        "_sources": raw.get('_sources'),
    }


def update_evidence(pn: str, result: dict, source: str) -> Path:
    """Write/update evidence file for a SKU with DR results."""
    safe_pn = re.sub(r'[\\/:*?"<>|]', "_", pn)
    ev_path = EVIDENCE_DIR / f"evidence_{safe_pn}.json"

    # Load existing evidence or create new
    if ev_path.exists():
        try:
            evidence = json.loads(ev_path.read_text("utf-8"))
        except json.JSONDecodeError:
            evidence = {}
    else:
        evidence = {}

    # Add DR results under a dedicated key (merge, don't overwrite)
    dr_key = f"deep_research_{source}"
    existing_dr = evidence.get(dr_key, {})
    new_dr = {
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "price": result["price"] or existing_dr.get("price"),
        "currency": result["currency"] or existing_dr.get("currency"),
        "source_url": result["source_url"] or existing_dr.get("source_url"),
        "category": result["category"] or existing_dr.get("category"),
        "image_url": result["image_url"] or existing_dr.get("image_url"),
        "price_type": result.get("price_type") or existing_dr.get("price_type"),
        "alias_found": result.get("alias_found") or existing_dr.get("alias_found"),
        "specs": result.get("specs") or existing_dr.get("specs"),
        "notes": result.get("notes", "") or existing_dr.get("notes", ""),
    }

    # Save sources list for training local AI
    if result.get("_sources"):
        new_dr["sources"] = result["_sources"]
    elif existing_dr.get("sources"):
        new_dr["sources"] = existing_dr["sources"]

    evidence[dr_key] = new_dr

    # Update top-level fields if DR found better data (never overwrite with empty)
    if result["price"] is not None and result["source_url"]:
        evidence["dr_price"] = result["price"]
        evidence["dr_currency"] = result["currency"]
        evidence["dr_price_source"] = result["source_url"]

    if result.get("price_type"):
        evidence["dr_price_type"] = result["price_type"]

    if result["image_url"]:
        evidence["dr_image_url"] = result["image_url"]

    if result["category"]:
        evidence["dr_category"] = result["category"]

    # Save sources to top-level for training data access
    if result.get("_sources"):
        evidence["dr_sources"] = result["_sources"]

    ev_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return ev_path


def main():
    parser = argparse.ArgumentParser(
        description="Import Deep Research response into evidence bundles"
    )
    parser.add_argument("response_file", help="Path to DR response text file")
    parser.add_argument("--source", choices=["gemini", "chatgpt", "claude"],
                        default=None, help="DR source (auto-detected from filename if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and show results without writing files")
    args = parser.parse_args()

    response_path = Path(args.response_file)
    if not response_path.exists():
        log.error(f"File not found: {response_path}")
        sys.exit(1)

    text = response_path.read_text("utf-8")
    log.info(f"Read {len(text):,} chars from {response_path.name}")

    # Auto-detect source from filename
    source = args.source
    if not source:
        fname = response_path.stem.lower()
        if 'gemini' in fname:
            source = 'gemini'
        elif 'chatgpt' in fname or 'gpt' in fname:
            source = 'chatgpt'
        elif 'claude' in fname:
            source = 'claude'
        else:
            source = 'unknown'
    log.info(f"Source: {source}")

    # Try JSON first, then markdown table
    results = parse_json_array(text)
    parse_method = "json"

    if not results:
        results = parse_markdown_table(text)
        parse_method = "markdown_table"

    if not results:
        log.error("Could not parse response. Supported formats: JSON array, markdown table.")
        log.error("Make sure the response contains a table with columns including 'PN' and 'Price'.")
        sys.exit(1)

    log.info(f"Parsed {len(results)} rows via {parse_method}")

    # Normalize and import
    imported = 0
    prices_found = 0
    skipped = 0
    import_summary = []

    for raw in results:
        normalized = normalize_result(raw)
        if not normalized or not normalized.get("pn"):
            skipped += 1
            continue

        pn = normalized["pn"]

        if args.dry_run:
            status = "PRICE" if normalized["price"] else "no_price"
            price_str = f"{normalized['currency'] or '?'} {normalized['price']}" if normalized['price'] else "-"
            print(f"  {pn:25s} {status:10s} {price_str:>15s}  {(normalized['source_url'] or '')[:50]}")
        else:
            ev_path = update_evidence(pn, normalized, source)
            imported += 1

        if normalized["price"] is not None:
            prices_found += 1

        import_summary.append({
            "pn": pn,
            "price": normalized["price"],
            "currency": normalized["currency"],
            "source_url": normalized["source_url"],
            "category": normalized["category"],
            "price_type": normalized.get("price_type"),
            "alias_found": normalized.get("alias_found"),
        })

    # Save import report
    if not args.dry_run:
        report = {
            "source": source,
            "response_file": str(response_path),
            "parse_method": parse_method,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "total_parsed": len(results),
            "imported": imported,
            "prices_found": prices_found,
            "skipped": skipped,
            "results": import_summary,
        }
        report_dir = ROOT / "research_queue" / "dr_responses"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"import_report_{source}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info(f"Import report: {report_path}")

    print(f"\n=== DR Import Summary ===")
    print(f"  Source:     {source}")
    print(f"  Parsed:     {len(results)}")
    print(f"  Imported:   {imported if not args.dry_run else 'DRY RUN'}")
    print(f"  Prices:     {prices_found}")
    print(f"  Skipped:    {skipped}")


if __name__ == "__main__":
    main()
