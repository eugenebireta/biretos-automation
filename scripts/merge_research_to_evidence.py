"""
merge_research_to_evidence.py — Merge enriched data from research_results/ into evidence/.

Source: research_results/result_<PN>.json  (final_recommendation block)
Target: downloads/evidence/evidence_<PN>.json

Merged fields (only if source is non-empty and target is missing/empty):
  - title_ru           → deep_research.title_ru
  - description_ru     → deep_research.description_ru
  - category_suggestion→ dr_category (if not already set)
  - price_value        → dr_price, dr_currency, dr_price_source (if not already set)
  - photo_url          → dr_image_url (if not already set)
  - specs              → deep_research.specs
  - identity_confirmed → deep_research.identity_confirmed
  - confidence         → deep_research.confidence
  - key_findings       → deep_research.key_findings

Policy:
  - Never overwrite existing non-empty dr_ fields (additive only)
  - Skip results where identity_confirmed=False
  - Skip garbage description_ru (contains "citeturn", length < 10)
  - Price: only merge if price_assessment is admissible_public_price
  - Always record merge metadata: merge_ts, merge_source

Usage:
    python scripts/merge_research_to_evidence.py [--dry-run] [--pn PN]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "research_results"
EVIDENCE_DIR = ROOT / "downloads" / "evidence"

ADMISSIBLE_PRICES = {"admissible_public_price", "public_price"}


def _is_empty(val) -> bool:
    """Check if a value is effectively empty."""
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip() == "" or val.strip().lower() in ("not_found", "not found", "none", "null")
    if isinstance(val, dict):
        return len(val) == 0
    if isinstance(val, list):
        return len(val) == 0
    return False


def _is_garbage_description(desc: str) -> bool:
    """Detect garbage descriptions from LLM artifacts."""
    if not desc or len(desc.strip()) < 10:
        return True
    # Strip Unicode private-use characters before checking
    clean = re.sub(r"[\ue000-\uf8ff]", "", desc)
    if "citeturn" in clean.lower():
        return True
    if "cite" in clean.lower() and "turn" in clean.lower() and "view" in clean.lower():
        return True
    # Pure citation junk
    if re.match(r"^[\s\d\w]*cite[\s\d\w]*$", clean, re.IGNORECASE):
        return True
    # Too short after stripping
    if len(clean.strip()) < 10:
        return True
    return False


def _safe_filename(pn: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", pn)


def load_result(pn: str) -> dict | None:
    """Load research result for a PN."""
    path = RESULTS_DIR / f"result_{pn}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_evidence(pn: str) -> tuple[dict | None, Path]:
    """Load evidence file for a PN."""
    safe = _safe_filename(pn)
    path = EVIDENCE_DIR / f"evidence_{safe}.json"
    if not path.exists():
        return None, path
    try:
        return json.loads(path.read_text(encoding="utf-8")), path
    except (json.JSONDecodeError, OSError):
        return None, path


def merge_one(pn: str, dry_run: bool = False) -> dict:
    """Merge one result into its evidence file.

    Returns a status dict:
      {"pn": str, "action": "merged"|"skipped"|"no_result"|"no_evidence",
       "fields_added": list[str], "reason": str}
    """
    result = load_result(pn)
    if result is None:
        return {"pn": pn, "action": "no_result", "fields_added": [], "reason": "no research result"}

    evidence, ev_path = load_evidence(pn)
    if evidence is None:
        return {"pn": pn, "action": "no_evidence", "fields_added": [], "reason": "no evidence file"}

    fr = result.get("final_recommendation", {})
    if not fr:
        return {"pn": pn, "action": "skipped", "fields_added": [], "reason": "empty final_recommendation"}

    # Skip unconfirmed identity
    if fr.get("identity_confirmed") is False:
        return {"pn": pn, "action": "skipped", "fields_added": [],
                "reason": "identity_confirmed=False"}

    fields_added = []

    # -- deep_research block (additive) --
    dr = evidence.get("deep_research", {})
    if not isinstance(dr, dict):
        dr = {}

    # title_ru
    title_ru = fr.get("title_ru", "")
    if not _is_empty(title_ru) and _is_empty(dr.get("title_ru")):
        dr["title_ru"] = title_ru.strip()
        fields_added.append("title_ru")

    # description_ru
    desc_ru = fr.get("description_ru", "")
    if not _is_empty(desc_ru) and not _is_garbage_description(desc_ru) and _is_empty(dr.get("description_ru")):
        dr["description_ru"] = desc_ru.strip()
        fields_added.append("description_ru")

    # specs
    specs = fr.get("specs", {})
    if not _is_empty(specs) and _is_empty(dr.get("specs")):
        dr["specs"] = specs
        fields_added.append("specs")

    # identity + confidence + key_findings
    if fr.get("identity_confirmed") is not None and "identity_confirmed" not in dr:
        dr["identity_confirmed"] = fr["identity_confirmed"]
        fields_added.append("identity_confirmed")

    confidence = fr.get("confidence") or result.get("confidence")
    if confidence and "confidence" not in dr:
        dr["confidence"] = confidence
        fields_added.append("dr_confidence")

    findings = fr.get("key_findings", [])
    if findings and _is_empty(dr.get("key_findings")):
        dr["key_findings"] = findings
        fields_added.append("key_findings")

    # sources from research
    sources = fr.get("sources", [])
    if sources and _is_empty(dr.get("sources")):
        dr["sources"] = sources
        fields_added.append("dr_sources")

    # Propagate description_ru → content.description_long_ru for Excel export
    desc_long = dr.get("description_ru", "")
    if desc_long and isinstance(evidence.get("content"), dict):
        if _is_empty(evidence["content"].get("description_long_ru")):
            evidence["content"]["description_long_ru"] = desc_long
            fields_added.append("content.description_long_ru")

    # merge metadata
    if fields_added:
        dr["merge_ts"] = datetime.now(timezone.utc).isoformat()
        dr["merge_source"] = f"result_{pn}.json"
        evidence["deep_research"] = dr

    # -- Top-level dr_ fields (only if not already set) --

    # dr_category
    cat = fr.get("category_suggestion", "")
    if not _is_empty(cat) and _is_empty(evidence.get("dr_category")):
        evidence["dr_category"] = cat.strip()
        fields_added.append("dr_category")

    # dr_image_url
    photo = fr.get("photo_url", "")
    if not _is_empty(photo) and _is_empty(evidence.get("dr_image_url")):
        evidence["dr_image_url"] = photo.strip()
        fields_added.append("dr_image_url")

    # dr_price, dr_currency, dr_price_source
    price_assessment = fr.get("price_assessment", "")
    price_value = fr.get("price_value", {})
    if (price_assessment in ADMISSIBLE_PRICES
            and isinstance(price_value, dict)
            and price_value.get("amount")
            and _is_empty(evidence.get("dr_price"))):
        evidence["dr_price"] = price_value["amount"]
        evidence["dr_currency"] = price_value.get("currency", "")
        evidence["dr_price_source"] = price_value.get("source_url", "")
        fields_added.append("dr_price")

    if not fields_added:
        return {"pn": pn, "action": "skipped", "fields_added": [],
                "reason": "all fields already populated"}

    if not dry_run:
        ev_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"pn": pn, "action": "merged", "fields_added": fields_added, "reason": ""}


def run(dry_run: bool = False, pn_filter: str | None = None) -> dict:
    """Run merge across all results.

    Returns summary dict.
    """
    result_files = sorted(RESULTS_DIR.glob("result_*.json"))
    pns = []
    for f in result_files:
        pn = f.stem.replace("result_", "")
        if pn_filter and pn != pn_filter:
            continue
        pns.append(pn)

    merged = 0
    skipped = 0
    no_evidence = 0
    no_result = 0
    all_fields = []
    details = []

    for pn in pns:
        status = merge_one(pn, dry_run=dry_run)
        details.append(status)
        if status["action"] == "merged":
            merged += 1
            all_fields.extend(status["fields_added"])
        elif status["action"] == "skipped":
            skipped += 1
        elif status["action"] == "no_evidence":
            no_evidence += 1
        elif status["action"] == "no_result":
            no_result += 1

    # Field counts
    from collections import Counter
    field_counts = dict(Counter(all_fields))

    summary = {
        "total": len(pns),
        "merged": merged,
        "skipped": skipped,
        "no_evidence": no_evidence,
        "no_result": no_result,
        "dry_run": dry_run,
        "field_counts": field_counts,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    log.info(f"Merge complete: {merged} merged, {skipped} skipped, "
             f"{no_evidence} no evidence, {no_result} no result")
    log.info(f"Fields added: {field_counts}")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Merge research results into evidence files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be merged without writing")
    parser.add_argument("--pn", type=str, default=None, help="Process only this PN")
    args = parser.parse_args()

    summary = run(dry_run=args.dry_run, pn_filter=args.pn)

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.dry_run:
        print("\n[DRY RUN] No files were modified.")


if __name__ == "__main__":
    main()
