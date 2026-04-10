"""photo_hunter.py — Multi-channel photo collector for evidence bundles.

Channels (priority order):
  1. OG-image scraping from known source URLs (eBay, distributors, manufacturers)
  2. Datasheet PDF image extraction (PyMuPDF — largest image from first pages)
  3. Family photo propagation (same series already has photo)
  4. SerpAPI Google Images search (PN + brand/category)
  5. AI generation from specs+category (OpenAI DALL-E / placeholder)

Usage:
    python scripts/photo_hunter.py [--dry-run] [--channels 1,2,3,4,5] [--limit N] [--pn PN]

Each channel writes:
  - downloads/photos/{PN}.jpg  (the actual image file)
  - updates evidence file: dr_image_url, dr_image_source, dr_image_channel
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image as PILImage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = ROOT / "downloads" / "evidence"
PHOTOS_DIR = ROOT / "downloads" / "photos"
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / "downloads" / ".env")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.google.com/",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

MIN_IMAGE_BYTES = 3000  # smaller = likely placeholder/icon
MIN_IMAGE_DIMENSION = 80  # pixels
BAD_ASPECT_RATIO = 6.0  # wider/taller than this = banner, not product photo


# ── Utilities ────────────────────────────────────────────────────────────────────

def safe_filename(pn: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", pn)


def load_evidence(pn: str) -> tuple[dict, Path]:
    safe = safe_filename(pn)
    path = EVIDENCE_DIR / f"evidence_{safe}.json"
    if path.exists():
        return json.loads(path.read_text("utf-8")), path
    return {}, path


def save_evidence(ev: dict, path: Path) -> None:
    path.write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")


def download_image(url: str, dest: Path, *, timeout: int = 15) -> bool:
    """Download an image, validate it, save as JPEG. Returns True on success."""
    if not url or url.startswith("data:") or url.startswith("x-raw-image"):
        return False
    low = url.lower().split("?")[0]
    if low.endswith(".svg") or low.endswith(".gif"):
        return False
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout, stream=True)
        if resp.status_code != 200:
            return False
        ct = resp.headers.get("content-type", "")
        if "image" not in ct and "octet" not in ct:
            return False
        data = resp.content
        if len(data) < MIN_IMAGE_BYTES:
            return False
        # Validate with PIL and convert to JPEG
        img = PILImage.open(io.BytesIO(data))
        w, h = img.size
        if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
            return False
        # Convert to RGB JPEG
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.save(dest, "JPEG", quality=90)
        return True
    except Exception as e:
        log.debug(f"Download failed {url[:60]}: {e}")
        return False


def photo_exists(pn: str) -> bool:
    dest = PHOTOS_DIR / f"{safe_filename(pn)}.jpg"
    return dest.exists() and dest.stat().st_size > MIN_IMAGE_BYTES


def photo_is_bad(pn: str) -> bool:
    """Check if existing photo is a banner/strip/icon that should be replaced."""
    dest = PHOTOS_DIR / f"{safe_filename(pn)}.jpg"
    if not dest.exists():
        return False
    try:
        img = PILImage.open(dest)
        w, h = img.size
        ratio = max(w, h) / max(min(w, h), 1)
        if w < 100 and h < 100:
            return True  # tiny icon
        if ratio > BAD_ASPECT_RATIO:
            return True  # extreme banner
        return False
    except Exception:
        return True


# ── Channel 1: OG-image / meta scraping from known URLs ─────────────────────────

def _extract_og_image(html: str, base_url: str) -> list[str]:
    """Extract image URLs from page meta tags, JSON-LD, and product image patterns."""
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    # og:image
    for tag in soup.find_all("meta", property="og:image"):
        url = tag.get("content", "").strip()
        if url:
            candidates.append(urljoin(base_url, url))

    # twitter:image
    for tag in soup.find_all("meta", attrs={"name": "twitter:image"}):
        url = tag.get("content", "").strip()
        if url:
            candidates.append(urljoin(base_url, url))

    # JSON-LD product images
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            ld = json.loads(script.string or "")
            if isinstance(ld, dict):
                for key in ("image", "images", "thumbnailUrl"):
                    val = ld.get(key)
                    if isinstance(val, str):
                        candidates.append(urljoin(base_url, val))
                    elif isinstance(val, list):
                        for v in val[:3]:
                            if isinstance(v, str):
                                candidates.append(urljoin(base_url, v))
                            elif isinstance(v, dict) and v.get("url"):
                                candidates.append(urljoin(base_url, v["url"]))
        except (json.JSONDecodeError, TypeError):
            pass

    # eBay specific: i.ebayimg.com pattern
    for img in soup.find_all("img"):
        src = img.get("src", "") or img.get("data-src", "")
        if "ebayimg.com" in src and "/g/" in src:
            candidates.append(urljoin(base_url, src))

    # Large product images (common patterns)
    for img in soup.find_all("img"):
        src = img.get("src", "") or img.get("data-src", "")
        if not src:
            continue
        full = urljoin(base_url, src)
        # Skip tiny icons, logos, tracking pixels
        if any(skip in full.lower() for skip in [
            "logo", "icon", "sprite", "pixel", "tracking", "blank",
            "spacer", "1x1", "banner", "badge", "flag"
        ]):
            continue
        # Prefer product-looking URLs
        if any(hint in full.lower() for hint in [
            "product", "catalog", "media", "upload", "image/cache",
            "scene7", "asset.conrad", "asset.re-in"
        ]):
            candidates.append(full)

    return candidates


def channel_og_scrape(pn: str, ev: dict) -> Optional[str]:
    """Try to scrape product image from known source URLs."""
    sources = ev.get("sources_chatgpt", []) + ev.get("sources_gemini", [])

    # Also check dr_price_source
    price_src = ev.get("dr_price_source", "")
    if price_src:
        sources.append({"url": price_src, "page_type": "distributor", "domain": ""})

    # Prioritize: eBay first (clean photos), then distributors, then others
    def sort_key(s):
        url = s.get("url", "")
        if "ebay" in url:
            return 0
        if s.get("page_type") == "distributor":
            return 1
        if s.get("page_type") == "manufacturer":
            return 2
        return 3

    sources.sort(key=sort_key)
    dest = PHOTOS_DIR / f"{safe_filename(pn)}.jpg"

    for src in sources[:5]:  # max 5 attempts
        url = src.get("url", "").strip()
        if not url or url.endswith(".pdf"):
            continue
        try:
            resp = requests.get(url, headers={
                "User-Agent": BROWSER_HEADERS["User-Agent"],
                "Accept": "text/html,application/xhtml+xml,*/*",
                "Accept-Language": "en-US,en;q=0.9",
            }, timeout=12)
            if resp.status_code != 200:
                continue
            candidates = _extract_og_image(resp.text, url)
            for img_url in candidates[:5]:
                if download_image(img_url, dest):
                    log.info(f"  [OG] {pn}: {img_url[:80]}")
                    return img_url
        except Exception as e:
            log.debug(f"  [OG] {pn} failed on {url[:50]}: {e}")
            continue
        time.sleep(0.3)

    return None


# ── Channel 2: Datasheet PDF image extraction ────────────────────────────────────

def channel_pdf_extract(pn: str, ev: dict) -> Optional[str]:
    """Download datasheet PDF, extract the largest product image."""
    try:
        import fitz
    except ImportError:
        log.warning("PyMuPDF not installed, skipping PDF channel")
        return None

    sources = ev.get("sources_chatgpt", []) + ev.get("sources_gemini", [])
    pdf_urls = []
    for s in sources:
        url = s.get("url", "")
        pt = s.get("page_type", "")
        if url.endswith(".pdf") or "pdf" in pt.lower():
            pdf_urls.append(url)

    # Also check searched_urls
    for url in ev.get("searched_urls", []):
        if url.endswith(".pdf") and url not in pdf_urls:
            pdf_urls.append(url)

    dest = PHOTOS_DIR / f"{safe_filename(pn)}.jpg"

    for pdf_url in pdf_urls[:2]:  # max 2 PDFs
        try:
            resp = requests.get(pdf_url, headers=BROWSER_HEADERS, timeout=20)
            if resp.status_code != 200 or len(resp.content) < 5000:
                continue

            doc = fitz.open(stream=resp.content, filetype="pdf")
            best_img = None
            best_area = 0

            # Scan first 5 pages for product images
            for page_num in range(min(5, len(doc))):
                page = doc[page_num]
                images = page.get_images(full=True)

                for img_info in images:
                    xref = img_info[0]
                    try:
                        base_image = doc.extract_image(xref)
                        if not base_image or not base_image.get("image"):
                            continue
                        w = base_image.get("width", 0)
                        h = base_image.get("height", 0)
                        area = w * h
                        img_bytes = base_image["image"]

                        # Skip tiny images (logos, icons)
                        if w < 100 or h < 100 or len(img_bytes) < 3000:
                            continue

                        # Prefer images that look like product photos (not full-page scans)
                        if area > 4_000_000:  # probably a full page background
                            continue

                        if area > best_area:
                            best_area = area
                            best_img = img_bytes
                    except Exception:
                        continue

            doc.close()

            if best_img and best_area > 10000:
                img = PILImage.open(io.BytesIO(best_img))
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(dest, "JPEG", quality=90)
                log.info(f"  [PDF] {pn}: extracted {best_area}px from {pdf_url[:60]}")
                return f"extracted_from:{pdf_url}"

        except Exception as e:
            log.debug(f"  [PDF] {pn} failed on {pdf_url[:50]}: {e}")
            continue

    return None


# ── Channel 3: Family photo propagation ──────────────────────────────────────────

def build_series_photo_map() -> dict[str, tuple[str, str]]:
    """Build map: series_key -> (donor_pn, image_url)."""
    series_map: dict[str, tuple[str, str]] = {}
    for f in EVIDENCE_DIR.iterdir():
        if not f.name.startswith("evidence_") or not f.name.endswith(".json"):
            continue
        try:
            ev = json.loads(f.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        img = ev.get("dr_image_url", "")
        series = ev.get("dr_series", "")
        brand = ev.get("dr_brand", "")
        pn = f.name.replace("evidence_", "").replace(".json", "")

        if img and series:
            key = f"{brand}|{series}".lower().strip()
            # Also check if local file exists
            if photo_exists(pn) or img.startswith("http"):
                series_map[key] = (pn, img)

    return series_map


def channel_family_propagation(pn: str, ev: dict, series_map: dict) -> Optional[str]:
    """Copy photo from a sibling SKU in the same series."""
    series = ev.get("dr_series", "")
    brand = ev.get("dr_brand", "")
    if not series:
        return None

    key = f"{brand}|{series}".lower().strip()
    if key not in series_map:
        return None

    donor_pn, donor_url = series_map[key]
    if donor_pn == pn:
        return None

    donor_file = PHOTOS_DIR / f"{safe_filename(donor_pn)}.jpg"
    dest = PHOTOS_DIR / f"{safe_filename(pn)}.jpg"

    if donor_file.exists() and donor_file.stat().st_size > MIN_IMAGE_BYTES:
        # Copy local file
        import shutil
        shutil.copy2(donor_file, dest)
        log.info(f"  [FAM] {pn}: copied from {donor_pn}")
        return f"family:{donor_pn}:{donor_url}"

    # Try downloading donor URL
    if donor_url.startswith("http") and download_image(donor_url, dest):
        log.info(f"  [FAM] {pn}: downloaded from sibling {donor_pn}")
        return f"family:{donor_pn}:{donor_url}"

    return None


# ── Channel 4: SerpAPI Google Images ─────────────────────────────────────────────

def channel_serpapi(pn: str, ev: dict) -> Optional[str]:
    """Search Google Images via SerpAPI for product photo."""
    api_key = os.environ.get("SERPAPI_KEY", "")
    if not api_key:
        log.warning("SERPAPI_KEY not set, skipping SerpAPI channel")
        return None

    try:
        from serpapi import GoogleSearch
    except ImportError:
        log.warning("serpapi package not installed")
        return None

    brand = ev.get("dr_brand") or ev.get("brand") or "Honeywell"
    category = ev.get("dr_category") or ""
    alias = ev.get("dr_alias") or ""

    # Build search queries in priority order
    queries = [f"{pn} {brand}"]
    if alias:
        queries.append(f"{alias} {brand}")
    if category:
        queries.append(f"{pn} {category}")

    dest = PHOTOS_DIR / f"{safe_filename(pn)}.jpg"

    for query in queries[:2]:  # max 2 API calls per SKU
        try:
            params = {
                "engine": "google_images",
                "q": query,
                "num": 8,
                "safe": "active",
                "api_key": api_key,
            }
            results = GoogleSearch(params).get_dict()
            images = results.get("images_results", [])
            time.sleep(0.5)

            for img in images[:5]:
                original = img.get("original", "")
                thumbnail = img.get("thumbnail", "")

                # Try original first
                if download_image(original, dest):
                    log.info(f"  [SERP] {pn}: {original[:80]}")
                    return original

                # Fallback to thumbnail
                if download_image(thumbnail, dest):
                    log.info(f"  [SERP] {pn}: thumbnail {thumbnail[:60]}")
                    return thumbnail

        except Exception as e:
            log.warning(f"  [SERP] {pn}: {e}")
            break

    return None


# ── Channel 5: AI-generated product render ───────────────────────────────────────

def channel_ai_generate(pn: str, ev: dict) -> Optional[str]:
    """Generate a product placeholder image using OpenAI DALL-E."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        log.warning("OPENAI_API_KEY not set, skipping AI generation channel")
        return None

    category = ev.get("dr_category") or ev.get("expected_category") or ""
    brand = ev.get("dr_brand") or ev.get("brand") or "Honeywell"
    title_ru = ev.get("dr_title_ru") or ev.get("assembled_title") or ""
    specs = ev.get("dr_specs") or ""
    series = ev.get("dr_series") or ""

    if not category and not title_ru:
        return None  # not enough info to generate

    # Build description for the AI
    desc_parts = []
    if category:
        desc_parts.append(category)
    if brand:
        desc_parts.append(f"by {brand}")
    if series:
        desc_parts.append(f"series {series}")
    if specs:
        # Take first few specs
        short_specs = "; ".join(specs.split(";")[:3])
        desc_parts.append(f"({short_specs})")

    product_desc = " ".join(desc_parts)

    prompt = (
        f"Professional product photograph of an industrial {product_desc}. "
        f"Clean white background, studio lighting, high detail, "
        f"catalog-quality product shot. Part number {pn}. "
        f"No text overlays, no watermarks, no human hands."
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )

        image_url = response.data[0].url
        dest = PHOTOS_DIR / f"{safe_filename(pn)}.jpg"

        if download_image(image_url, dest):
            log.info(f"  [AI] {pn}: generated from '{product_desc[:50]}'")
            return f"ai_generated:dall-e-3:{product_desc[:80]}"

    except Exception as e:
        log.warning(f"  [AI] {pn}: generation failed: {e}")

    return None


# ── Channel 6: Gemini Imagen generation ──────────────────────────────────────────

def channel_gemini_imagen(pn: str, ev: dict) -> Optional[str]:
    """Generate product photo using Google Imagen 4.0 via Gemini API."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("GEMINI_API_KEY not set, skipping Imagen channel")
        return None

    category = ev.get("dr_category") or ev.get("expected_category") or ""
    brand = ev.get("dr_brand") or ev.get("brand") or "Honeywell"
    title_ru = ev.get("dr_title_ru") or ev.get("assembled_title") or ""
    specs = ev.get("dr_specs") or ""
    series = ev.get("dr_series") or ""

    if not category and not title_ru:
        return None

    # Build product description
    desc_parts = []
    if category:
        desc_parts.append(category)
    if brand:
        desc_parts.append(f"by {brand}")
    if series:
        desc_parts.append(f"series {series}")
    if specs:
        short_specs = "; ".join(specs.split(";")[:3])
        desc_parts.append(f"({short_specs})")

    product_desc = " ".join(desc_parts)

    prompt = (
        f"Professional product photograph of an industrial {product_desc}. "
        f"Clean white background, studio lighting, high detail, "
        f"catalog-quality product shot. No text, no watermarks, no human hands."
    )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="1:1",
            ),
        )

        if response.generated_images:
            img_data = response.generated_images[0].image.image_bytes
            dest = PHOTOS_DIR / f"{safe_filename(pn)}.jpg"

            img = PILImage.open(io.BytesIO(img_data))
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(dest, "JPEG", quality=92)

            log.info(f"  [IMAGEN] {pn}: generated from '{product_desc[:50]}'")
            return f"ai_generated:imagen-4.0:{product_desc[:80]}"

    except Exception as e:
        log.warning(f"  [IMAGEN] {pn}: generation failed: {e}")

    return None


# ── Channel 7: Gemini Vision + PDF page render ──────────────────────────────────

def channel_gemini_pdf_vision(pn: str, ev: dict) -> Optional[str]:
    """Render PDF pages to images, use Gemini Vision to find & crop product photo."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("GEMINI_API_KEY not set, skipping Vision PDF channel")
        return None

    try:
        import fitz
    except ImportError:
        log.warning("PyMuPDF not installed, skipping Vision PDF channel")
        return None

    # Collect PDF URLs
    sources = ev.get("sources_chatgpt", []) + ev.get("sources_gemini", [])
    pdf_urls = []
    for s in sources:
        url = s.get("url", "")
        pt = s.get("page_type", "")
        if url.endswith(".pdf") or "pdf" in pt.lower():
            pdf_urls.append(url)
    for url in ev.get("searched_urls", []):
        if url.endswith(".pdf") and url not in pdf_urls:
            pdf_urls.append(url)

    if not pdf_urls:
        return None

    dest = PHOTOS_DIR / f"{safe_filename(pn)}.jpg"

    for pdf_url in pdf_urls[:2]:
        try:
            resp = requests.get(pdf_url, headers=BROWSER_HEADERS, timeout=20)
            if resp.status_code != 200 or len(resp.content) < 5000:
                continue

            doc = fitz.open(stream=resp.content, filetype="pdf")

            # Render first 3 pages as images, ask Gemini which has product photo
            for page_num in range(min(3, len(doc))):
                page = doc[page_num]
                # Render at 150 DPI (balance quality vs size)
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")

                if len(img_bytes) < 5000:
                    continue

                # Ask Gemini Vision to find product photo
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=api_key)

                vision_prompt = (
                    f"This is page {page_num + 1} of a product datasheet. "
                    f"I'm looking for a product photo of part number {pn} "
                    f"({ev.get('dr_category', 'industrial product')}). "
                    f"If you can see a product photo (not a logo, not a diagram, "
                    f"not a schematic — an actual photo of the physical product), "
                    f"respond with ONLY the bounding box as: "
                    f"FOUND x1,y1,x2,y2 (pixel coordinates, top-left and bottom-right). "
                    f"If no product photo is visible, respond with: NONE"
                )

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                        vision_prompt,
                    ],
                )

                answer = response.text.strip()
                if answer.startswith("FOUND"):
                    # Parse bounding box
                    try:
                        coords = answer.replace("FOUND", "").strip()
                        parts = [int(c.strip()) for c in coords.split(",")]
                        if len(parts) == 4:
                            x1, y1, x2, y2 = parts
                            # Crop the product photo
                            page_img = PILImage.open(io.BytesIO(img_bytes))
                            w, h = page_img.size
                            # Clamp coordinates
                            x1, y1 = max(0, x1), max(0, y1)
                            x2, y2 = min(w, x2), min(h, y2)

                            if (x2 - x1) > 50 and (y2 - y1) > 50:
                                cropped = page_img.crop((x1, y1, x2, y2))
                                if cropped.mode != "RGB":
                                    cropped = cropped.convert("RGB")
                                cropped.save(dest, "JPEG", quality=90)
                                doc.close()
                                log.info(f"  [VISION] {pn}: cropped from page {page_num+1} of {pdf_url[:50]}")
                                return f"pdf_vision:{pdf_url}:page{page_num+1}"
                    except (ValueError, IndexError) as e:
                        log.debug(f"  [VISION] {pn}: bbox parse failed: {answer}")

                time.sleep(0.5)  # rate limit

            doc.close()

        except Exception as e:
            log.debug(f"  [VISION] {pn} PDF failed {pdf_url[:50]}: {e}")
            continue

    return None


