"""spec_extractor.py — Extract product specifications from visited HTML pages.

Strategies (in priority order):
1. Two-column tables (<table><tr><td>key</td><td>value</td></tr>)
2. Definition lists (<dl><dt>key</dt><dd>value</dd>)
3. Divs/sections with class containing "spec" (colon-delimited text pairs)

Results stored in bundle["content"]["specs"] and bundle["specs_status"].
Does NOT make network calls — works on already-downloaded HTML.
"""
from __future__ import annotations

import re
from typing import Optional

_MAX_KEY_LEN = 80
_MAX_VAL_LEN = 300
_MAX_SPECS = 100  # cap total specs per page


def _normalize_spec_key(key: str) -> str:
    """Normalise a spec key to snake_case ASCII-ish form."""
    key = key.strip().lower()
    # Replace common separators with underscore
    key = re.sub(r"[\s\-./]+", "_", key)
    # Remove non-alphanumeric except underscore
    key = re.sub(r"[^\w]", "", key, flags=re.UNICODE)
    # Collapse multiple underscores
    key = re.sub(r"_+", "_", key).strip("_")
    return key[:50] if key else ""


def _clean_text(s: str) -> str:
    return " ".join(s.split()).strip()


def extract_specs_from_html(html: str, pn: Optional[str] = None) -> dict:
    """Extract product specifications from an HTML page.

    Returns a dict mapping normalised spec key → value string.
    Returns empty dict if no specs found.
    Never raises — all errors are swallowed (non-blocking).
    """
    specs: dict = {}
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # ── Strategy 1: two-column tables ────────────────────────────────────
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) == 2:
                    key = _clean_text(cells[0].get_text())
                    val = _clean_text(cells[1].get_text())
                    if key and val and len(key) <= _MAX_KEY_LEN and len(val) <= _MAX_VAL_LEN:
                        nk = _normalize_spec_key(key)
                        if nk and nk not in specs:
                            specs[nk] = val
                if len(specs) >= _MAX_SPECS:
                    break
            if len(specs) >= _MAX_SPECS:
                break

        # ── Strategy 2: definition lists (<dl>/<dt>/<dd>) ────────────────────
        if len(specs) < _MAX_SPECS:
            for dl in soup.find_all("dl"):
                dts = dl.find_all("dt")
                dds = dl.find_all("dd")
                for dt, dd in zip(dts, dds):
                    key = _clean_text(dt.get_text())
                    val = _clean_text(dd.get_text())
                    if key and val and len(key) <= _MAX_KEY_LEN and len(val) <= _MAX_VAL_LEN:
                        nk = _normalize_spec_key(key)
                        if nk and nk not in specs:
                            specs[nk] = val
                if len(specs) >= _MAX_SPECS:
                    break

        # ── Strategy 3: divs/sections with class containing "spec" ───────────
        if len(specs) < _MAX_SPECS:
            spec_containers = soup.find_all(
                ["div", "section", "ul"],
                class_=lambda c: c and any("spec" in cls.lower() for cls in (c if isinstance(c, list) else [c])),
            )
            for container in spec_containers:
                items = container.find_all(["li", "p", "span", "div"], recursive=False)
                if not items:
                    items = container.find_all(["li", "p"])
                for item in items:
                    text = _clean_text(item.get_text())
                    if ":" in text:
                        parts = text.split(":", 1)
                        key = parts[0].strip()
                        val = parts[1].strip()
                        if key and val and len(key) <= _MAX_KEY_LEN and len(val) <= _MAX_VAL_LEN:
                            nk = _normalize_spec_key(key)
                            if nk and nk not in specs:
                                specs[nk] = val
                    if len(specs) >= _MAX_SPECS:
                        break
                if len(specs) >= _MAX_SPECS:
                    break

    except Exception:
        pass  # Non-blocking: never fail the pipeline

    return specs


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python spec_extractor.py <url_or_html_file>")
        sys.exit(1)

    arg = sys.argv[1]
    if arg.startswith("http"):
        import requests
        r = requests.get(arg, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        html_content = r.text
    else:
        with open(arg, encoding="utf-8", errors="replace") as fh:
            html_content = fh.read()

    result = extract_specs_from_html(html_content)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nTotal specs extracted: {len(result)}")
