"""export_pipeline.py — Evidence bundle + InSales-ready export.

Outputs:
  1. evidence/evidence_{pn}.json — per-SKU full evidence bundle
  2. export/insales_export.csv  — InSales-ready (AUTO_PUBLISH + REVIEW_REQUIRED only)
  3. export/audit_report.json   — run summary + per-SKU status matrix

Card status logic:
  AUTO_PUBLISH:    KEEP photo + publishable price (public/rfq) + no mismatch
  REVIEW_REQUIRED: KEEP photo but price uncertain, OR valid price but no/reject photo
  DRAFT_ONLY:      No usable photo + no valid price, OR mismatch flags block publish

Photo canonical filename:
  {BRAND}_{PN_NORMALIZED}_{SHA1_8}.jpg
  No spaces, uppercase brand+PN, 8-char sha1 suffix for dedup.

Public photo URL:
  base_photo_url + "/" + canonical_filename
  If no hosting configured → staging placeholder [LOCAL:{path}]
"""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Filename normalization ───────────────────────────────────────────────────────

_UNSAFE_RE = re.compile(r"[^\w\-]")


def _safe(s: str) -> str:
    return _UNSAFE_RE.sub("_", s.upper()).strip("_")


def canonical_photo_filename(brand: str, pn: str, sha1: str, ext: str = "jpg") -> str:
    """Canonical photo filename for storage: {BRAND}_{PN}_{SHA1_8}.{ext}"""
    sha1_8 = (sha1 or "00000000")[:8]
    return f"{_safe(brand)}_{_safe(pn)}_{sha1_8}.{ext}"


# ── Card status ──────────────────────────────────────────────────────────────────

_PUBLISHABLE_PRICE = {"public_price", "rfq_only"}
_BLOCKING_PRICE = {"category_mismatch_only", "brand_mismatch_only"}


def assign_card_status(
    photo_verdict: str,
    price_status: str,
    category_mismatch: bool = False,
    brand_mismatch: bool = False,
    stock_photo_flag: bool = False,
) -> tuple[str, list[str]]:
    """Assign AUTO_PUBLISH / REVIEW_REQUIRED / DRAFT_ONLY.

    Returns (status, review_reasons[]).
    """
    reasons: list[str] = []

    has_good_photo = photo_verdict == "KEEP"
    has_valid_price = price_status in _PUBLISHABLE_PRICE
    has_blocking_mismatch = category_mismatch or brand_mismatch
    has_price_at_all = price_status not in ("no_price_found", "")

    if stock_photo_flag:
        reasons.append("stock_photo_flag")
    if category_mismatch:
        reasons.append("category_mismatch")
    if brand_mismatch:
        reasons.append("brand_mismatch")

    if has_good_photo and has_valid_price and not has_blocking_mismatch:
        return "AUTO_PUBLISH", reasons

    if has_good_photo or (has_valid_price and not has_blocking_mismatch):
        if has_blocking_mismatch:
            reasons.append("mismatch_blocks_publish")
        return "REVIEW_REQUIRED", reasons

    reasons.append("no_photo_and_no_price" if not has_good_photo and not has_price_at_all
                   else "photo_rejected_or_missing")
    return "DRAFT_ONLY", reasons


# ── Evidence bundle ──────────────────────────────────────────────────────────────

