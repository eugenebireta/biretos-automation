"""
download_documents.py — Download all product documents found by Deep Research.

Reads research_results/result_*.json, finds document URLs in:
  - final_recommendation.datasheet_url
  - final_recommendation.documents (list of {url, doc_type, language})
  - deep_research.documents (same)

Downloads to:
  downloads/documents/{PN}/{doc_type}_{n}.pdf  (or .jpg/.png for drawings)

Updates evidence file:
  evidence.documents = [
    {"doc_type": "Datasheet", "local_path": "...", "url": "...", "language": "en",
     "status": "downloaded", "size_bytes": N, "pages": N, "description": "..."}
  ]

Also extracts from PDFs (via PyMuPDF):
  - specs dict  → evidence.deep_research.specs (merged, not overwritten)
  - text excerpt → evidence.deep_research.datasheet_text (first 2000 chars)

Usage:
    python scripts/download_documents.py [--dry-run] [--pn PN] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "research_results"
EVIDENCE_DIR = ROOT / "downloads" / "evidence"
DOCS_DIR = ROOT / "downloads" / "documents"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
}

# Document types we recognize
KNOWN_DOC_TYPES = {
    "datasheet", "installation manual", "wiring diagram", "installation guide",
    "ce declaration", "atex certificate", "iecex certificate", "ul certificate",
    "safety data sheet", "sds", "product bulletin", "brochure",
    "quick start guide", "programming guide", "dimensional drawing",
    "user manual", "technical manual", "operating manual",
}

# Max file size to download (50 MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# Min file size (skip tiny files — likely error pages)
MIN_FILE_SIZE = 5 * 1024  # 5 KB


def _safe_filename(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", s)


def _safe_doc_type(doc_type: str) -> str:
    """Normalize doc type to safe filename part."""
    return re.sub(r"[^\w]", "_", doc_type.lower()).strip("_")[:30]


def _guess_extension(url: str, content_type: str = "") -> str:
    """Guess file extension from URL and content-type."""
    low_url = url.lower().split("?")[0]
    if low_url.endswith(".pdf"):
        return ".pdf"
    if low_url.endswith(".png"):
        return ".png"
    if low_url.endswith((".jpg", ".jpeg")):
        return ".jpg"
    if low_url.endswith(".zip"):
        return ".zip"
    if "pdf" in content_type:
        return ".pdf"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    if "png" in content_type:
        return ".png"
    return ".pdf"  # default for docs


def download_file(url: str, dest: Path, timeout: int = 30) -> dict:
    """Download a file to dest. Returns status dict."""
    if not url or not url.startswith("http"):
        return {"status": "skip", "reason": "invalid url"}

    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout, stream=True)
        if resp.status_code == 404:
            return {"status": "not_found", "reason": "HTTP 404"}
        if resp.status_code == 403:
            return {"status": "blocked", "reason": "HTTP 403"}
        if resp.status_code != 200:
            return {"status": "error", "reason": f"HTTP {resp.status_code}"}

        content_type = resp.headers.get("content-type", "")

        # Check content-length if available
        content_length = resp.headers.get("content-length")
        if content_length and int(content_length) > MAX_FILE_SIZE:
            return {"status": "skip", "reason": "file too large"}

        data = b""
        for chunk in resp.iter_content(chunk_size=65536):
            data += chunk
            if len(data) > MAX_FILE_SIZE:
                return {"status": "skip", "reason": "file too large"}

        if len(data) < MIN_FILE_SIZE:
            return {"status": "skip", "reason": f"file too small ({len(data)} bytes)"}

        # Determine extension
        ext = _guess_extension(url, content_type)
        final_dest = dest.with_suffix(ext)
        final_dest.parent.mkdir(parents=True, exist_ok=True)
        final_dest.write_bytes(data)

        try:
            local_path = str(final_dest.relative_to(ROOT))
        except ValueError:
            local_path = str(final_dest)

        return {
            "status": "downloaded",
            "local_path": local_path,
            "size_bytes": len(data),
            "content_type": content_type,
            "extension": ext,
        }

    except requests.Timeout:
        return {"status": "error", "reason": "timeout"}
    except requests.RequestException as e:
        return {"status": "error", "reason": str(e)[:100]}


def extract_pdf_data(local_path: Path) -> dict:
    """Extract text, specs, and page count from a PDF using PyMuPDF."""
    result = {"pages": 0, "text_excerpt": "", "specs": {}}
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(local_path))
        result["pages"] = len(doc)

        # Extract text from first 3 pages
        texts = []
        for i in range(min(3, len(doc))):
            page_text = doc[i].get_text("text")
            if page_text:
                texts.append(page_text)
        full_text = "\n".join(texts)
        result["text_excerpt"] = full_text[:3000]

        # Extract specs: look for "key: value" patterns
        specs = {}
        for line in full_text.splitlines():
            line = line.strip()
            # Pattern: "Label: Value" or "Label ............... Value"
            m = re.match(r"^([A-Za-zА-Яа-я][A-Za-zА-Яа-я\s/\-]{2,40}):\s*(.{1,80})$", line)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                if val and len(val) > 0:
                    specs[key] = val
        result["specs"] = specs

        doc.close()
    except Exception as e:
        log.debug(f"PDF parse error: {e}")

    return result


def collect_doc_urls(result: dict) -> list[dict]:
    """Collect all document URLs from a research result."""
    docs = []
    fr = result.get("final_recommendation", {})
    dr = result.get("deep_research", {})

    # Direct datasheet_url field
    for field, doc_type in [
        ("datasheet_url", "Datasheet"),
        ("manual_url", "Installation Manual"),
        ("certificate_url", "CE Declaration"),
    ]:
        url = fr.get(field) or dr.get(field)
        if url and isinstance(url, str) and url.startswith("http"):
            docs.append({"url": url, "doc_type": doc_type, "language": "en", "description": ""})

    # documents list (from new prompt format Table 2)
    for doc_list_field in ["documents", "docs"]:
        for source in [fr, dr]:
            doc_list = source.get(doc_list_field, [])
            if isinstance(doc_list, list):
                for item in doc_list:
                    if isinstance(item, dict) and item.get("url", "").startswith("http"):
                        docs.append({
                            "url": item["url"],
                            "doc_type": item.get("doc_type") or item.get("type") or "Document",
                            "language": item.get("language", ""),
                            "description": item.get("description") or item.get("desc") or "",
                        })

    # Deduplicate by URL
    seen = set()
    unique = []
    for d in docs:
        url = d["url"]
        if url not in seen:
            seen.add(url)
            unique.append(d)

    return unique


def process_one(pn: str, dry_run: bool = False) -> dict:
    """Download all documents for one PN. Returns status dict."""
    pn_safe = _safe_filename(pn)

    # Load research result
    result_path = RESULTS_DIR / f"result_{pn_safe}.json"
    if not result_path.exists():
        return {"pn": pn, "action": "no_result", "docs": []}

    result = json.loads(result_path.read_text(encoding="utf-8"))
    doc_urls = collect_doc_urls(result)

    if not doc_urls:
        return {"pn": pn, "action": "no_docs", "docs": []}

    # Load evidence file
    ev_path = EVIDENCE_DIR / f"evidence_{pn_safe}.json"
    evidence = {}
    if ev_path.exists():
        try:
            evidence = json.loads(ev_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing_urls = {d.get("url") for d in evidence.get("documents", [])}

    downloaded = []
    for i, doc in enumerate(doc_urls):
        url = doc["url"]
        doc_type = doc.get("doc_type", "Document")
        language = doc.get("language", "")
        description = doc.get("description", "")

        if url in existing_urls:
            log.info(f"  [{pn}] skip (already have): {url[:70]}")
            continue

        log.info(f"  [{pn}] {doc_type}: {url[:80]}")

        doc_type_safe = _safe_doc_type(doc_type)
        dest_stem = DOCS_DIR / pn_safe / f"{doc_type_safe}_{i+1}"

        if dry_run:
            downloaded.append({
                "doc_type": doc_type, "url": url, "language": language,
                "description": description, "status": "dry_run",
            })
            continue

        dl = download_file(url, dest_stem)
        entry = {
            "doc_type": doc_type,
            "url": url,
            "language": language,
            "description": description,
            "status": dl["status"],
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }

        if dl["status"] == "downloaded":
            local_path = dl["local_path"]
            entry["local_path"] = local_path
            entry["size_bytes"] = dl["size_bytes"]

            # Parse PDF if it's a PDF
            full_local = ROOT / local_path
            if full_local.suffix == ".pdf":
                pdf_data = extract_pdf_data(full_local)
                entry["pages"] = pdf_data["pages"]

                # Merge specs into deep_research
                if pdf_data["specs"]:
                    dr = evidence.setdefault("deep_research", {})
                    existing_specs = dr.get("specs") or {}
                    if not existing_specs:
                        dr["specs"] = pdf_data["specs"]
                    elif isinstance(existing_specs, dict):
                        # Add keys not already present
                        for k, v in pdf_data["specs"].items():
                            if k not in existing_specs:
                                existing_specs[k] = v

                # Store text excerpt for datasheet
                if doc_type.lower() == "datasheet" and pdf_data["text_excerpt"]:
                    dr = evidence.setdefault("deep_research", {})
                    if not dr.get("datasheet_text"):
                        dr["datasheet_text"] = pdf_data["text_excerpt"]

        downloaded.append(entry)
        time.sleep(0.5)  # polite delay

    if not dry_run and downloaded:
        # Update evidence file
        existing_docs = evidence.get("documents", [])
        existing_docs.extend(d for d in downloaded if d["status"] == "downloaded")
        evidence["documents"] = existing_docs
        evidence["documents_updated_at"] = datetime.now(timezone.utc).isoformat()
        ev_path.write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return {"pn": pn, "action": "processed", "docs": downloaded}


def run(dry_run: bool = False, pn_filter: str | None = None, limit: int = 0) -> dict:
    """Run document downloader for all result files."""
    result_files = sorted(RESULTS_DIR.glob("result_*.json"))
    pns = [f.stem.replace("result_", "") for f in result_files]

    if pn_filter:
        pns = [p for p in pns if p == pn_filter]

    if limit:
        pns = pns[:limit]

    stats = {
        "total_pns": len(pns),
        "downloaded": 0,
        "skipped": 0,
        "errors": 0,
        "no_docs": 0,
        "dry_run": dry_run,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    for pn in pns:
        result = process_one(pn, dry_run=dry_run)
        for doc in result.get("docs", []):
            s = doc.get("status", "")
            if s == "downloaded":
                stats["downloaded"] += 1
            elif s in ("skip", "dry_run"):
                stats["skipped"] += 1
            elif s in ("error", "not_found", "blocked"):
                stats["errors"] += 1
        if result["action"] == "no_docs":
            stats["no_docs"] += 1

    log.info(
        f"Done: {stats['downloaded']} downloaded, {stats['errors']} errors, "
        f"{stats['no_docs']} PNs with no docs found"
    )
    return stats


def main():
    parser = argparse.ArgumentParser(description="Download product documents from DR results")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded")
    parser.add_argument("--pn", type=str, default=None, help="Process only this PN")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N PNs")
    args = parser.parse_args()

    stats = run(dry_run=args.dry_run, pn_filter=args.pn, limit=args.limit)
    print(json.dumps(stats, indent=2, ensure_ascii=False))

    if args.dry_run:
        print("\n[DRY RUN] No files downloaded.")


if __name__ == "__main__":
    main()
