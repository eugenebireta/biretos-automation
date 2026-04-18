"""Use Gemini with Google Search grounding to find datasheet URLs for remaining 60 SKUs."""
from __future__ import annotations

import json
import sys
import time
import subprocess
from pathlib import Path
from urllib.parse import urlparse
import requests as http_requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
DS_DIR = ROOT / "downloads" / "datasheets_v2"

USA_VPS = "216.9.227.124"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

NEEDS_USA_VPS = ["prod-edam.honeywell", "honeywell.scene7", "honeywell.com",
                 "buildings.honeywell", "sps.honeywell"]


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


def main():
    from google import genai as genai_new
    from google.genai import types
    from scripts.app_secrets import get_secret

    client = genai_new.Client(api_key=get_secret("GEMINI_API_KEY"))
    search_config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.1,
    )

    # Find SKUs without datasheet
    no_ds = []
    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in {"---", "--", "_", "PN", "-----"}:
            continue
        pn_safe = pn.replace("/", "_").replace(" ", "_")
        if (DS_DIR / f"{pn_safe}.pdf").exists():
            continue
        brand = d.get("brand", "") or (d.get("structured_identity") or {}).get("confirmed_manufacturer", "")
        subbrand = d.get("subbrand", "")
        real_brand = subbrand or brand
        seed = (d.get("content") or {}).get("seed_name", "") or d.get("name", "")
        no_ds.append((pn, real_brand, seed))

    print(f"Finding datasheets for {len(no_ds)} SKUs via Gemini web search")
    print("=" * 90)

    stats = {"found_url": 0, "downloaded": 0, "not_found": 0, "failed": 0}

    for idx, (pn, brand, seed) in enumerate(no_ds):
        pn_safe = pn.replace("/", "_").replace(" ", "_")
        out_file = DS_DIR / f"{pn_safe}.pdf"
        if out_file.exists():
            continue

        print(f"  [{idx+1}/{len(no_ds)}] {pn:<22} ({brand})... ", end="", flush=True)

        prompt = (
            f"Find the official manufacturer datasheet PDF URL for this product:\n"
            f"  Part number: {pn}\n"
            f"  Brand: {brand}\n"
            f"  Description: {seed}\n\n"
            f"Search Google for the exact PDF URL. Return ONLY the URL in this format:\n"
            f'{{"url": "https://...", "source": "manufacturer.com"}}\n'
            f'If not found, return: {{"url": null, "source": null}}'
        )

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=search_config,
            )
            text = response.text.strip() if response.text else ""

            # Extract URL
            import re
            url_match = re.search(r'https?://\S+\.pdf', text)
            if not url_match:
                stats["not_found"] += 1
                print("no URL found")
                time.sleep(8)
                continue

            url = url_match.group().rstrip('",;)')
            stats["found_url"] += 1

            # Download
            domain = urlparse(url).netloc.replace("www.", "")
            use_vps = any(d in domain for d in NEEDS_USA_VPS)

            if use_vps:
                ok = download_via_vps(url, out_file)
            else:
                ok = download_direct(url, out_file)

            if ok:
                size_kb = out_file.stat().st_size // 1024
                print(f"OK ({size_kb} KB) from {domain}")
                stats["downloaded"] += 1
            else:
                print(f"download failed ({domain})")
                stats["failed"] += 1

        except Exception as e:
            print(f"ERROR: {str(e)[:60]}")
            stats["failed"] += 1

        time.sleep(10)

    print(f"\nStats: found_url={stats['found_url']}, downloaded={stats['downloaded']}, "
          f"not_found={stats['not_found']}, failed={stats['failed']}")


if __name__ == "__main__":
    main()
