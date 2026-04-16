"""SerpAPI datasheet search for SKUs without PDF links.

Searches Google for "{brand} {pn} datasheet filetype:pdf"
Downloads found PDFs directly or via USA VPS.
Tracks statistics: which search patterns and domains give best results.

Pauses 10 sec between requests.
"""
from __future__ import annotations

import json
import re
import sys
import io
import time
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from collections import Counter, defaultdict
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.app_secrets import get_secret
import requests as http_requests

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
DS_DIR = ROOT / "downloads" / "datasheets_v2"
STATS_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "datasheet_search_stats.json"

SERPAPI_KEY = get_secret("SERPAPI_KEY")
USA_VPS = "216.9.227.124"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

NEEDS_USA_VPS = [
    "prod-edam.honeywell.com", "honeywell.scene7.com",
    "buildings.honeywell.com", "automation.honeywell.com",
    "sps.honeywell.com", "sps-support.honeywell.com",
    "process.honeywell.com", "honeywell.com",
]

SKIP_PNS = {"---", "--", "_", "PN", "-----", ""}

# Statistics tracking
stats = {
    "search_patterns": Counter(),    # which query pattern found results
    "domains_found": Counter(),      # which domains had PDFs
    "domains_downloaded": Counter(), # which domains successfully downloaded
    "domains_failed": Counter(),     # which domains failed to download
    "method_success": Counter(),     # direct vs usa_vps
    "brand_coverage": defaultdict(lambda: {"searched": 0, "found": 0, "downloaded": 0}),
    "total_searched": 0,
    "total_found": 0,
    "total_downloaded": 0,
    "total_failed": 0,
    "total_no_results": 0,
}


def needs_vps(url: str) -> bool:
    domain = urlparse(url).netloc.replace("www.", "")
    return any(d in domain for d in NEEDS_USA_VPS)


def download_via_vps(url: str, local_path: Path) -> bool:
    remote_tmp = f"/tmp/dl_{local_path.name}"
    try:
        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", f"root@{USA_VPS}",
             f"curl -sL -o {remote_tmp} -w '%{{http_code}}' -H 'User-Agent: Mozilla/5.0' '{url}'"],
            capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace",
        )
        status = result.stdout.strip().replace("'", "")
        if status != "200":
            return False
        subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no",
             f"root@{USA_VPS}:{remote_tmp}", str(local_path)],
            capture_output=True, timeout=30,
        )
        subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", f"root@{USA_VPS}",
             f"rm -f {remote_tmp}"],
            capture_output=True, timeout=10,
        )
        return local_path.exists() and local_path.stat().st_size > 1000
    except Exception:
        return False


def download_direct(url: str, local_path: Path) -> bool:
    try:
        r = http_requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 1000:
            local_path.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False


def search_datasheet(pn: str, brand: str, seed_name: str) -> list[dict]:
    """Search Google for datasheet PDF. Try multiple query patterns."""
    results_all = []

    # Pattern 1: brand + pn + datasheet + filetype:pdf
    query = f"{brand} {pn} datasheet filetype:pdf"
    pattern_name = "brand_pn_datasheet_pdf"

    try:
        resp = http_requests.get("https://serpapi.com/search", params={
            "q": query, "engine": "google", "api_key": SERPAPI_KEY,
            "num": 5, "gl": "de", "hl": "en",
        }, timeout=30)
        data = resp.json()
        organic = data.get("organic_results", [])

        for r in organic[:5]:
            url = r.get("link", "")
            title = r.get("title", "")
            domain = urlparse(url).netloc.replace("www.", "")

            if ".pdf" in url.lower() or "pdf" in title.lower():
                results_all.append({
                    "url": url, "domain": domain, "title": title,
                    "pattern": pattern_name,
                })
                stats["search_patterns"][pattern_name] += 1
                stats["domains_found"][domain] += 1

    except Exception:
        pass

    return results_all


def main():
    DS_DIR.mkdir(parents=True, exist_ok=True)
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Find SKUs without datasheets
    to_search = []
    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in SKIP_PNS:
            continue

        pn_safe = pn.replace("/", "_").replace(" ", "_")
        if (DS_DIR / f"{pn_safe}.pdf").exists():
            continue

        raw = json.dumps(d)
        if re.findall(r"https?://[^\s\"<>]+\.pdf", raw, re.IGNORECASE):
            continue  # already has PDF URLs (handled by night_batch)

        brand = d.get("brand", "") or (d.get("structured_identity") or {}).get("confirmed_manufacturer", "")
        seed = (d.get("content") or {}).get("seed_name", "") or d.get("name", "")
        to_search.append((pn, brand, seed))

    print(f"Datasheet SerpAPI search: {len(to_search)} SKUs")
    print("=" * 90)

    for idx, (pn, brand, seed) in enumerate(to_search):
        pn_safe = pn.replace("/", "_").replace(" ", "_")
        out_file = DS_DIR / f"{pn_safe}.pdf"

        if out_file.exists():
            continue

        stats["total_searched"] += 1
        stats["brand_coverage"][brand]["searched"] += 1

        print(f"  [{idx+1}/{len(to_search)}] {pn:<22} ({brand})... ", end="", flush=True)

        # Search
        results = search_datasheet(pn, brand, seed)

        if not results:
            stats["total_no_results"] += 1
            print("no PDF found")
            time.sleep(10)
            continue

        stats["total_found"] += 1
        stats["brand_coverage"][brand]["found"] += 1

        # Try to download first result
        downloaded = False
        for r in results[:3]:
            url = r["url"]
            domain = r["domain"]

            # Clean URL
            url = url.split("?download=")[0]

            if needs_vps(url):
                ok = download_via_vps(url, out_file)
                method = "usa_vps"
            else:
                ok = download_direct(url, out_file)
                method = "direct"

            if ok:
                size_kb = out_file.stat().st_size // 1024
                print(f"OK ({size_kb} KB) from {domain} [{method}]")
                stats["total_downloaded"] += 1
                stats["domains_downloaded"][domain] += 1
                stats["method_success"][method] += 1
                stats["brand_coverage"][brand]["downloaded"] += 1
                downloaded = True
                break
            else:
                stats["domains_failed"][domain] += 1

            time.sleep(2)

        if not downloaded:
            stats["total_failed"] += 1
            print(f"download failed ({results[0]['domain']})")

        # Save stats periodically
        if (idx + 1) % 10 == 0:
            _save_stats()

        time.sleep(10)  # 10 sec between searches

    _save_stats()
    _print_stats()


def _save_stats():
    serializable = {
        "search_patterns": dict(stats["search_patterns"]),
        "domains_found": dict(stats["domains_found"].most_common(30)),
        "domains_downloaded": dict(stats["domains_downloaded"].most_common(30)),
        "domains_failed": dict(stats["domains_failed"].most_common(20)),
        "method_success": dict(stats["method_success"]),
        "brand_coverage": {b: dict(v) for b, v in stats["brand_coverage"].items()},
        "total_searched": stats["total_searched"],
        "total_found": stats["total_found"],
        "total_downloaded": stats["total_downloaded"],
        "total_failed": stats["total_failed"],
        "total_no_results": stats["total_no_results"],
        "timestamp": datetime.now().isoformat(),
    }
    STATS_FILE.write_text(json.dumps(serializable, indent=2, ensure_ascii=False), encoding="utf-8")


def _print_stats():
    print("\n" + "=" * 90)
    print("DATASHEET SEARCH STATISTICS")
    print("=" * 90)
    print(f"  Searched:     {stats['total_searched']}")
    print(f"  Found PDF:    {stats['total_found']}")
    print(f"  Downloaded:   {stats['total_downloaded']}")
    print(f"  Failed DL:    {stats['total_failed']}")
    print(f"  No results:   {stats['total_no_results']}")

    print("\n  Top domains providing datasheets:")
    for dom, cnt in stats["domains_downloaded"].most_common(10):
        print(f"    {dom:<40} {cnt} downloads")

    print("\n  Top domains found but failed:")
    for dom, cnt in stats["domains_failed"].most_common(10):
        print(f"    {dom:<40} {cnt} failures")

    print("\n  Download method success:")
    for method, cnt in stats["method_success"].most_common():
        print(f"    {method:<20} {cnt}")

    print("\n  Brand coverage:")
    for brand, data in sorted(stats["brand_coverage"].items(), key=lambda x: -x[1]["searched"]):
        s, f, d = data["searched"], data["found"], data["downloaded"]
        print(f"    {brand:<20} searched={s:<4} found={f:<4} downloaded={d}")

    print(f"\n  Stats saved: {STATS_FILE}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Saving stats...")
        _save_stats()
        _print_stats()
    except Exception as e:
        print(f"\nERROR: {e}")
        _save_stats()
        _print_stats()
