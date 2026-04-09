"""dr_results_import.py — Import Deep Research (DR) results from markdown files.

Reads DR result files (GPT compass and Claude deep-research) from a source directory,
parses Table 1 (product data) and Table 2 (visited URLs), and writes:
  - research_results/result_<pn>.json  (one per SKU with data)
  - training_data/dr_url_training_<date>.jsonl  (Table 2 URLs for local AI training)

Usage:
    python scripts/dr_results_import.py [--source-dir DIR] [--dry-run]

Source dir default: C:/Users/eugene/Downloads
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent.parent
RESULTS_DIR = _ROOT / "research_results"
TRAINING_DIR = _ROOT / "training_data"
EVIDENCE_DIR = _ROOT / "downloads" / "evidence"

DEFAULT_SOURCE_DIR = Path("C:/Users/eugene/Downloads")

# Files to import (relative names or patterns)
DR_FILE_PATTERNS = [
    "compass_artifact_wf-*.md",
    "deep-research-report*.md",
]

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Markdown table parser
# ---------------------------------------------------------------------------

def _parse_table_rows(lines: list[str]) -> list[dict[str, str]]:
    """Parse a markdown pipe-table into list of dicts keyed by column header."""
    header_idx = None
    for i, line in enumerate(lines):
        if re.match(r"\s*\|.*\|\s*$", line) and "---" not in line:
            # Check next line is separator
            if i + 1 < len(lines) and re.match(r"\s*\|[-|: ]+\|\s*$", lines[i + 1]):
                header_idx = i
                break

    if header_idx is None:
        return []

    # Parse headers
    header_line = lines[header_idx]
    headers = [h.strip() for h in header_line.strip("|").split("|")]

    rows = []
    for line in lines[header_idx + 2:]:  # skip header + separator
        line = line.strip()
        if not line.startswith("|"):
            break  # end of table
        cells = [c.strip() for c in line.strip("|").split("|")]
        # Pad/truncate to header length
        while len(cells) < len(headers):
            cells.append("")
        row = {headers[j]: cells[j] for j in range(len(headers))}
        rows.append(row)

    return rows


def _find_table_section(text: str, section_hint: str) -> list[str]:
    """Extract lines for a table section (Table 1 or Table 2)."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if section_hint.lower() in line.lower():
            start = i
            break

    if start is None:
        # Try to find any pipe table
        for i, line in enumerate(lines):
            if re.match(r"\s*\|\s*#\s*\|", line):
                start = max(0, i - 2)
                break

    if start is None:
        return lines  # return all, let parser figure it out

    return lines[start:]


def _clean_value(v: str) -> str:
    """Strip footnote citations like 【6†L785-L789】 and normalize."""
    v = re.sub(r"【[^】]*】", "", v)  # GPT citations
    v = re.sub(r"\[.*?\]\(.*?\)", "", v)  # markdown links (keep text? no, drop all)
    v = v.strip()
    return v


def _is_not_found(v: str) -> bool:
    """Check if a value means 'not found'."""
    clean = _clean_value(v).lower()
    return clean in ("", "not found", "n/a", "–", "-", "none", "null", "no")


# ---------------------------------------------------------------------------
# Parse Table 1 rows into standardized result dicts
# ---------------------------------------------------------------------------

def _determine_provider(filename: str) -> str:
    fn = filename.lower()
    if "compass_artifact" in fn:
        return "dr_gpt"
    if "deep-research-report" in fn or "gemini" in fn:
        return "dr_gemini"
    return "dr_claude"


def _determine_confidence(row: dict[str, str]) -> str:
    """Estimate confidence from available data."""
    has_price = not _is_not_found(row.get("Price", ""))
    has_image = not _is_not_found(row.get("Image URL", ""))
    has_category = not _is_not_found(row.get("Category", ""))

    found_count = sum([has_price, has_image, has_category])
    if found_count >= 2:
        return "medium"
    if found_count == 1:
        return "low"
    return "low"


def _build_price_value(row: dict[str, str]) -> Optional[dict]:
    price_raw = _clean_value(row.get("Price", ""))
    currency = _clean_value(row.get("Currency", ""))
    source_url = _clean_value(row.get("Source URL", ""))
    price_type = _clean_value(row.get("Price_Type", ""))

    if _is_not_found(price_raw) or _is_not_found(currency):
        return None

    # Extract numeric value
    num_match = re.search(r"[\d,]+\.?\d*", price_raw.replace(",", "."))
    if not num_match:
        return None

    try:
        amount = float(num_match.group().replace(",", ""))
    except ValueError:
        return None

    result = {
        "amount": amount,
        "currency": currency.upper()[:3],
        "unit_basis": "piece",
        "source_url": source_url if not _is_not_found(source_url) else None,
    }
    if price_type and not _is_not_found(price_type):
        result["price_type"] = price_type
    return result