def build_evidence_bundle(
    pn: str,
    name: str,
    brand: str,
    photo_result: dict,
    vision_verdict: dict,
    price_result: dict,
    datasheet_result: dict,
    run_ts: str,
    our_price_raw: str = "",
) -> dict:
    """Build full per-SKU evidence bundle.

    All source data is preserved as-is. FX conversion result is additive.
    """
    photo_verdict = vision_verdict.get("verdict", "NO_PHOTO")
    price_status = price_result.get("price_status", "no_price_found")
    sha1 = photo_result.get("sha1", "")

    card_status, review_reasons = assign_card_status(
        photo_verdict=photo_verdict,
        price_status=price_status,
        category_mismatch=bool(price_result.get("category_mismatch")),
        brand_mismatch=bool(price_result.get("brand_mismatch")),
        stock_photo_flag=bool(photo_result.get("stock_photo_flag")),
    )

    canon_fn = canonical_photo_filename(brand, pn, sha1) if sha1 else None

    return {
        "schema_version": "1.1",
        "generated_at": run_ts,
        "pn": pn,
        "brand": brand,
        "name": name,
        "our_price_raw": our_price_raw,

        "card_status": card_status,
        "review_reasons": review_reasons,

        "photo": {
            "verdict": photo_verdict,
            "verdict_reason": vision_verdict.get("reason", ""),
            "path": photo_result.get("path", ""),
            "sha1": sha1,
            "canonical_filename": canon_fn,
            "public_url": None,        # set by storage adapter
            "width": photo_result.get("width", 0),
            "height": photo_result.get("height", 0),
            "size_kb": photo_result.get("size_kb", 0),
            "source": photo_result.get("source", ""),
            "phash": photo_result.get("phash", ""),
            "stock_photo_flag": bool(photo_result.get("stock_photo_flag")),
            "mpn_confirmed_via_jsonld": bool(photo_result.get("mpn_confirmed")),
        },

        "price": {
            "price_status": price_status,
            "price_per_unit": price_result.get("price_usd"),
            "currency": price_result.get("currency"),
            "rub_price": price_result.get("rub_price"),
            "fx_rate_used": price_result.get("fx_rate_used"),
            "fx_provider": price_result.get("fx_provider"),
            "price_confidence": price_result.get("price_confidence", 0),
            "source_url": price_result.get("source_url"),
            "source_type": price_result.get("source_type"),
            "source_tier": price_result.get("source_tier"),
            "stock_status": price_result.get("stock_status", "unknown"),
            "offer_unit_basis": price_result.get("offer_unit_basis", "unknown"),
            "offer_qty": price_result.get("offer_qty"),
            "lead_time_detected": bool(price_result.get("lead_time_detected")),
            "suffix_conflict": bool(price_result.get("suffix_conflict")),
            "category_mismatch": bool(price_result.get("category_mismatch")),
            "page_product_class": price_result.get("page_product_class", ""),
            "brand_mismatch": bool(price_result.get("brand_mismatch")),
        },

        "datasheet": datasheet_result,

        "content": {
            "specs": photo_result.get("specs") or {},
            "description": photo_result.get("description"),
        },

        "trace": {
            "pn_match_location": photo_result.get("pn_match_location", ""),
            "pn_match_confidence": photo_result.get("pn_match_confidence", 0),
            "numeric_pn_guard_triggered": bool(photo_result.get("numeric_pn_guard_triggered")),
            "jsonld_hit": bool(photo_result.get("mpn_confirmed")),
            "source_trust_weight": photo_result.get("source_trust_weight"),
        },
    }


# ── Write helpers ────────────────────────────────────────────────────────────────

