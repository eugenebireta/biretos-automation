"""brand_experience_writer.py — Per-brand enrichment experience recorder.

Records structured per-SKU enrichment outcomes keyed by brand/PN for:
- Local AI training data (brand-specific search strategies)
- RAG retrieval (what worked / didn't for this brand)
- Retrospective analysis (domains, quality, corrections)

Uses enrichment_experience_log.py as the write backend (existing JSONL log).
The experience records are stored in shadow_log/experience_YYYY-MM.jsonl
with task_family="brand_<brand>" for filtering.

NEVER raises — all exceptions are swallowed (non-blocking for pipeline).
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

_ROOT = Path(_scripts_dir).parent
_SHADOW_LOG_DIR = _ROOT / "shadow_log"
BRAND_EXP_SCHEMA = "brand_experience_v1"


@dataclass
class BrandExperienceRecord:
    """Structured per-SKU brand experience for training and RAG."""
    brand: str
    pn: str
    pn_family: Optional[str] = None

    # Search experience
    search_queries_used: list[str] = field(default_factory=list)
    sources_tried: list[str] = field(default_factory=list)
    sources_that_worked: list[str] = field(default_factory=list)
    sources_that_failed: list[str] = field(default_factory=list)

    # Results
    price_found: bool = False
    price_currency: Optional[str] = None
    price_source_tier: Optional[str] = None
    photo_found: bool = False
    photo_quality: Optional[str] = None  # "KEEP" | "REJECT" | "NO_PHOTO"
    datasheet_found: bool = False
    specs_extracted: dict = field(default_factory=dict)
    jsonld_fields_found: list[str] = field(default_factory=list)

    # Outcome
    category_confirmed: Optional[str] = None
    card_status: str = "unknown"
    training_label: str = "unknown"  # "success" | "partial" | "failed"
    correction: Optional[str] = None


def _calc_salience(r: BrandExperienceRecord) -> int:
    if r.correction:
        return 9  # Corrections are highest priority for training
    if r.training_label == "failed":
        return 7  # Failures are highly informative
    if r.training_label == "success":
        return 4  # Successes are baseline
    return 5


def _build_summary(r: BrandExperienceRecord) -> str:
    parts = [f"{r.brand}/{r.pn}"]
    if r.pn_family and r.pn_family != r.brand:
        parts.append(f"({r.pn_family})")
    parts.append(f"->{r.card_status}")
    if r.price_found:
        parts.append(f"price:{r.price_currency or 'ok'}")
    if r.photo_quality:
        parts.append(f"photo:{r.photo_quality}")
    if r.specs_extracted:
        parts.append(f"specs:{len(r.specs_extracted)}")
    if r.correction:
        parts.append(f"FIX:{r.correction[:20]}")
    summary = " ".join(parts)
    return summary[:200]


def write_brand_experience(
    record: BrandExperienceRecord,
    shadow_log_dir: Optional[Path] = None,
) -> None:
    """Write brand experience record to shadow_log/experience_YYYY-MM.jsonl.

    Builds a structured JSONL record compatible with enrichment_experience_log schema.
    NEVER raises — all exceptions are swallowed.
    """
    try:
        log_dir = shadow_log_dir or _SHADOW_LOG_DIR
        month = datetime.datetime.utcnow().strftime("%Y-%m")
        path = log_dir / f"experience_{month}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)

        # Derive pn_family from brand_knowledge if not provided
        if record.pn_family is None:
            try:
                from brand_knowledge import get_product_family
                record.pn_family = get_product_family(record.brand, record.pn)
            except Exception:
                pass

        exp_record = {
            "schema_version": BRAND_EXP_SCHEMA,
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "pn": record.pn,
            "brand": record.brand,
            "task_type": "brand_enrichment",
            "task_family": f"brand_{record.brand.lower().replace(' ', '_')}",
            "pn_family": record.pn_family,
            "decision": record.card_status,
            "reason_code": record.training_label,
            "outcome": record.training_label,
            "salience_score": _calc_salience(record),
            "summary": _build_summary(record),
            # Search experience (domain-normalised)
            "sources_worked": [_domain(u) for u in record.sources_that_worked],
            "sources_failed": [_domain(u) for u in record.sources_that_failed],
            # Results
            "price_found": record.price_found,
            "price_currency": record.price_currency,
            "price_source_tier": record.price_source_tier,
            "photo_quality": record.photo_quality,
            "datasheet_found": record.datasheet_found,
            "specs_count": len(record.specs_extracted),
            "jsonld_fields": record.jsonld_fields_found,
            # Training
            "training_label": record.training_label,
            "correction": record.correction,
            "correction_if_any": record.correction,
        }

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(exp_record, ensure_ascii=False) + "\n")

    except Exception as exc:
        log.debug(f"write_brand_experience failed for {record.pn}: {exc}")


def _domain(url: str) -> str:
    """Extract domain from URL, or return as-is if not a URL."""
    if url.startswith("http"):
        try:
            return urlparse(url).netloc or url
        except Exception:
            pass
    return url[:60]


def build_brand_experience_from_bundle(bundle: dict) -> BrandExperienceRecord:
    """Build a BrandExperienceRecord from a completed evidence bundle.

    Call this after build_evidence_bundle() + save_checkpoint().
    """
    pn = bundle.get("pn", "")
    brand = bundle.get("brand", "Honeywell")
    card_status = bundle.get("card_status", "unknown")

    photo_verdict = bundle.get("photo", {}).get("verdict", "NO_PHOTO")
    photo_quality = photo_verdict  # "KEEP" | "REJECT" | "NO_PHOTO"

    price = bundle.get("price", {})
    price_status = price.get("price_status", "no_price_found")
    price_found = price_status in ("public_price", "admissible_public_price", "ACCEPTED")
    price_currency = price.get("currency")
    price_tier = price.get("source_tier")

    datasheet = bundle.get("datasheet", {})
    datasheet_found = datasheet.get("datasheet_status") == "found"

    specs = bundle.get("content", {}).get("specs") or {}
    jsonld = bundle.get("jsonld_full") or {}
    jsonld_fields = [k for k, v in jsonld.items() if v is not None]

    # Source URLs
    source_url = price.get("source_url") or bundle.get("photo", {}).get("source", "")
    sources_worked = [source_url] if source_url and price_found else []
    sources_tried = [source_url] if source_url else []

    # Training label
    if card_status in ("AUTO_PUBLISH", "PROMOTE_CANONICAL"):
        training_label = "success"
    elif card_status == "DRAFT_ONLY":
        training_label = "failed"
    else:
        training_label = "partial"

    return BrandExperienceRecord(
        brand=brand,
        pn=pn,
        sources_tried=sources_tried,
        sources_that_worked=sources_worked,
        price_found=price_found,
        price_currency=price_currency,
        price_source_tier=price_tier,
        photo_found=photo_quality == "KEEP",
        photo_quality=photo_quality,
        datasheet_found=datasheet_found,
        specs_extracted=specs,
        jsonld_fields_found=jsonld_fields,
        category_confirmed=bundle.get("expected_category"),
        card_status=card_status,
        training_label=training_label,
    )


if __name__ == "__main__":
    import json as _json
    from pathlib import Path as _Path

    # Demonstrate by building records from existing evidence bundles
    evidence_dir = _ROOT / "downloads" / "evidence"
    bundles = []
    for f in sorted(evidence_dir.glob("evidence_*.json"))[:5]:
        try:
            b = _json.loads(f.read_text(encoding="utf-8"))
            bundles.append(b)
        except Exception:
            continue

    print(f"Building brand experience records from {len(bundles)} evidence bundles...")
    for bundle in bundles:
        rec = build_brand_experience_from_bundle(bundle)
        print(f"  {rec.pn}: label={rec.training_label} photo={rec.photo_quality} "
              f"price={rec.price_found} specs={len(rec.specs_extracted)}")
        print(f"    summary: {_build_summary(rec)}")