_COL_ALIASES: dict[str, list[str]] = {
    "PN": ["PN", "Part Number", "Артикул"],
    "Brand": ["Brand", "Бренд"],
    "Title": ["Product Name (Russian)", "Название (рус)", "Title"],
    "Description": ["Description (Russian, 2-3 sentences)", "Description (Russian, 3-5 sentences)", "Описание (рус, 2-3 предложения)", "Description"],
    "Category": ["Category", "InSales Category", "Категория InSales", "Категория"],
    "Price": ["Price", "Цена"],
    "Currency": ["Currency", "Валюта"],
    "Source URL": ["Price Source URL", "Источник цены (URL)", "Source URL"],
    "Image URL": ["Photo URL", "Фото (URL)", "Image URL"],
    "Datasheet URL": ["Datasheet PDF URL", "Datasheet URL"],
    "Specs": ["Key Specs (structured: param: value; param: value)", "Key Specs", "Характеристики", "Specs"],
    "Certifications": ["Certifications", "Certs"],
    "EAN": ["EAN/GTIN", "EAN"],
    "Notes": ["Notes"],
    "Alias": ["Alias"],
}


def _normalize_row(row: dict[str, str]) -> dict[str, str]:
    """Map variant column names to canonical keys used in _build_result_json."""
    out = dict(row)
    for canonical, aliases in _COL_ALIASES.items():
        if canonical not in out:
            for alias in aliases:
                if alias in row and alias != canonical:
                    out[canonical] = row[alias]
                    break
    return out


def _build_result_json(row: dict[str, str], provider: str, source_file: str) -> Optional[dict]:
    """Build result_*.json dict from a Table 1 row. Returns None if no useful data."""
    row = _normalize_row(row)
    pn_raw = _clean_value(row.get("PN", ""))
    if not pn_raw:
        return None

    price_value = _build_price_value(row)
    image_url = _clean_value(row.get("Image URL", ""))
    if _is_not_found(image_url):
        image_url = None

    source_url = _clean_value(row.get("Source URL", ""))
    category = _clean_value(row.get("Category", ""))
    notes = _clean_value(row.get("Notes", "") or row.get("Description", ""))
    alias = _clean_value(row.get("Alias", ""))
    specs_raw = _clean_value(row.get("Specs", ""))

    # Skip rows with zero useful data
    has_any = price_value or image_url or (not _is_not_found(category)) or (not _is_not_found(source_url))
    if not has_any:
        return None

    # Build specs dict from raw specs string
    specs = {}
    if specs_raw and not _is_not_found(specs_raw):
        specs["raw"] = specs_raw
    if alias and not _is_not_found(alias):
        specs["aliases"] = [a.strip() for a in alias.split(";") if a.strip()]

    # Sources
    sources = []
    if not _is_not_found(source_url):
        domain = re.search(r"https?://([^/]+)", source_url)
        page_type = _clean_value(row.get("Price_Type", "distributor"))
        if _is_not_found(page_type):
            page_type = "distributor"
        supports = ["identity"]
        if price_value:
            supports.append("price")
        if image_url:
            supports.append("photo")
        sources.append({
            "url": source_url,
            "type": page_type,
            "domain": domain.group(1) if domain else "",
            "supports": supports,
        })

    price_assessment = "admissible_public_price" if price_value else "no_public_price"
    confidence = _determine_confidence(row)

    # For GPT results with "gray_market" or "surplus" price type, lower confidence
    price_type = _clean_value(row.get("Price_Type", ""))
    if price_type in ("surplus", "gray_market"):
        confidence = "low"
        price_assessment = "ambiguous_offer"

    title_ru = _clean_value(row.get("Title", "")) or (category if not _is_not_found(category) else "")
    brand = _clean_value(row.get("Brand", "")) or "Honeywell"
    datasheet_url = _clean_value(row.get("Datasheet URL", ""))
    if _is_not_found(datasheet_url):
        datasheet_url = None
    certifications = _clean_value(row.get("Certifications", ""))
    ean = _clean_value(row.get("EAN", ""))

    key_findings = []
    if notes and not _is_not_found(notes):
        key_findings.append(notes)
    if alias and not _is_not_found(alias):
        key_findings.append(f"Aliases: {alias}")
    if certifications and not _is_not_found(certifications):
        key_findings.append(f"Certifications: {certifications}")

    return {
        "result_version": "v1",
        "task_id": f"dr_import_{pn_raw}",
        "entity_id": pn_raw,
        "research_reason": "dr_import",
        "priority": "medium",
        "final_recommendation": {
            "identity_confirmed": not _is_not_found(category) or not _is_not_found(title_ru),
            "brand": brand if not _is_not_found(brand) else "Honeywell",
            "title_ru": title_ru if not _is_not_found(title_ru) else "",
            "description_ru": notes if not _is_not_found(notes) else "",
            "category_suggestion": category if not _is_not_found(category) else "",
            "price_assessment": price_assessment,
            "price_value": price_value,
            "photo_url": image_url,
            "datasheet_url": datasheet_url,
            "specs": specs,
            "key_findings": key_findings,
            "ambiguities": [],
            "sources": sources,
            "confidence": confidence,
            "confidence_notes": f"Imported from DR file {source_file}. Price: {'yes' if price_value else 'no'}, Image: {'yes' if image_url else 'no'}, Category: {'yes' if not _is_not_found(category) else 'no'}.",
            **({"ean": ean} if ean and not _is_not_found(ean) else {}),
        },
        "sources": sources,
        "confidence": confidence,
        "parse_error": "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": "gpt-4o" if provider == "dr_gpt" else "claude-opus-4",
        "raw_response_length": 0,
        "cost_usd": 0.0,
        "web_search_used": True,
        "dr_source_file": source_file,
    }