def write_evidence_bundles(bundles: list[dict], evidence_dir: Path) -> None:
    """Write one JSON file per SKU into evidence_dir/."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for b in bundles:
        pn_safe = re.sub(r'[\\/:*?"<>|]', "_", b["pn"])
        path = evidence_dir / f"evidence_{pn_safe}.json"
        path.write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")


_BASE_FIELDS = [
    "Артикул", "Название", "Бренд", "Изображение",
    "Цена", "Валюта", "Статус цены", "Статус наличия",
    "Описание", "Статус карточки", "Причины проверки",
]


def write_insales_export(
    bundles: list[dict],
    output_path: Path,
    base_photo_url: str = "",
) -> int:
    """Write InSales-compatible CSV export.

    Only AUTO_PUBLISH and REVIEW_REQUIRED cards are included.
    DRAFT_ONLY are excluded.

    Returns count of exported rows.
    """
    rows = []
    for b in bundles:
        if b["card_status"] == "DRAFT_ONLY":
            continue

        photo = b.get("photo", {})
        price = b.get("price", {})

        # Photo URL
        photo_url = ""
        if photo.get("canonical_filename") and base_photo_url:
            photo_url = f"{base_photo_url.rstrip('/')}/{photo['canonical_filename']}"
        elif photo.get("path"):
            photo_url = f"[LOCAL:{photo['path']}]"

        # Price — RUB if converted, else original
        price_val = price.get("rub_price") or price.get("price_per_unit")
        price_currency = "RUB" if price.get("rub_price") else (price.get("currency") or "")

        row: dict = {
            "Артикул":            b["pn"],
            "Название":           b["name"],
            "Бренд":              b["brand"],
            "Изображение":        photo_url,
            "Цена":               str(price_val) if price_val else "",
            "Валюта":             price_currency,
            "Статус цены":        price.get("price_status", ""),
            "Статус наличия":     price.get("stock_status", ""),
            "Описание":           (b.get("content", {}).get("description") or "")[:500],
            "Статус карточки":    b["card_status"],
            "Причины проверки":   "; ".join(b.get("review_reasons", [])),
        }

        # Specs as additional columns
        for k, v in (b.get("content", {}).get("specs") or {}).items():
            col_name = f"Характеристика: {k}"
            row[col_name] = str(v)[:200]

        rows.append(row)

    if not rows:
        return 0

    # Collect all columns (preserve order)
    all_cols: list[str] = []
    seen: set[str] = set()
    for f in _BASE_FIELDS:
        if f not in seen:
            all_cols.append(f)
            seen.add(f)
    for row in rows:
        for f in row:
            if f not in seen:
                all_cols.append(f)
                seen.add(f)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def write_audit_report(
    bundles: list[dict],
    output_path: Path,
    run_meta: dict,
) -> dict:
    """Write audit_report.json and return summary dict."""
    total = len(bundles)

    def count(pred) -> int:
        return sum(1 for b in bundles if pred(b))

    def pct(n: int) -> str:
        return f"{n / total * 100:.1f}%" if total else "0%"

    auto_pub = count(lambda b: b["card_status"] == "AUTO_PUBLISH")
    review_req = count(lambda b: b["card_status"] == "REVIEW_REQUIRED")
    draft = count(lambda b: b["card_status"] == "DRAFT_ONLY")

    keep = count(lambda b: b["photo"]["verdict"] == "KEEP")
    public_price = count(lambda b: b["price"]["price_status"] == "public_price")
    rfq = count(lambda b: b["price"]["price_status"] == "rfq_only")
    cat_mismatch = count(lambda b: b["price"]["category_mismatch"])
    no_price = count(lambda b: b["price"]["price_status"] in ("no_price_found", ""))
    datasheet_found = count(lambda b: (b.get("datasheet") or {}).get("datasheet_status") == "found")
    numeric_guard = count(lambda b: b["trace"].get("numeric_pn_guard_triggered"))
    stock_flag = count(lambda b: b["photo"].get("stock_photo_flag"))
    suffix_conflict = count(lambda b: b["price"].get("suffix_conflict"))

    summary = {
        "run_meta": run_meta,
        "total_sku": total,
        "photo": {
            "keep": keep, "keep_rate": pct(keep),
            "reject": total - keep - count(lambda b: b["photo"]["verdict"] == "NO_PHOTO"),
            "no_photo": count(lambda b: b["photo"]["verdict"] == "NO_PHOTO"),
        },
        "price": {
            "public_price": public_price,
            "rfq_only": rfq,
            "no_price_found": no_price,
            "category_mismatch_isolated": cat_mismatch,
        },
        "datasheet": {"found": datasheet_found},
        "cards": {
            "auto_publish": auto_pub, "auto_publish_rate": pct(auto_pub),
            "review_required": review_req,
            "draft_only": draft,
        },
        "flags": {
            "numeric_pn_guard_triggered": numeric_guard,
            "stock_photo_flag": stock_flag,
            "suffix_conflict": suffix_conflict,
            "category_mismatch": cat_mismatch,
        },
    }

    per_sku = [
        {
            "pn": b["pn"],
            "name": b["name"][:60],
            "card_status": b["card_status"],
            "photo_verdict": b["photo"]["verdict"],
            "price_status": b["price"]["price_status"],
            "review_reasons": b.get("review_reasons", []),
        }
        for b in bundles
    ]

    report = {**summary, "per_sku": per_sku}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