# ── Main orchestrator ────────────────────────────────────────────────────────────

CHANNEL_MAP = {
    1: ("og_scrape", channel_og_scrape),
    2: ("pdf_extract", channel_pdf_extract),
    3: ("family", None),  # needs series_map, handled separately
    4: ("serpapi", channel_serpapi),
    5: ("ai_generate", channel_ai_generate),
    6: ("gemini_imagen", channel_gemini_imagen),
    7: ("gemini_pdf_vision", channel_gemini_pdf_vision),
}


def hunt_photo(pn: str, ev: dict, ev_path: Path, channels: list[int],
               series_map: dict, dry_run: bool = False) -> dict:
    """Try all channels in order. Returns result dict."""
    result = {"pn": pn, "channel": None, "url": None, "status": "not_found"}

    for ch_num in channels:
        if ch_num == 3:
            url = channel_family_propagation(pn, ev, series_map)
        else:
            _, func = CHANNEL_MAP[ch_num]
            url = func(pn, ev)

        if url:
            ch_name = CHANNEL_MAP[ch_num][0]
            result = {"pn": pn, "channel": ch_name, "url": url, "status": "found"}

            if not dry_run:
                ev["dr_image_url"] = url
                ev["dr_image_channel"] = ch_name
                save_evidence(ev, ev_path)

            break

    return result