# ---------------------------------------------------------------------------
# Parse Table 2 (new format) — Documents found
# ---------------------------------------------------------------------------

def _parse_documents_table(text: str, source_file: str) -> dict[str, list[dict]]:
    """Parse documents table from new 3-table DR format.

    Returns dict: {pn: [{url, doc_type, language, description}]}
    """
    lines = text.splitlines()
    doc_table_start = None
    for i, line in enumerate(lines):
        lower = line.lower()
        if ("table 2" in lower or "documents found" in lower or "document url" in lower):
            doc_table_start = i
            break

    if doc_table_start is None:
        return {}

    rows = _parse_table_rows(lines[doc_table_start:])
    results: dict[str, list[dict]] = {}

    for row in rows:
        # Support both "Part Number" and "PN" as key
        pn = _clean_value(row.get("Part Number", "") or row.get("PN", ""))
        url = _clean_value(row.get("Document URL", "") or row.get("URL", ""))
        if not pn or not url or _is_not_found(url):
            continue
        if not url.startswith("http"):
            continue

        doc_type = _clean_value(row.get("Document Type", "") or row.get("Type", "Document"))
        language = _clean_value(row.get("Language", ""))
        description = _clean_value(row.get("Description", "") or row.get("Desc", ""))

        if _is_not_found(doc_type):
            doc_type = "Document"

        entry = {
            "url": url,
            "doc_type": doc_type,
            "language": language if not _is_not_found(language) else "",
            "description": description if not _is_not_found(description) else "",
            "source_file": source_file,
        }
        results.setdefault(pn, []).append(entry)

    return results


# ---------------------------------------------------------------------------
# Parse Table 3 (new) / Table 2 (old) — visited URLs for training data
# ---------------------------------------------------------------------------

def _parse_table2_rows(text: str, source_file: str, provider: str) -> list[dict]:
    """Parse Table 2 (visited URLs) for local AI training."""
    # Find Table 2 section
    lines = text.splitlines()
    table2_start = None
    for i, line in enumerate(lines):
        if "table 2" in line.lower() or "every url visited" in line.lower() or "посещённые" in line.lower():
            table2_start = i
            break

    if table2_start is None:
        return []

    section_lines = lines[table2_start:]
    rows = _parse_table_rows(section_lines)

    results = []
    for row in rows:
        # Support both old format (PN) and new format (Part Number)
        pn = _clean_value(row.get("PN", "") or row.get("Part Number", ""))
        url = _clean_value(row.get("URL", "") or row.get("Page URL", ""))
        if not pn or not url or _is_not_found(url):
            continue
        if not url.startswith("http"):
            continue

        has_docs_raw = _clean_value(row.get("Has_Documents", "") or row.get("Has Documents", "")).lower()

        entry = {
            "pn": pn,
            "url": url,
            "page_type": _clean_value(row.get("Page_Type", "") or row.get("Page Type", "")),
            "has_price": _clean_value(row.get("Has_Price", "") or row.get("Has Price", "")).lower() in ("yes", "да", "true"),
            "has_specs": _clean_value(row.get("Has_Specs", "") or row.get("Has Specs", "")).lower() in ("yes", "да", "true"),
            "has_photo": _clean_value(row.get("Has_Photo", "") or row.get("Has Photo", "")).lower() in ("yes", "да", "true"),
            "has_documents": has_docs_raw in ("yes", "да", "true"),
            "domain": _clean_value(row.get("Domain", "")),
            "source_file": source_file,
            "provider": provider,
            "imported_at": datetime.now(timezone.utc).isoformat(),
        }
        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Main import logic
