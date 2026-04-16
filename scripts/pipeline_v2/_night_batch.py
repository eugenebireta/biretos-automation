"""Night batch: download ALL datasheets + scene7 photos for 370 SKUs.

1. Find all PDF URLs in evidence
2. Download via USA VPS (for Honeywell) or direct (for others)
3. Find all scene7/CDN photo URLs
4. Download photos via USA VPS
5. Parse downloaded PDFs via Gemini
6. Pauses between requests to avoid bans

Run: python scripts/pipeline_v2/_night_batch.py
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

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
DS_DIR = ROOT / "downloads" / "datasheets_v2"
SCENE7_DIR = ROOT / "downloads" / "staging" / "scene7_photos"
TRUST_CONFIG = json.loads((ROOT / "config" / "seed_source_trust.json").read_text(encoding="utf-8"))

DS_DIR.mkdir(parents=True, exist_ok=True)
SCENE7_DIR.mkdir(parents=True, exist_ok=True)

USA_VPS = "216.9.227.124"
USA_VPS_USER = "root"

# Domains that need USA VPS (blocked from Russia)
NEEDS_USA_VPS = [
    "prod-edam.honeywell.com",
    "honeywell.scene7.com",
    "buildings.honeywell.com",
    "automation.honeywell.com",
    "sps.honeywell.com",
    "sps-support.honeywell.com",
    "process.honeywell.com",
    "honeywell.com",
]

SKIP_PNS = {"---", "--", "_", "PN", "-----", ""}

import requests
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def needs_usa_vps(url: str) -> bool:
    domain = urlparse(url).netloc.replace("www.", "")
    return any(d in domain for d in NEEDS_USA_VPS)


def download_via_vps(url: str, local_path: Path) -> bool:
    """Download file via USA VPS using SSH+curl."""
    remote_tmp = f"/tmp/dl_{local_path.name}"
    try:
        # Download on VPS
        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no",
             f"{USA_VPS_USER}@{USA_VPS}",
             f"curl -sL -o {remote_tmp} -w '%{{http_code}}' -H 'User-Agent: Mozilla/5.0' '{url}'"],
            capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace",
        )
        status = result.stdout.strip().replace("'", "")
        if status != "200":
            return False

        # Copy to local
        subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no",
             f"{USA_VPS_USER}@{USA_VPS}:{remote_tmp}", str(local_path)],
            capture_output=True, timeout=30,
        )

        # Cleanup remote
        subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no",
             f"{USA_VPS_USER}@{USA_VPS}", f"rm -f {remote_tmp}"],
            capture_output=True, timeout=10,
        )
        return local_path.exists() and local_path.stat().st_size > 1000
    except Exception:
        return False


def download_direct(url: str, local_path: Path) -> bool:
    """Download file directly."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 1000:
            # Check it's PDF
            if local_path.suffix == ".pdf" and not r.content[:4] == b"%PDF":
                if b"application/pdf" not in r.headers.get("content-type", "").encode():
                    return False
            local_path.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False


def phase1_download_datasheets():
    """Find and download all PDF datasheets from evidence."""
    print("=" * 90)
    print("PHASE 1: Download datasheets for 370 SKUs")
    print("=" * 90)

    stats = {"already": 0, "downloaded": 0, "failed": 0, "no_pdf": 0}

    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in SKIP_PNS:
            continue

        pn_safe = pn.replace("/", "_").replace(" ", "_")
        out_file = DS_DIR / f"{pn_safe}.pdf"

        if out_file.exists() and out_file.stat().st_size > 1000:
            stats["already"] += 1
            continue

        # Find PDF URLs
        raw = json.dumps(d)
        pdf_urls = list(set(re.findall(r"https?://[^\s\"<>]+\.pdf[^\s\"<>]*", raw, re.IGNORECASE)))

        if not pdf_urls:
            stats["no_pdf"] += 1
            continue

        # Sort: non-blocked first
        def sort_key(url):
            if needs_usa_vps(url):
                return 1  # try direct first, VPS second
            return 0
        pdf_urls.sort(key=sort_key)

        success = False
        for url in pdf_urls[:3]:  # try max 3 URLs
            # Clean URL
            url = url.split("?download=")[0]  # remove ?download=false

            if needs_usa_vps(url):
                ok = download_via_vps(url, out_file)
            else:
                ok = download_direct(url, out_file)

            if ok:
                size_kb = out_file.stat().st_size // 1024
                domain = urlparse(url).netloc.replace("www.", "")
                print(f"  {pn:<22} OK ({size_kb} KB) from {domain}")
                stats["downloaded"] += 1
                success = True
                break

            time.sleep(1)  # pause between attempts

        if not success:
            stats["failed"] += 1

        time.sleep(10)  # 10 sec between SKUs to avoid bans

    print(f"\nDatasheets: {stats['downloaded']} new + {stats['already']} existing, "
          f"{stats['failed']} failed, {stats['no_pdf']} no PDF URL")
    return stats


def phase2_download_scene7():
    """Download all scene7 product photos."""
    print("\n" + "=" * 90)
    print("PHASE 2: Download scene7 photos")
    print("=" * 90)

    scene7_urls = {}
    for f in EV_DIR.glob("evidence_*.json"):
        raw = f.read_text(encoding="utf-8")
        urls = re.findall(r"https?://honeywell\.scene7\.com/[^\s\"<>]+", raw)
        if urls:
            d = json.loads(raw)
            pn = d.get("pn", "")
            if pn and pn not in SKIP_PNS:
                scene7_urls[pn] = urls[0]

    stats = {"already": 0, "downloaded": 0, "failed": 0}

    for pn, url in sorted(scene7_urls.items()):
        pn_safe = pn.replace("/", "_").replace(" ", "_")
        out_file = SCENE7_DIR / f"{pn_safe}.jpg"

        if out_file.exists() and out_file.stat().st_size > 1000:
            stats["already"] += 1
            continue

        # Add size params
        full_url = url + "?wid=800&hei=800" if "?" not in url else url

        ok = download_via_vps(full_url, out_file)
        if ok:
            size_kb = out_file.stat().st_size // 1024
            print(f"  {pn:<22} OK ({size_kb} KB)")
            stats["downloaded"] += 1
        else:
            stats["failed"] += 1

        time.sleep(10)  # 10 sec between CDN requests to avoid bans

    print(f"\nScene7 photos: {stats['downloaded']} new + {stats['already']} existing, "
          f"{stats['failed']} failed")
    return stats


def phase3_find_other_cdns():
    """Scan evidence for other image CDNs similar to scene7."""
    print("\n" + "=" * 90)
    print("PHASE 3: Scan for other product image CDNs")
    print("=" * 90)

    from collections import Counter
    cdn_counter = Counter()

    image_patterns = re.compile(
        r"https?://[^\s\"<>]+\.(jpg|jpeg|png|webp)",
        re.IGNORECASE,
    )

    for f in EV_DIR.glob("evidence_*.json"):
        raw = f.read_text(encoding="utf-8")
        image_patterns.findall(raw)
        # Get full URLs
        full_urls = re.findall(r"https?://[^\s\"<>]+\.(?:jpg|jpeg|png|webp)", raw, re.IGNORECASE)
        for url in full_urls:
            domain = urlparse(url).netloc.replace("www.", "")
            # Filter out known noise
            if any(x in domain for x in ["dev.bireta.ru", "insales-cdn", "google", "facebook"]):
                continue
            cdn_counter[domain] += 1

    print("Image hosting domains (5+ refs):")
    for domain, cnt in cdn_counter.most_common(30):
        if cnt >= 5:
            print(f"  {domain:<40} {cnt} images")


def phase4_parse_datasheets():
    """Parse downloaded PDFs via Gemini."""
    print("\n" + "=" * 90)
    print("PHASE 4: Parse datasheets via Gemini")
    print("=" * 90)

    try:
        import google.generativeai as genai
        from scripts.app_secrets import get_secret
        genai.configure(api_key=get_secret("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-2.5-flash")
    except Exception as e:
        print(f"Gemini init failed: {e}")
        return

    PROMPT = (
        "IMPORTANT: Read ALL pages of this PDF, not just the first page.\n"
        "EAN codes, article numbers, and part numbers are often on page 2 or later.\n\n"
        "This is a product datasheet PDF. Extract ALL available data from EVERY page.\n"
        "Return ONLY a valid JSON object:\n"
        '{"pn":"","article_no":"","brand":"","title":"","description":"",\n'
        '"specs":{},"ean":"","dimensions_mm":"","weight_g":"",\n'
        '"series":"","category":"","certifications":[]}\n\n'
        "Extract pn (Material Number), article_no, ean (EAN-code/GTIN),\n"
        "ALL specs: dimensions, weight, voltage, current, temperature range,\n"
        "IP rating, material, color, mounting type. Check EVERY page."
    )

    # Load existing results
    results_file = ROOT / "downloads" / "staging" / "tier_collector_output" / "datasheet_extracted.json"
    existing = json.loads(results_file.read_text(encoding="utf-8")) if results_file.exists() else {}

    pdfs = sorted(DS_DIR.glob("*.pdf"))
    pdfs = [p for p in pdfs if "catalog" not in p.stem.lower()]

    # Only parse new ones
    new_pdfs = [p for p in pdfs if p.stem not in existing]
    print(f"Total PDFs: {len(pdfs)}, already parsed: {len(existing)}, new: {len(new_pdfs)}")

    for pdf in new_pdfs:
        pn = pdf.stem
        size_kb = pdf.stat().st_size // 1024

        if size_kb > 50000:
            print(f"  {pn:<22} SKIP (too large: {size_kb} KB)")
            continue

        print(f"  {pn:<22} ({size_kb} KB)... ", end="", flush=True)

        try:
            uploaded = genai.upload_file(str(pdf), mime_type="application/pdf")
            response = model.generate_content(
                [uploaded, PROMPT],
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=4000,
                ),
            )

            raw = response.text.strip()
            if "```" in raw:
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            try:
                data = json.loads(raw)
                existing[pn] = data
                ean = data.get("ean", "")
                title = data.get("title", "")[:50]
                specs = len(data.get("specs", {}))
                print(f"OK  ean={ean or '-'}  specs={specs}  title={title}")
            except json.JSONDecodeError:
                # Salvage partial data
                ean_match = re.search(r'"ean"\s*:\s*"([^"]*)"', raw)
                title_match = re.search(r'"title"\s*:\s*"([^"]*)"', raw)
                pn_match = re.search(r'"pn"\s*:\s*"([^"]*)"', raw)
                partial = {
                    "pn": pn_match.group(1) if pn_match else "",
                    "title": title_match.group(1) if title_match else "",
                    "ean": ean_match.group(1) if ean_match else "",
                    "_partial": True,
                }
                existing[pn] = partial
                print(f"PARTIAL  ean={partial['ean'] or '-'}  title={partial['title'][:40]}")

        except Exception as e:
            print(f"ERROR: {str(e)[:60]}")

        # Save after each PDF
        results_file.parent.mkdir(parents=True, exist_ok=True)
        results_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

        time.sleep(10)  # 10 sec between Gemini calls

    print(f"\nTotal parsed: {len(existing)}")


def main():
    # Phase 1-3 are quick, run once
    try:
        phase1_download_datasheets()
    except Exception as e:
        print(f"PHASE 1 ERROR: {e}")

    try:
        phase2_download_scene7()
    except Exception as e:
        print(f"PHASE 2 ERROR: {e}")

    try:
        phase3_find_other_cdns()
    except Exception as e:
        print(f"PHASE 3 ERROR: {e}")

    # Phase 4 is long — auto-retry on failure
    max_retries = 3
    for attempt in range(max_retries):
        try:
            phase4_parse_datasheets()
            break
        except Exception as e:
            print(f"\nPHASE 4 ERROR (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print("Waiting 30 sec and retrying...")
                time.sleep(30)
            else:
                print("All retries exhausted.")

    print("\n" + "=" * 90)
    print("NIGHT BATCH COMPLETE")
    print(f"Datasheets: {DS_DIR}")
    print(f"Scene7 photos: {SCENE7_DIR}")
    print("=" * 90)


if __name__ == "__main__":
    main()
