"""Re-download correct datasheets for SKUs marked needs_new_datasheet."""
from __future__ import annotations

import json
import sys
import time
import subprocess
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import requests as http_requests

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
DS_DIR = ROOT / "downloads" / "datasheets_v2"
DS_DIR_OLD = ROOT / "downloads" / "datasheets_v2_wrong"
DS_DIR_OLD.mkdir(parents=True, exist_ok=True)

USA_VPS = "216.9.227.124"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def download_via_vps(url: str, local_path: Path) -> bool:
    try:
        subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", f"root@{USA_VPS}",
             f"curl -sL -o /tmp/{local_path.name} -H 'User-Agent: Mozilla/5.0' '{url}'"],
            capture_output=True, timeout=60, encoding="utf-8", errors="replace",
        )
        subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no",
             f"root@{USA_VPS}:/tmp/{local_path.name}", str(local_path)],
            capture_output=True, timeout=30,
        )
        return local_path.exists() and local_path.stat().st_size > 1000
    except Exception:
        return False


def download_direct(url: str, local_path: Path) -> bool:
    try:
        r = http_requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 1000 and r.content[:4] == b"%PDF":
            local_path.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False


def search_datasheet(pn: str, brand: str, api_key: str) -> list:
    """Smart SerpAPI search with multiple query variants."""
    queries = [
        f'"{pn}" datasheet {brand} filetype:pdf',
        f'"{pn}" {brand} data sheet filetype:pdf',
        f'{brand} {pn} specifications filetype:pdf',
    ]

    all_results = []
    for q in queries:
        try:
            resp = http_requests.get("https://serpapi.com/search", params={
                "q": q, "engine": "google", "api_key": api_key,
                "num": 5, "gl": "de", "hl": "en",
            }, timeout=25)
            organic = resp.json().get("organic_results", [])
            for r in organic:
                url = r.get("link", "")
                title = r.get("title", "")
                # Must be PDF and contain the PN in title
                if ".pdf" in url.lower():
                    pn_clean = pn.lower().replace("-", "").replace(".", "")
                    title_clean = title.lower().replace("-", "").replace(".", "")
                    if pn_clean in title_clean or pn.lower() in title.lower():
                        all_results.append({"url": url, "title": title})
        except Exception:
            continue
        time.sleep(2)
    return all_results


def main():
    from scripts.app_secrets import get_secret
    api_key = get_secret("SERPAPI_KEY")

    needs_new = []
    for f in EV_DIR.glob("evidence_*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        fd = d.get("from_datasheet", {})
        corr = fd.get("_corrections", {})
        if corr.get("needs_new_datasheet"):
            pn = d.get("pn", "")
            si = d.get("structured_identity") or {}
            brand = d.get("brand", "") or si.get("confirmed_manufacturer", "")
            seed = (d.get("content") or {}).get("seed_name", "") or d.get("name", "")
            needs_new.append((pn, brand, seed, fd))

    print(f"Re-downloading {len(needs_new)} wrong datasheets")
    print("=" * 80)

    stats = {"found": 0, "downloaded": 0, "no_results": 0, "failed": 0}

    for pn, brand, seed, fd in needs_new:
        pn_safe = pn.replace("/", "_").replace(" ", "_")
        print(f"\n  {pn} ({brand})...")

        # Backup old wrong PDF
        old_pdf = DS_DIR / f"{pn_safe}.pdf"
        if old_pdf.exists():
            backup = DS_DIR_OLD / f"{pn_safe}_wrong.pdf"
            old_pdf.rename(backup)
            print(f"    Moved old wrong PDF to {backup.name}")

        # Search
        results = search_datasheet(pn, brand, api_key)
        if not results:
            print("    No new PDF found")
            stats["no_results"] += 1
            continue

        stats["found"] += 1
        # Try download
        downloaded = False
        for r in results[:3]:
            url = r["url"]
            domain = urlparse(url).netloc.replace("www.", "")
            use_vps = any(d in domain for d in [
                "prod-edam.honeywell.com", "honeywell.scene7.com",
                "buildings.honeywell.com", "automation.honeywell.com",
                "sps.honeywell.com", "honeywellsafety.com",
            ])

            new_pdf = DS_DIR / f"{pn_safe}.pdf"
            ok = download_via_vps(url, new_pdf) if use_vps else download_direct(url, new_pdf)

            if ok:
                size_kb = new_pdf.stat().st_size // 1024
                print(f"    OK: downloaded {size_kb} KB from {domain}")
                stats["downloaded"] += 1
                downloaded = True
                # Clear needs_new_datasheet flag
                ev_file = EV_DIR / f"evidence_{pn_safe}.json"
                if ev_file.exists():
                    d = json.loads(ev_file.read_text(encoding="utf-8"))
                    fd2 = d.get("from_datasheet", {})
                    corr = fd2.get("_corrections", {})
                    corr["needs_new_datasheet"] = False
                    corr["redownloaded_from"] = url
                    corr["redownloaded_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    fd2["_corrections"] = corr
                    fd2["datasheet_pdf"] = str(new_pdf.relative_to(ROOT))
                    fd2["datasheet_size_kb"] = size_kb
                    d["from_datasheet"] = fd2
                    ev_file.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
                break

            time.sleep(1)

        if not downloaded:
            print(f"    All {len(results)} download attempts failed")
            stats["failed"] += 1

        time.sleep(6)

    print("\n" + "=" * 80)
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