# ---------------------------------------------------------------------------

def import_file(
    filepath: Path,
    results_dir: Path,
    training_dir: Path,
    dry_run: bool = False,
) -> dict[str, int]:
    """Import one DR markdown file. Returns counts: {written, skipped, urls}."""
    text = filepath.read_text(encoding="utf-8", errors="replace")
    filename = filepath.name
    provider = _determine_provider(filename)

    stats = {"written": 0, "skipped": 0, "urls": 0, "updated": 0}

    # --- Table 1: product data ---
    all_lines = text.splitlines()
    table1_start = None
    # Patterns that identify Table 1 header rows (various prompt versions)
    _T1_HEADER_PATTERNS = [
        # Old format: | # | PN |
        lambda line: re.search(r"\|\s*#\s*\|", line) and re.search(r"\|\s*PN\s*\|", line, re.IGNORECASE),
        # Old format: | # | or | № |
        lambda line: re.search(r"\|\s*(#|№)\s*\|", line),
        # New format: | Part Number | Brand |
        lambda line: re.search(r"\|\s*Part Number\s*\|", line, re.IGNORECASE),
        # Russian format: | Артикул | Бренд |
        lambda line: re.search(r"\|\s*Артикул\s*\|", line),
    ]
    for i, line in enumerate(all_lines):
        for pat in _T1_HEADER_PATTERNS:
            if pat(line):
                table1_start = i
                break
        if table1_start is not None:
            break

    # Collect ALL matching product data table headers
    # For Part Number / Артикул headers, also require Brand/Бренд to exclude URL tables.
    # Old-format | # | PN | tables don't have Brand but are always product data.
    def _is_product_data_header(line: str) -> bool:
        # Old format: | # | PN | — always product data
        if re.search(r"\|\s*(#|№)\s*\|", line) and re.search(r"\|\s*PN\s*\|", line, re.IGNORECASE):
            return True
        if re.search(r"\|\s*(#|№)\s*\|", line):
            return True
        # New format: Part Number or Артикул — require Brand/Бренд to exclude URL tables
        has_pn = bool(re.search(r"\|\s*(Part Number|Артикул)\s*\|", line, re.IGNORECASE))
        has_brand = bool(re.search(r"\|\s*(Brand|Бренд)\s*\|", line, re.IGNORECASE))
        return has_pn and has_brand

    all_table_starts = [i for i, line in enumerate(all_lines) if _is_product_data_header(line)]

    rows = []
    for start in all_table_starts:
        rows.extend(_parse_table_rows(all_lines[start:]))

    results_dir.mkdir(parents=True, exist_ok=True)

    for row in rows:
        norm_row = _normalize_row(row)
        pn = _clean_value(norm_row.get("PN", ""))
        if not pn or pn == "#":
            continue
        row = norm_row  # use normalized row for rest of processing

        result = _build_result_json(row, provider, filename)
        if result is None:
            stats["skipped"] += 1
            continue

        # Sanitize PN for filename
        pn_safe = re.sub(r"[^\w\.\-]", "_", pn)
        out_path = results_dir / f"result_{pn_safe}.json"

        if out_path.exists():
            # Merge: only update if new data is better
            try:
                existing = json.loads(out_path.read_text(encoding="utf-8"))
                existing_conf = {"high": 3, "medium": 2, "low": 1}.get(
                    existing.get("confidence", "low"), 1
                )
                new_conf = {"high": 3, "medium": 2, "low": 1}.get(
                    result.get("confidence", "low"), 1
                )

                # Always merge price and photo from DR if existing doesn't have them
                if not dry_run:
                    changed = False
                    ex_rec = existing.get("final_recommendation", {})
                    new_rec = result.get("final_recommendation", {})

                    if not ex_rec.get("price_value") and new_rec.get("price_value"):
                        ex_rec["price_value"] = new_rec["price_value"]
                        ex_rec["price_assessment"] = new_rec["price_assessment"]
                        changed = True

                    if not ex_rec.get("photo_url") and new_rec.get("photo_url"):
                        ex_rec["photo_url"] = new_rec["photo_url"]
                        changed = True

                    if not ex_rec.get("datasheet_url") and new_rec.get("datasheet_url"):
                        ex_rec["datasheet_url"] = new_rec["datasheet_url"]
                        changed = True

                    if not ex_rec.get("title_ru") and new_rec.get("title_ru"):
                        ex_rec["title_ru"] = new_rec["title_ru"]
                        changed = True

                    if not ex_rec.get("description_ru") and new_rec.get("description_ru"):
                        ex_rec["description_ru"] = new_rec["description_ru"]
                        changed = True

                    # Add sources from DR that aren't already there
                    existing_urls = {s.get("url") for s in ex_rec.get("sources", [])}
                    for src in new_rec.get("sources", []):
                        if src.get("url") not in existing_urls:
                            ex_rec.setdefault("sources", []).append(src)
                            changed = True

                    if changed:
                        existing["final_recommendation"] = ex_rec
                        existing["sources"] = ex_rec.get("sources", [])
                        existing["dr_source_file"] = filename
                        out_path.write_text(
                            json.dumps(existing, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1
                continue
            except Exception:
                pass  # Fall through to overwrite

        if not dry_run:
            out_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        stats["written"] += 1

    # --- Documents table (new 3-table format: Table 2 = documents) ---
    doc_map = _parse_documents_table(text, filename)
    if doc_map and not dry_run:
        for pn, docs in doc_map.items():
            pn_safe = re.sub(r"[^\w\.\-]", "_", pn)
            out_path = results_dir / f"result_{pn_safe}.json"
            if out_path.exists():
                try:
                    r = json.loads(out_path.read_text(encoding="utf-8"))
                    existing_docs = r.get("final_recommendation", {}).get("documents", [])
                    existing_urls = {d.get("url") for d in existing_docs}
                    added = [d for d in docs if d.get("url") not in existing_urls]
                    if added:
                        r.setdefault("final_recommendation", {}).setdefault("documents", []).extend(added)
                        out_path.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
    stats["docs"] = sum(len(v) for v in doc_map.values())

    # --- Sources/URLs table (Table 3 in new format, Table 2 in old format) ---
    url_rows = _parse_table2_rows(text, filename, provider)
    if url_rows:
        training_dir.mkdir(parents=True, exist_ok=True)
        training_path = training_dir / f"dr_url_training_{TODAY}.jsonl"
        if not dry_run:
            with open(training_path, "a", encoding="utf-8") as f:
                for entry in url_rows:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        stats["urls"] = len(url_rows)

    return stats


def run(
    source_dir: Path = DEFAULT_SOURCE_DIR,
    results_dir: Path = RESULTS_DIR,
    training_dir: Path = TRAINING_DIR,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict[str, int]:
    """Import all DR files from source_dir. Returns aggregate stats."""
    import glob

    files: list[Path] = []
    for pattern in DR_FILE_PATTERNS:
        files.extend(Path(source_dir).glob(pattern))

    files = sorted(set(files))

    if verbose:
        print(f"Found {len(files)} DR files in {source_dir}")

    total = {"written": 0, "skipped": 0, "urls": 0, "updated": 0, "files": 0}

    for filepath in files:
        if verbose:
            print(f"  [{filepath.name}] ... ", end="", flush=True)
        try:
            stats = import_file(filepath, results_dir, training_dir, dry_run=dry_run)
            if verbose:
                print(f"written={stats['written']}, updated={stats['updated']}, skipped={stats['skipped']}, urls={stats['urls']}")
            for k in ("written", "skipped", "urls", "updated"):
                total[k] += stats[k]
            total["files"] += 1
        except Exception as e:
            if verbose:
                print(f"ERROR: {e}")

    if verbose:
        print(f"\nTotal: {total['files']} files, {total['written']} new results, "
              f"{total['updated']} updated, {total['skipped']} skipped, {total['urls']} training URLs")

    return total


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import DR markdown results into research_results/")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR), help="Directory with DR markdown files")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't write files")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-file output")
    args = parser.parse_args()

    run(
        source_dir=Path(args.source_dir),
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )
