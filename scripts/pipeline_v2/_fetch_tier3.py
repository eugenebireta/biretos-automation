"""Quick tier3 fetch: sites that work without protection."""
from __future__ import annotations

import json
import sys
import io
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.app_secrets import get_secret
import anthropic

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT = ROOT / "downloads" / "staging" / "tier_collector_output"

URLS = [
    ("7910180000", "Weidmuller", "WTR 4 test-disconnect terminal",
     "https://us.wiautomation.com/weidmuller/general-automation/other/7910180000"),
    ("CM010610", "DKC", "screw M6x10",
     "https://www.chipdip.ru/product0/8000757816"),
    ("1000106", "Howard Leight", "earplugs 304L",
     "https://www.amazon.co.uk/Honeywell-1000106-Howard-Leight-Individually/dp/B006GCNBYI"),
    ("36022-RU", "DKC", "horizontal angle 100x80",
     "https://www.dkc.ru/ru/catalog/product/36022-ru/"),
    ("36024-RU", "DKC", "horizontal angle 200x80",
     "https://www.dkc.ru/ru/catalog/product/36024-ru/"),
    ("36299-RU", "DKC", "RRC adapter",
     "https://www.dkc.ru/ru/catalog/product/36299-ru/"),
    ("CWSS-RB-S8", "System Sensor", "sounder beacon red",
     "https://www.stockonfire.com/product/cwss-rb-s8-system-sensor/"),
    ("EVCS-HSB", "Notifier", "fire EVCS refuge outstation",
     "https://www.stockonfire.com/product/evcs-hsb/"),
    ("1011893-RU", "Sperian", "safety harness H-design",
     "https://www.fabory.com/en/honeywell-miller-h-design-harness-1011893/p/P0100018940"),
    ("1006186", "Howard Leight", "earplugs 303L red",
     "https://www.modern-eastern.com/en/home/honeywell-earplugs-304l-large-Box-of-200-pair-1006186"),
]

EXTRACT_PROMPT = """Extract product data for {brand} {pn} ({seed}).
Return ONLY a JSON object:
{{"pn":"","brand":"","title":"","price":"","currency":"","photo_url":"","specs":{{}},"ean":"","category_path":"","datasheet_url":"","is_correct_product":true}}

Rules:
- If the page shows a DIFFERENT product, set is_correct_product=false
- specs: all technical specifications (dimensions, weight, material, color, etc)
- ean: EAN/GTIN barcode if visible
- price: selling price (not pack price)

Page content:
{text}"""


def fetch_page(url: str) -> str | None:
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )
            page = context.new_page()
            page.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined})')
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            time.sleep(4)
            text = page.evaluate("document.body.innerText")
            browser.close()
            return text if len(text) > 100 else None
    except Exception:
        return None


def main():
    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))
    OUTPUT.mkdir(parents=True, exist_ok=True)

    results = {}

    for pn, brand, seed, url in URLS:
        print(f"{pn:<22} ({brand})... ", end="", flush=True)

        text = fetch_page(url)
        if not text:
            print("FETCH FAILED")
            continue

        print(f"fetched ({len(text)} chars)... ", end="", flush=True)

        prompt = EXTRACT_PROMPT.format(brand=brand, pn=pn, seed=seed, text=text[:3500])

        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
        except Exception as e:
            print(f"EXTRACT ERROR: {e}")
            continue

        ok = data.get("is_correct_product", False)
        has_p = bool(data.get("price"))
        has_e = bool(data.get("ean"))
        has_s = len(data.get("specs", {}))

        status = "OK" if ok else "WRONG"
        fields = []
        if has_p:
            fields.append(f"price={data['price']}{data.get('currency', '')}")
        if has_e:
            fields.append(f"EAN={data['ean']}")
        if has_s:
            fields.append(f"specs({has_s})")

        print(f"{status} {' '.join(fields)}")
        if ok:
            data["_source_url"] = url
            results[pn] = data

        time.sleep(0.5)

    out_file = OUTPUT / "tier3_results.json"
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {len(results)} correct products to {out_file}")


if __name__ == "__main__":
    main()
