"""Merge datasheet/EAN/photos data into evidence_*.json files.

Writes to a NEW namespace `from_datasheet` to not break existing fields.
After merge: evidence files contain authoritative datasheet data.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
DS_DIR = ROOT / "downloads" / "datasheets_v2"
PHOTOS_DIR = ROOT / "downloads" / "datasheet_photos"

DS_DATA = json.loads((ROOT / "downloads/staging/tier_collector_output/datasheet_extracted.json").read_text(encoding="utf-8"))
EAN_FOCUSED = json.loads((ROOT / "downloads/staging/tier_collector_output/ean_focused_extraction.json").read_text(encoding="utf-8")) if (ROOT / "downloads/staging/tier_collector_output/ean_focused_extraction.json").exists() else {}
EAN_DIST = json.loads((ROOT / "downloads/staging/tier_collector_output/ean_from_distributors.json").read_text(encoding="utf-8")) if (ROOT / "downloads/staging/tier_collector_output/ean_from_distributors.json").exists() else {}
EAN_EXT = json.loads((ROOT / "downloads/staging/tier_collector_output/ean_extended_search.json").read_text(encoding="utf-8")) if (ROOT / "downloads/staging/tier_collector_output/ean_extended_search.json").exists() else {}
EAN_CLAUDE = json.loads((ROOT / "downloads/staging/tier_collector_output/ean_claude_retry.json").read_text(encoding="utf-8")) if (ROOT / "downloads/staging/tier_collector_output/ean_claude_retry.json").exists() else {}


def get_best_ean(pn_safe: str) -> dict:
    """Get EAN from best available source. Datasheet > distributor."""
    # Datasheet parse
    ds = DS_DATA.get(pn_safe, {})
    ean = str(ds.get("ean", ""))
    if ean.isdigit() and len(ean) == 13:
        return {"ean": ean, "source": "datasheet_parse", "tier": 1}

    # Datasheet focused
    focused = EAN_FOCUSED.get(pn_safe, {})
    ean = str(focused.get("ean", ""))
    if ean.isdigit() and len(ean) == 13:
        return {"ean": ean, "source": "datasheet_focused", "tier": 1}

    # Distributor
    dist = EAN_DIST.get(pn_safe, {})
    ean = str(dist.get("ean", ""))
    if ean.isdigit() and len(ean) == 13:
        return {
            "ean": ean,
            "source": "distributor",
            "domain": dist.get("domain", ""),
            "source_url": dist.get("source_url", ""),
            "tier": 2,
        }

    # Extended grounding (Gemini)
    ext = EAN_EXT.get(pn_safe, {})
    ean = str(ext.get("ean", ""))
    if ext.get("valid") and ean.isdigit() and len(ean) == 13:
        return {"ean": ean, "source": "extended_grounding", "tier": 2}

    # Claude retry
    cr = EAN_CLAUDE.get(pn_safe, {})
    ean = str(cr.get("ean", ""))
    if cr.get("valid") and ean.isdigit() and len(ean) == 13:
        return {"ean": ean, "source": "claude_retry", "tier": 2}

    return {}


def get_datasheet_data(pn_safe: str) -> dict:
    """Get all datasheet-derived data."""
    ds = DS_DATA.get(pn_safe, {})
    if not ds or "_partial_raw" in ds or "error" in ds:
        return {}

    # Extract clean data
    title = str(ds.get("title", "")).strip()
    description = str(ds.get("description", "")).strip()
    series = str(ds.get("series", "")).strip()
    category = ds.get("category", "")
    if isinstance(category, list):
        category = " > ".join(str(c) for c in category)
    elif isinstance(category, dict):
        category = str(category)

    specs = ds.get("specs", {})
    if not isinstance(specs, dict):
        specs = {}

    # Weight
    weight_g = ds.get("weight_g", "")
    if isinstance(weight_g, dict):
        weight_g = weight_g.get("net") or weight_g.get("product_net") or ""
    if str(weight_g) in ("Not specified", "Not provided", "?", "None", ""):
        weight_g = ""

    # Dimensions
    dimensions = ds.get("dimensions_mm", "")
    if isinstance(dimensions, dict):
        parts = []
        for k in ["length", "width", "height", "depth_length"]:
            if dimensions.get(k):
                parts.append(str(dimensions[k]))
        dimensions = " x ".join(parts) if parts else ""
    if str(dimensions) in ("Not specified", "Not provided", "?", "None", ""):
        dimensions = ""

    certifications = ds.get("certifications", [])
    if not isinstance(certifications, list):
        certifications = []
    # Clean cert entries
    clean_certs = []
    for c in certifications:
        if isinstance(c, dict):
            clean_certs.append(c.get("name") or str(c))
        else:
            clean_certs.append(str(c))

    article_no = str(ds.get("article_no") or "").strip()

    return {
        "title": title,
        "description": description,
        "specs": specs,
        "specs_count": len(specs),
        "series": series,
        "category": category,
        "weight_g": weight_g,
        "dimensions_mm": dimensions,
        "certifications": clean_certs,
        "article_no": article_no,
    }


def main():
    now = datetime.now(timezone.utc).isoformat()
    stats = {
        "merged": 0,
        "ean_added": 0,
        "specs_added": 0,
        "weight_added": 0,
        "dims_added": 0,
        "photos_linked": 0,
        "datasheet_linked": 0,
    }

    print("=" * 80)
    print("Merging datasheet data into evidence_*.json")
    print("=" * 80)

    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in {"---", "--", "_", "PN", "-----"}:
            continue
        pn_safe = pn.replace("/", "_").replace(" ", "_")

        # Build from_datasheet block
        ds_data = get_datasheet_data(pn_safe)
        ean_data = get_best_ean(pn_safe)

        # Datasheet PDF link
        pdf_path = DS_DIR / f"{pn_safe}.pdf"
        has_pdf = pdf_path.exists()

        # Photos
        photos = []
        if PHOTOS_DIR.exists():
            for ph in PHOTOS_DIR.glob(f"{pn_safe}_p*.*"):
                photos.append(str(ph.relative_to(ROOT)))

        if not (ds_data or ean_data or has_pdf or photos):
            continue

        from_datasheet = {
            "merged_at": now,
            "schema_version": 2,
        }

        if ds_data:
            from_datasheet.update(ds_data)
            stats["specs_added"] += 1 if ds_data.get("specs_count", 0) > 0 else 0
            stats["weight_added"] += 1 if ds_data.get("weight_g") else 0
            stats["dims_added"] += 1 if ds_data.get("dimensions_mm") else 0

        if ean_data:
            from_datasheet["ean"] = ean_data["ean"]
            from_datasheet["ean_source"] = ean_data["source"]
            from_datasheet["ean_tier"] = ean_data["tier"]
            if "domain" in ean_data:
                from_datasheet["ean_domain"] = ean_data["domain"]
                from_datasheet["ean_source_url"] = ean_data.get("source_url", "")
            stats["ean_added"] += 1

        if has_pdf:
            from_datasheet["datasheet_pdf"] = str(pdf_path.relative_to(ROOT))
            from_datasheet["datasheet_size_kb"] = pdf_path.stat().st_size // 1024
            stats["datasheet_linked"] += 1

        if photos:
            from_datasheet["product_photos"] = photos
            from_datasheet["photo_count"] = len(photos)
            stats["photos_linked"] += 1

        # Write to evidence — using merge, not replace
        d["from_datasheet"] = from_datasheet
        f.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        stats["merged"] += 1

    print("\nMerge complete:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