def main():
    parser = argparse.ArgumentParser(description="Multi-channel photo hunter")
    parser.add_argument("--dry-run", action="store_true", help="Don't write files")
    parser.add_argument("--channels", default="1,2,3,7,6",
                        help="Comma-separated channel numbers (default: 1,2,3,7,6). "
                             "4=SerpAPI, 5=DALL-E, 6=Gemini Imagen, 7=Gemini Vision+PDF")
    parser.add_argument("--limit", type=int, default=0, help="Max SKUs to process (0=all)")
    parser.add_argument("--pn", default="", help="Process only this PN")
    parser.add_argument("--force", action="store_true", help="Re-process even if photo exists")
    parser.add_argument("--replace-bad", action="store_true",
                        help="Also re-process photos that are banners/icons/broken")
    args = parser.parse_args()

    channels = [int(c.strip()) for c in args.channels.split(",")]
    log.info(f"Channels: {channels} | Dry-run: {args.dry_run}")

    # Build series map for family propagation (channel 3)
    series_map = build_series_photo_map() if 3 in channels else {}
    if series_map:
        log.info(f"Series photo map: {len(series_map)} series with photos")

    # Collect SKUs to process
    targets = []
    for f in sorted(EVIDENCE_DIR.iterdir()):
        if not f.name.startswith("evidence_") or not f.name.endswith(".json"):
            continue
        pn = f.name.replace("evidence_", "").replace(".json", "")

        if args.pn and pn != args.pn:
            continue

        ev, ev_path = load_evidence(pn)

        # Skip if already has good photo (unless --force or --replace-bad)
        if not args.force:
            has_url = bool(ev.get("dr_image_url"))
            has_local = photo_exists(pn)

            if args.replace_bad:
                # Only include if photo is bad/missing
                if has_local and not photo_is_bad(pn):
                    continue
            else:
                if has_url or has_local:
                    continue

        targets.append((pn, ev, ev_path))

    if args.limit:
        targets = targets[:args.limit]

    log.info(f"Targets: {len(targets)} SKUs without photos")

    # Process
    found = 0
    results = []

    for i, (pn, ev, ev_path) in enumerate(targets):
        prefix = f"[{i+1}/{len(targets)}]"
        result = hunt_photo(pn, ev, ev_path, channels, series_map, dry_run=args.dry_run)
        results.append(result)

        if result["status"] == "found":
            found += 1
            ch = result["channel"]
            url_short = (result["url"] or "")[:60]
            print(f"  {prefix} + {pn:<25} [{ch}] {url_short}")
        else:
            print(f"  {prefix} - {pn:<25} [not found]")

    # Summary
    print(f"\n=== Photo Hunter Summary ===")
    print(f"  Processed: {len(targets)}")
    print(f"  Found:     {found}")
    print(f"  Not found: {len(targets) - found}")
    if not args.dry_run:
        print(f"  Photos in: {PHOTOS_DIR}")

    # Channel breakdown
    ch_counts = {}
    for r in results:
        ch = r.get("channel") or "not_found"
        ch_counts[ch] = ch_counts.get(ch, 0) + 1
    print(f"\n  By channel:")
    for ch, count in sorted(ch_counts.items()):
        print(f"    {ch}: {count}")

    # Save hunt report
    if not args.dry_run and results:
        from datetime import datetime
        report = {
            "run_at": datetime.now().isoformat(),
            "channels": channels,
            "processed": len(targets),
            "found": found,
            "channel_breakdown": ch_counts,
            "results": results,
        }
        report_path = ROOT / "downloads" / "photo_hunt_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"Report: {report_path}")


if __name__ == "__main__":
    main()
