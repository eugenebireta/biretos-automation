"""exporter_insales.py — Draft InSales CSV from validated evidence + photo manifest.

Reads evidence bundles as source of truth, attaches photo URLs from
cloud_upload_manifest.csv, and outputs:
  1. insales_draft_export.csv  — exportable rows
  2. insales_skipped.csv       — skipped/review rows with reasons

Principles:
  - No hallucinated values — only validated/usable fields exported
  - specs_raw_unvalidated never exported as confirmed specs
  - blocked price / weak identity cases flagged, not silently included
  - photo URL from manifest only, never reconstructed
  - brand from evidence, not hardcoded

Usage:
    python scripts/exporter_insales.py [--limit N] [--include-draft]
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
EVIDENCE_DIR = DOWNLOADS / "evidence"
TRIAGE_DIR = DOWNLOADS / "photo_triage"
EXPORT_DIR = DOWNLOADS / "export"

CLOUD_MANIFEST_CSV = TRIAGE_DIR / "cloud_upload_manifest.csv"
OUTPUT_EXPORT = EXPORT_DIR / "insales_draft_export.csv"
OUTPUT_SKIPPED = EXPORT_DIR / "insales_skipped.csv"

SKIP_PNS = {"---", "-----", "PN", "_", ""}

EXPORT_FIELDS = [
    "Артикул",
    "Название",
    "Бренд",
    "Изображение",
    "Цена",
    "Валюта",
    "Категория",
    "Краткое описание",
    "Статус экспорта",
    "Примечание",
]

SKIPPED_FIELDS = [
    "Артикул",
    "Название",
    "Бренд",
    "Причина пропуска",
    "identity_level",
    "card_status",
    "has_price",
    "has_photo",
]


# ── Specs formatting ─────────────────────────────────────────────────────────

def format_specs_html(specs: dict[str, Any]) -> str:
    """Format confirmed specs as HTML list for InSales description.

    Strategy:
      1. If structured key-value pairs exist (beyond raw/aliases) → HTML list
      2. If only 'raw' text from DR → use as plain text description
      3. Exclude internal fields (aliases, merge_ts, etc.)
    """
    if not specs or not isinstance(specs, dict):
        return ""

    internal_keys = {"raw", "aliases", "sources", "cite", "confidence", "merge_ts",
                     "merge_source", "imported_at", "source", "source_url",
                     "key_findings", "title_ru", "description_ru", "identity_confirmed"}

    # Try structured key-value pairs first
    items = []
    for k, v in specs.items():
        if k in internal_keys:
            continue
        v_str = str(v).strip() if v is not None else ""
        if not v_str or v_str.lower() in ("none", "n/a", "unknown", "null"):
            continue
        clean_key = k.replace("_", " ").strip()
        if clean_key:
            clean_key = clean_key[0].upper() + clean_key[1:]
        items.append(f"<li><b>{clean_key}:</b> {v_str[:200]}</li>")

    if items:
        return "<ul>" + "".join(items) + "</ul>"

    # Fallback: use 'raw' text from DR (this is validated DR content, NOT
    # specs_raw_unvalidated which is identity-blocked)
    raw = specs.get("raw", "")
    if raw and isinstance(raw, str):
        clean = raw.strip()[:500]
        if clean:
            return f"<p>{clean}</p>"

    return ""


# ── Photo manifest loader ────────────────────────────────────────────────────

def load_photo_manifest() -> dict[str, str]:
    """Load part_number -> public_url mapping from cloud upload manifest."""
    mapping: dict[str, str] = {}
    if not CLOUD_MANIFEST_CSV.exists():
        log.warning(f"Cloud manifest not found: {CLOUD_MANIFEST_CSV}")
        return mapping
    with open(CLOUD_MANIFEST_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pn = row.get("part_number", "").strip()
            url = row.get("public_url", "").strip()
            status = row.get("upload_status", "")
            if pn and url and status == "ok":
                mapping[pn] = url
    log.info(f"Photo manifest loaded: {len(mapping)} URLs")
    return mapping


# ── Evidence loading ──────────────────────────────────────────────────────────

def load_all_evidence() -> list[dict]:
    """Load all valid evidence bundles."""
    bundles = []
    for f in sorted(EVIDENCE_DIR.glob("evidence_*.json")):
        pn = f.stem.replace("evidence_", "")
        if pn in SKIP_PNS:
            continue
        try:
            ev = json.loads(f.read_text(encoding="utf-8-sig"))
            ev["_pn"] = pn  # ensure PN always set
            bundles.append(ev)
        except Exception as e:
            log.warning(f"Failed to load {f.name}: {e}")
    return bundles


# ── Export eligibility ────────────────────────────────────────────────────────

def check_exportable(ev: dict) -> tuple[bool, str]:
    """Check if a SKU is exportable. Returns (eligible, skip_reason)."""
    pn = ev.get("_pn", "")
    brand = ev.get("brand", "")
    title = ev.get("assembled_title", "")
    identity = ev.get("identity_level", "unknown")

    # Hard requirements
    if not pn:
        return False, "no_part_number"
    if not brand:
        return False, "no_brand"
    if not title:
        return False, "no_title"

    # Identity gate
    if identity == "unknown":
        return False, "identity_unknown"

    # Identity gate result (from hardening batch)
    ig = ev.get("identity_gate", {})
    if ig.get("gate_result") == "block":
        return False, f"identity_blocked:{','.join(ig.get('reason_codes',[]))}"

    # Price check — need some price (dr_price or our_price_raw)
    dr_price = ev.get("dr_price")
    our_price = ev.get("our_price_raw", "")
    price_blocked = ev.get("dr_price_blocked")
    dr_price_flag = ev.get("dr_price_flag", "")

    has_usable_price = False
    if dr_price and not price_blocked and dr_price_flag != "WRONG_SOURCE":
        has_usable_price = True
    if our_price and our_price not in ("0,00", "0.00", "0", ""):
        has_usable_price = True

    if not has_usable_price:
        return False, "no_usable_price"

    # Specs validation — specs_raw_unvalidated means specs blocked
    if ev.get("specs_status") == "blocked_identity_unresolved":
        pass  # Not a hard block — SKU can export without specs

    return True, ""


# ── Row builder ───────────────────────────────────────────────────────────────

def build_export_row(ev: dict, photo_url: str) -> dict:
    """Build a single export row from validated evidence fields."""
    pn = ev["_pn"]
    brand = ev.get("brand", "")
    title = ev.get("assembled_title", "") or ev.get("name", "")

    # Price: prefer our_price_raw (RUB), fallback to dr_price
    our_price = ev.get("our_price_raw", "")
    dr_price = ev.get("dr_price")
    dr_currency = ev.get("dr_currency", "")
    dr_price_flag = ev.get("dr_price_flag", "")
    price_blocked = ev.get("dr_price_blocked")

    price_val = ""
    currency = ""

    if our_price and our_price not in ("0,00", "0.00", "0", ""):
        price_val = our_price
        currency = "RUB"
    elif dr_price and not price_blocked and dr_price_flag != "WRONG_SOURCE":
        price_val = str(dr_price)
        currency = dr_currency or ""

    # Category: use product_category (validated) or dr_category
    category = ev.get("product_category", "") or ev.get("dr_category", "")

    # Specs: only from deep_research.specs (structured), exclude raw
    dr = ev.get("deep_research", {})
    specs_dict = dr.get("specs", {})
    if isinstance(specs_dict, dict):
        specs_html = format_specs_html(specs_dict)
    else:
        specs_html = ""

    # Skip unvalidated specs
    if ev.get("specs_status") == "blocked_identity_unresolved":
        specs_html = ""

    # Review note
    notes = []
    identity = ev.get("identity_level", "")
    card_status = ev.get("card_status", "")

    if identity == "weak":
        notes.append("weak_identity")
    if dr_price_flag == "PACK_SUSPECT":
        notes.append("pack_suspect_price")
    if not photo_url:
        notes.append("no_photo")
    if not specs_html:
        notes.append("no_specs")
    if card_status == "DRAFT_ONLY":
        notes.append("draft_only")

    status = "export_ready_draft"
    if notes:
        status = "export_with_gaps"

    return {
        "Артикул": pn,
        "Название": title,
        "Бренд": brand,
        "Изображение": photo_url,
        "Цена": price_val,
        "Валюта": currency,
        "Категория": category,
        "Краткое описание": specs_html,
        "Статус экспорта": status,
        "Примечание": "; ".join(notes) if notes else "",
    }


def build_skipped_row(ev: dict, reason: str) -> dict:
    """Build a row for the skipped report."""
    pn = ev.get("_pn", "")
    return {
        "Артикул": pn,
        "Название": ev.get("assembled_title", "") or ev.get("name", ""),
        "Бренд": ev.get("brand", ""),
        "Причина пропуска": reason,
        "identity_level": ev.get("identity_level", ""),
        "card_status": ev.get("card_status", ""),
        "has_price": (
            "yes" if ev.get("dr_price") or ev.get("our_price_raw", "") not in ("0,00", "0.00", "0", "")
            else "no"
        ),
        "has_photo": "yes" if ev.get("dr_image_url") else "no",
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run_export(include_draft: bool = False, limit: int = 0) -> dict:
    """Run the full export pipeline. Returns stats dict."""
    photo_map = load_photo_manifest()
    bundles = load_all_evidence()
    if limit:
        bundles = bundles[:limit]

    log.info(f"Evidence bundles: {len(bundles)}")

    export_rows = []
    skipped_rows = []

    for ev in bundles:
        pn = ev["_pn"]
        eligible, skip_reason = check_exportable(ev)

        if not eligible and not include_draft:
            skipped_rows.append(build_skipped_row(ev, skip_reason))
            continue

        if not eligible and include_draft:
            # Include but mark as draft
            pass

        photo_url = photo_map.get(pn, "")
        row = build_export_row(ev, photo_url)

        if not eligible:
            row["Статус экспорта"] = "draft_with_issues"
            row["Примечание"] = skip_reason + ("; " + row["Примечание"] if row["Примечание"] else "")
            skipped_rows.append(build_skipped_row(ev, skip_reason))

        export_rows.append(row)

    # Write export CSV
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_EXPORT, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(export_rows)
    log.info(f"Export: {len(export_rows)} rows → {OUTPUT_EXPORT}")

    # Write skipped CSV
    with open(OUTPUT_SKIPPED, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SKIPPED_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(skipped_rows)
    log.info(f"Skipped: {len(skipped_rows)} rows → {OUTPUT_SKIPPED}")

    # Stats
    with_photo = sum(1 for r in export_rows if r.get("Изображение"))
    with_price = sum(1 for r in export_rows if r.get("Цена"))
    with_specs = sum(1 for r in export_rows if r.get("Краткое описание"))
    ready = sum(1 for r in export_rows if r.get("Статус экспорта") == "export_ready_draft")
    gaps = sum(1 for r in export_rows if r.get("Статус экспорта") == "export_with_gaps")

    return {
        "total_evidence": len(bundles),
        "exported": len(export_rows),
        "skipped": len(skipped_rows),
        "with_photo": with_photo,
        "with_price": with_price,
        "with_specs": with_specs,
        "export_ready_draft": ready,
        "export_with_gaps": gaps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="InSales draft export from evidence")
    parser.add_argument("--include-draft", action="store_true",
                        help="Include DRAFT_ONLY cards (marked as draft_with_issues)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of SKUs (0=all)")
    args = parser.parse_args()

    stats = run_export(include_draft=args.include_draft, limit=args.limit)

    print("\n=== INSALES DRAFT EXPORT ===")
    print(f"  Total evidence:     {stats['total_evidence']}")
    print(f"  Exported:           {stats['exported']}")
    print(f"  Skipped:            {stats['skipped']}")
    print(f"  With photo URL:     {stats['with_photo']}")
    print(f"  With price:         {stats['with_price']}")
    print(f"  With specs:         {stats['with_specs']}")
    print(f"  Export-ready draft: {stats['export_ready_draft']}")
    print(f"  Export with gaps:   {stats['export_with_gaps']}")
    print(f"  Output: {OUTPUT_EXPORT}")


if __name__ == "__main__":
    main()
